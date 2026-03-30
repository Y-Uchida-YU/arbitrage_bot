from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.config.settings import Settings
from app.db.repository import Repository
from app.models.core import Route
from app.utils.confidence import (
    balance_confidence_at_least,
    fee_confidence_at_least,
    normalize_balance_confidence,
    normalize_fee_confidence,
    normalize_quote_match_status,
)


class ReadinessService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def route_readiness_rows(
        self,
        repo: Repository,
        *,
        route_id: str | None = None,
    ) -> list[dict[str, object]]:
        routes = await repo.list_routes()
        target_routes = [r for r in routes if route_id is None or r.id == route_id]
        output: list[dict[str, object]] = []
        for route in target_routes:
            output.append(await self._build_route_row(repo, route))
        return output

    async def readiness_summary(self, repo: Repository) -> dict[str, object]:
        rows = await self.route_readiness_rows(repo)
        red = sum(1 for row in rows if row["readiness_grade"] == "red")
        yellow = sum(1 for row in rows if row["readiness_grade"] == "yellow")
        green = sum(1 for row in rows if row["readiness_grade"] == "green")

        last_mode = "none"
        ordered = sorted(
            rows,
            key=lambda x: self._as_utc(x["last_observation_at"]) or datetime.fromtimestamp(0, tz=timezone.utc),
            reverse=True,
        )
        if ordered:
            last_mode = str(ordered[0].get("last_backtest_mode", "none"))

        return {
            "red_count": red,
            "yellow_count": yellow,
            "green_count": green,
            "total_routes": len(rows),
            "latest_backtest_mode": last_mode,
        }

    async def _build_route_row(self, repo: Repository, route: Route) -> dict[str, object]:
        latest_health = await repo.latest_route_health_snapshot(route.id)
        runtime = await repo.get_route_runtime_state(route.id)
        observation = await repo.market_snapshot_stats_for_route(route.id)
        opp_stats = await repo.opportunity_stats_for_route(route.id)
        backtest_stats = await repo.backtest_stats_for_route(route.id)

        support_status = str(getattr(latest_health, "support_status", "unknown")).strip().lower()
        fee_status = normalize_fee_confidence(getattr(latest_health, "fee_known_status", "unknown"))
        balance_status = normalize_balance_confidence(getattr(latest_health, "balance_match_status", "unknown"))
        quote_match_status = normalize_quote_match_status(getattr(latest_health, "quote_match_status", "unknown"))

        cooldown_active = False
        fatal_paused = False
        if runtime is not None:
            cooldown_until = self._as_utc(runtime.cooldown_until)
            cooldown_active = bool(cooldown_until and cooldown_until > datetime.now(timezone.utc))
            fatal_paused = bool(runtime.paused and runtime.last_failure_fatal)
        if latest_health is not None:
            cooldown_active = cooldown_active or bool(latest_health.cooldown_active)

        blockers, actions = self._build_blockers_and_actions(
            support_status=support_status,
            fee_status=fee_status,
            balance_status=balance_status,
            quote_match_status=quote_match_status,
            cooldown_active=cooldown_active,
            fatal_paused=fatal_paused,
            observation_count=int(observation["observation_count"]),
            backtest_run_count=int(backtest_stats["backtest_run_count"]),
            quote_unavailable_rate=Decimal(opp_stats["quote_unavailable_rate"]),
        )
        grade = self._grade_from_blockers(blockers)

        return {
            "route_id": route.id,
            "strategy": route.strategy,
            "support_status": support_status,
            "fee_known_status": fee_status,
            "balance_match_status": balance_status,
            "quote_match_status": quote_match_status,
            "cooldown_active": cooldown_active,
            "fatal_paused": fatal_paused,
            "observation_count": int(observation["observation_count"]),
            "last_observation_at": self._as_utc(observation["last_observation_at"]),
            "quote_unavailable_rate": Decimal(opp_stats["quote_unavailable_rate"]),
            "recent_blocked_reasons": list(opp_stats["blocked_top"]),
            "backtest_run_count": int(backtest_stats["backtest_run_count"]),
            "last_backtest_status": str(backtest_stats["last_backtest_status"]),
            "last_backtest_pnl": Decimal(backtest_stats["last_backtest_pnl"]),
            "last_backtest_mode": str(backtest_stats["last_backtest_mode"]),
            "readiness_grade": grade,
            "readiness_blockers": blockers,
            "human_action_items": actions,
        }

    def _build_blockers_and_actions(
        self,
        *,
        support_status: str,
        fee_status: str,
        balance_status: str,
        quote_match_status: str,
        cooldown_active: bool,
        fatal_paused: bool,
        observation_count: int,
        backtest_run_count: int,
        quote_unavailable_rate: Decimal,
    ) -> tuple[list[str], list[str]]:
        blockers: list[str] = []
        actions: list[str] = []

        if support_status != "supported":
            blockers.append("unsupported_route")
            actions.append("Resolve adapter/quoter support and eliminate quote_unavailable before readiness review.")
        if not fee_confidence_at_least(fee_status, "venue_declared"):
            blockers.append("fee_unverified")
            actions.append("Collect venue/account or chain-verified fee provenance for this route.")
        if balance_status == "mismatch":
            blockers.append("balance_mismatch")
            actions.append("Investigate balance drift and reconcile DB/inventory/wallet state.")
        elif not balance_confidence_at_least(balance_status, "wallet_verified"):
            blockers.append("balance_unverified")
            actions.append("Add wallet/venue balance verification and keep drift checks green.")
        if quote_match_status != "matched":
            blockers.append("quote_match_unverified")
            actions.append("Stabilize quote consistency checks to avoid unknown/mismatch states.")
        if observation_count < 20:
            blockers.append("insufficient_observations")
            actions.append("Accumulate more real observation records before readiness gating.")
        if backtest_run_count < 1:
            blockers.append("backtest_missing")
            actions.append("Run both opportunities and market_snapshots replay for this route.")
        if quote_unavailable_rate >= Decimal("0.20"):
            blockers.append("quote_unavailable_rate_high")
            actions.append("Reduce quote_unavailable rate by fixing route support/health dependencies.")
        if cooldown_active:
            blockers.append("cooldown_active")
            actions.append("Clear cooldown only after root cause analysis and audit logging.")
        if fatal_paused:
            blockers.append("fatal_paused")
            actions.append("Keep route paused until fatal failure category is resolved and re-tested.")

        dedup_actions: list[str] = []
        seen: set[str] = set()
        for item in actions:
            if item in seen:
                continue
            seen.add(item)
            dedup_actions.append(item)

        return blockers, dedup_actions

    @staticmethod
    def _grade_from_blockers(blockers: list[str]) -> str:
        if not blockers:
            return "green"
        critical = {
            "unsupported_route",
            "fee_unverified",
            "balance_mismatch",
            "balance_unverified",
            "backtest_missing",
            "fatal_paused",
        }
        if any(blocker in critical for blocker in blockers):
            return "red"
        return "yellow"

    @staticmethod
    def _as_utc(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
