from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.config.settings import Settings
from app.db.repository import Repository
from app.models.core import Route
from app.readiness.service import ReadinessService
from app.utils.confidence import normalize_support_status


@dataclass(slots=True)
class KpiEvaluation:
    name: str
    status: str
    value: str
    threshold: str
    critical: bool
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "value": self.value,
            "threshold": self.threshold,
            "critical": self.critical,
            "note": self.note,
        }


class CommissioningService:
    def __init__(self, settings: Settings, readiness_service: ReadinessService) -> None:
        self.settings = settings
        self.readiness_service = readiness_service

    async def commissioning_route_rows(
        self,
        repo: Repository,
        *,
        route_id: str | None = None,
    ) -> list[dict[str, object]]:
        routes = await repo.list_routes()
        readiness_rows = await self.readiness_service.route_readiness_rows(repo)
        readiness_by_route = {str(row["route_id"]): row for row in readiness_rows}

        output: list[dict[str, object]] = []
        for route in routes:
            if route_id is not None and route.id != route_id:
                continue
            stats = await repo.commissioning_stats_for_route(route.id)
            readiness = readiness_by_route.get(route.id)
            output.append(self._build_route_row(route, stats=stats, readiness=readiness))
        return output

    async def commissioning_summary(self, repo: Repository) -> dict[str, object]:
        rows = await self.commissioning_route_rows(repo)
        latest_mode = await repo.latest_backtest_mode()
        phase_counts: dict[str, int] = {}
        fail_routes = 0
        warn_routes = 0
        live_intent = 0
        shadow = 0
        for row in rows:
            phase = str(row["phase"])
            phase_counts[phase] = phase_counts.get(phase, 0) + 1
            if any(str(item["status"]) == "fail" for item in row["kpi_evaluations"]):  # type: ignore[index]
                fail_routes += 1
            if any(str(item["status"]) == "warn" for item in row["kpi_evaluations"]):  # type: ignore[index]
                warn_routes += 1
            if str(row["route_type"]) == "live_intent":
                live_intent += 1
            if str(row["route_type"]) == "shadow":
                shadow += 1

        return {
            "total_routes": len(rows),
            "routes_not_ready": sum(1 for row in rows if row["promotion_gate_status"] == "not_ready"),
            "routes_observation_ready": sum(
                1 for row in rows if row["promotion_gate_status"] == "observation_ready"
            ),
            "routes_review_ready": sum(1 for row in rows if row["promotion_gate_status"] == "review_ready"),
            "routes_promotion_blocked": sum(
                1 for row in rows if row["promotion_gate_status"] == "promotion_blocked"
            ),
            "live_intent_routes": live_intent,
            "shadow_routes": shadow,
            "latest_backtest_mode": latest_mode,
            "phase_counts": phase_counts,
            "gate_fail_route_count": fail_routes,
            "gate_warn_route_count": warn_routes,
        }

    def _build_route_row(
        self,
        route: Route,
        *,
        stats: dict[str, object],
        readiness: dict[str, object] | None,
    ) -> dict[str, object]:
        strategy = route.strategy
        route_type = self._route_type(strategy)
        support_status = normalize_support_status(
            str((readiness or {}).get("support_status", "unknown"))
        )
        readiness_grade = str((readiness or {}).get("readiness_grade", "red")).strip().lower() or "red"
        fatal_paused = bool((readiness or {}).get("fatal_paused", False))
        readiness_blockers = [str(item) for item in (readiness or {}).get("readiness_blockers", [])]
        readiness_actions = [str(item) for item in (readiness or {}).get("human_action_items", [])]

        observation_window_days = Decimal(str(stats.get("observation_window_days", "0")))
        market_snapshot_count = int(stats.get("market_snapshot_count", 0))
        opportunity_count = int(stats.get("opportunity_count", 0))
        backtest_run_count_total = int(stats.get("backtest_run_count_total", 0))
        backtest_run_count_market_snapshots = int(stats.get("backtest_run_count_market_snapshots", 0))
        backtest_run_count_opportunities = int(stats.get("backtest_run_count_opportunities", 0))
        quote_unavailable_rate = Decimal(str(stats.get("quote_unavailable_rate", "0")))
        health_unknown_rate = Decimal(str(stats.get("health_unknown_rate", "0")))
        fee_unverified_rate = Decimal(str(stats.get("fee_unverified_rate", "0")))
        balance_unverified_rate = Decimal(str(stats.get("balance_unverified_rate", "0")))
        quote_mismatch_rate = Decimal(str(stats.get("quote_mismatch_rate", "0")))
        fatal_pause_count = int(stats.get("fatal_pause_count", 0))
        cooldown_event_count = int(stats.get("cooldown_event_count", 0))

        kpis = self._evaluate_kpis(
            route_type=route_type,
            observation_window_days=observation_window_days,
            market_snapshot_count=market_snapshot_count,
            opportunity_count=opportunity_count,
            backtest_run_count_total=backtest_run_count_total,
            backtest_run_count_market_snapshots=backtest_run_count_market_snapshots,
            backtest_run_count_opportunities=backtest_run_count_opportunities,
            quote_unavailable_rate=quote_unavailable_rate,
            health_unknown_rate=health_unknown_rate,
            fee_unverified_rate=fee_unverified_rate,
            balance_unverified_rate=balance_unverified_rate,
            quote_mismatch_rate=quote_mismatch_rate,
            support_status=support_status,
            readiness_grade=readiness_grade,
            fatal_paused=fatal_paused,
            fatal_pause_count=fatal_pause_count,
            cooldown_event_count=cooldown_event_count,
        )

        minimum_gate_passed = self._minimum_gate_passed(
            route_type=route_type,
            observation_window_days=observation_window_days,
            market_snapshot_count=market_snapshot_count,
            opportunity_count=opportunity_count,
            backtest_run_count_total=backtest_run_count_total,
            backtest_run_count_market_snapshots=backtest_run_count_market_snapshots,
            backtest_run_count_opportunities=backtest_run_count_opportunities,
            quote_unavailable_rate=quote_unavailable_rate,
            support_status=support_status,
            readiness_grade=readiness_grade,
            fatal_paused=fatal_paused,
        )
        critical_fails = [item.name for item in kpis if item.critical and item.status == "fail"]
        promotion_gate_status = self._promotion_gate_status(
            route_type=route_type,
            critical_fails=critical_fails,
            minimum_gate_passed=minimum_gate_passed,
        )
        phase = self._phase_for_route(
            market_snapshot_count=market_snapshot_count,
            opportunity_count=opportunity_count,
            backtest_run_count_total=backtest_run_count_total,
            promotion_gate_status=promotion_gate_status,
        )

        blockers = list(dict.fromkeys(critical_fails + readiness_blockers))
        actions = list(dict.fromkeys(readiness_actions + [item.note for item in kpis if item.note and item.status != "pass"]))

        return {
            "route_id": route.id,
            "strategy": strategy,
            "route_type": route_type,
            "phase": phase,
            "readiness_grade": readiness_grade,
            "promotion_gate_status": promotion_gate_status,
            "observation_window_days": observation_window_days,
            "market_snapshot_count": market_snapshot_count,
            "opportunity_count": opportunity_count,
            "quote_unavailable_rate": quote_unavailable_rate,
            "health_unknown_rate": health_unknown_rate,
            "fee_unverified_rate": fee_unverified_rate,
            "balance_unverified_rate": balance_unverified_rate,
            "quote_mismatch_rate": quote_mismatch_rate,
            "backtest_run_count_total": backtest_run_count_total,
            "backtest_run_count_market_snapshots": backtest_run_count_market_snapshots,
            "backtest_run_count_opportunities": backtest_run_count_opportunities,
            "fatal_pause_count": fatal_pause_count,
            "cooldown_event_count": cooldown_event_count,
            "blocked_reason_top_n": list(stats.get("blocked_reason_top_n", [])),
            "latest_backtest_pnl": Decimal(str(stats.get("latest_backtest_pnl", "0"))),
            "median_backtest_pnl": Decimal(str(stats.get("median_backtest_pnl", "0"))),
            "worst_backtest_drawdown": Decimal(str(stats.get("worst_backtest_drawdown", "0"))),
            "latest_readiness_grade": readiness_grade,
            "kpi_evaluations": [item.to_dict() for item in kpis],
            "gate_blockers": blockers,
            "human_action_items": actions,
        }

    def _evaluate_kpis(
        self,
        *,
        route_type: str,
        observation_window_days: Decimal,
        market_snapshot_count: int,
        opportunity_count: int,
        backtest_run_count_total: int,
        backtest_run_count_market_snapshots: int,
        backtest_run_count_opportunities: int,
        quote_unavailable_rate: Decimal,
        health_unknown_rate: Decimal,
        fee_unverified_rate: Decimal,
        balance_unverified_rate: Decimal,
        quote_mismatch_rate: Decimal,
        support_status: str,
        readiness_grade: str,
        fatal_paused: bool,
        fatal_pause_count: int,
        cooldown_event_count: int,
    ) -> list[KpiEvaluation]:
        is_live = route_type == "live_intent"
        quote_warn_max = self._warn_quote_unavailable_max(route_type)

        kpis: list[KpiEvaluation] = [
            self._minimum_kpi(
                "observation_window_days",
                observation_window_days,
                Decimal(
                    self.settings.commissioning_live_min_observation_days
                    if is_live
                    else self.settings.commissioning_shadow_min_observation_days
                ),
                critical=True,
                note="Collect more real observation days before promotion review.",
            ),
            self._minimum_kpi(
                "market_snapshot_count",
                Decimal(market_snapshot_count),
                Decimal(
                    self.settings.commissioning_live_min_market_snapshots
                    if is_live
                    else self.settings.commissioning_shadow_min_market_snapshots
                ),
                critical=True,
                note="Increase market snapshot persistence volume for this route.",
            ),
            self._minimum_kpi(
                "opportunity_count",
                Decimal(opportunity_count),
                Decimal(
                    self.settings.commissioning_live_min_opportunities
                    if is_live
                    else self.settings.commissioning_shadow_min_opportunities
                ),
                critical=True,
                note="Collect more opportunity records to reduce sampling bias.",
            ),
        ]

        if is_live:
            kpis.append(
                self._minimum_kpi(
                    "backtest_run_count_market_snapshots",
                    Decimal(backtest_run_count_market_snapshots),
                    Decimal(self.settings.commissioning_live_min_backtest_runs_market_snapshots),
                    critical=True,
                    note="Run additional market_snapshots replay backtests.",
                )
            )
            kpis.append(
                self._minimum_kpi(
                    "backtest_run_count_opportunities",
                    Decimal(backtest_run_count_opportunities),
                    Decimal(self.settings.commissioning_live_min_backtest_runs_opportunities),
                    critical=True,
                    note="Run additional opportunities replay backtests.",
                )
            )
        else:
            kpis.append(
                self._minimum_kpi(
                    "backtest_run_count_total",
                    Decimal(backtest_run_count_total),
                    Decimal(self.settings.commissioning_shadow_min_backtest_runs_total),
                    critical=True,
                    note="Run additional replay/backtest iterations for observation review.",
                )
            )

        kpis.extend(
            [
                self._rate_kpi(
                    "quote_unavailable_rate",
                    quote_unavailable_rate,
                    self.settings.commissioning_live_max_quote_unavailable_rate
                    if is_live
                    else self.settings.commissioning_shadow_max_quote_unavailable_rate,
                    quote_warn_max,
                    critical=True,
                    note="Reduce quote_unavailable frequency by fixing route support or keeping route out of promotion scope.",
                ),
                self._rate_kpi(
                    "health_unknown_rate",
                    health_unknown_rate,
                    self.settings.commissioning_warn_health_unknown_rate,
                    self.settings.commissioning_fail_health_unknown_rate,
                    critical=True,
                    note="Stabilize health telemetry so unknown states are rare and explainable.",
                ),
                self._rate_kpi(
                    "fee_unverified_rate",
                    fee_unverified_rate,
                    self.settings.commissioning_warn_fee_unverified_rate,
                    self.settings.commissioning_fail_fee_unverified_rate,
                    critical=True,
                    note="Increase fee provenance confidence and reduce fallback-only runs.",
                ),
                self._rate_kpi(
                    "balance_unverified_rate",
                    balance_unverified_rate,
                    self.settings.commissioning_warn_balance_unverified_rate,
                    self.settings.commissioning_fail_balance_unverified_rate,
                    critical=True,
                    note="Improve balance verification (wallet/venue) and eliminate inventory drift.",
                ),
                self._rate_kpi(
                    "quote_mismatch_rate",
                    quote_mismatch_rate,
                    self.settings.commissioning_warn_quote_mismatch_rate,
                    self.settings.commissioning_fail_quote_mismatch_rate,
                    critical=True,
                    note="Address quote mismatch causes before promotion review.",
                ),
                self._enum_kpi(
                    "support_status",
                    support_status,
                    pass_when={"supported"},
                    warn_when=set(),
                    critical=True,
                    note="Unsupported or unknown support status must be resolved before promotion.",
                ),
                self._enum_kpi(
                    "readiness_grade",
                    readiness_grade,
                    pass_when={"green"},
                    warn_when={"yellow"},
                    critical=True,
                    note="Keep route out of promotion while readiness is red.",
                ),
                self._bool_kpi(
                    "fatal_pause_unresolved",
                    not fatal_paused,
                    critical=True,
                    note="Resolve fatal pause conditions and clear route pause with audit logging.",
                ),
                self._minimum_kpi(
                    "fatal_pause_count",
                    Decimal(fatal_pause_count),
                    Decimal("0"),
                    critical=False,
                    note="Review repeated fatal failure history before promotion discussions.",
                    reverse=True,
                ),
                self._minimum_kpi(
                    "cooldown_event_count",
                    Decimal(cooldown_event_count),
                    Decimal("0"),
                    critical=False,
                    note="Investigate recurring cooldown triggers and reduce instability.",
                    reverse=True,
                ),
            ]
        )
        return kpis

    def _minimum_gate_passed(
        self,
        *,
        route_type: str,
        observation_window_days: Decimal,
        market_snapshot_count: int,
        opportunity_count: int,
        backtest_run_count_total: int,
        backtest_run_count_market_snapshots: int,
        backtest_run_count_opportunities: int,
        quote_unavailable_rate: Decimal,
        support_status: str,
        readiness_grade: str,
        fatal_paused: bool,
    ) -> bool:
        is_live = route_type == "live_intent"
        min_days = Decimal(
            self.settings.commissioning_live_min_observation_days
            if is_live
            else self.settings.commissioning_shadow_min_observation_days
        )
        min_snapshots = Decimal(
            self.settings.commissioning_live_min_market_snapshots
            if is_live
            else self.settings.commissioning_shadow_min_market_snapshots
        )
        min_opps = Decimal(
            self.settings.commissioning_live_min_opportunities
            if is_live
            else self.settings.commissioning_shadow_min_opportunities
        )
        max_unavailable = (
            self.settings.commissioning_live_max_quote_unavailable_rate
            if is_live
            else self.settings.commissioning_shadow_max_quote_unavailable_rate
        )
        backtest_ok = (
            backtest_run_count_market_snapshots >= self.settings.commissioning_live_min_backtest_runs_market_snapshots
            and backtest_run_count_opportunities >= self.settings.commissioning_live_min_backtest_runs_opportunities
        ) if is_live else (backtest_run_count_total >= self.settings.commissioning_shadow_min_backtest_runs_total)

        return (
            observation_window_days >= min_days
            and Decimal(market_snapshot_count) >= min_snapshots
            and Decimal(opportunity_count) >= min_opps
            and backtest_ok
            and quote_unavailable_rate <= max_unavailable
            and support_status == "supported"
            and readiness_grade != "red"
            and not fatal_paused
        )

    @staticmethod
    def _route_type(strategy: str) -> str:
        if strategy == "hyperevm_dex_dex":
            return "live_intent"
        if strategy == "base_virtual_shadow":
            return "shadow"
        return "other"

    @staticmethod
    def _promotion_gate_status(
        *,
        route_type: str,
        critical_fails: list[str],
        minimum_gate_passed: bool,
    ) -> str:
        if critical_fails:
            return "promotion_blocked"
        if not minimum_gate_passed:
            return "not_ready"
        if route_type == "shadow":
            return "observation_ready"
        if route_type == "live_intent":
            return "review_ready"
        return "not_ready"

    @staticmethod
    def _phase_for_route(
        *,
        market_snapshot_count: int,
        opportunity_count: int,
        backtest_run_count_total: int,
        promotion_gate_status: str,
    ) -> str:
        if market_snapshot_count == 0 and opportunity_count == 0:
            return "phase_0_mock_sanity"
        if backtest_run_count_total == 0:
            return "phase_1_real_observation"
        if promotion_gate_status in {"review_ready", "observation_ready"}:
            return "phase_3_commissioning_review"
        return "phase_2_replay_review"

    def _warn_quote_unavailable_max(self, route_type: str) -> Decimal:
        base = (
            self.settings.commissioning_live_max_quote_unavailable_rate
            if route_type == "live_intent"
            else self.settings.commissioning_shadow_max_quote_unavailable_rate
        )
        expanded = (base * Decimal("1.5")).quantize(Decimal("0.00001"))
        return min(expanded, Decimal("1"))

    @staticmethod
    def _minimum_kpi(
        name: str,
        value: Decimal,
        threshold: Decimal,
        *,
        critical: bool,
        note: str,
        reverse: bool = False,
    ) -> KpiEvaluation:
        if reverse:
            status = "pass" if value <= threshold else "warn"
            return KpiEvaluation(
                name=name,
                status=status,
                value=str(value),
                threshold=f"<= {threshold}",
                critical=critical,
                note=note,
            )
        status = "pass" if value >= threshold else "fail"
        return KpiEvaluation(
            name=name,
            status=status,
            value=str(value),
            threshold=f">= {threshold}",
            critical=critical,
            note=note,
        )

    @staticmethod
    def _rate_kpi(
        name: str,
        value: Decimal,
        pass_max: Decimal,
        warn_max: Decimal,
        *,
        critical: bool,
        note: str,
    ) -> KpiEvaluation:
        if value <= pass_max:
            status = "pass"
        elif value <= warn_max:
            status = "warn"
        else:
            status = "fail"
        return KpiEvaluation(
            name=name,
            status=status,
            value=str(value),
            threshold=f"pass<= {pass_max}, warn<= {warn_max}",
            critical=critical,
            note=note,
        )

    @staticmethod
    def _enum_kpi(
        name: str,
        value: str,
        *,
        pass_when: set[str],
        warn_when: set[str],
        critical: bool,
        note: str,
    ) -> KpiEvaluation:
        if value in pass_when:
            status = "pass"
        elif value in warn_when:
            status = "warn"
        else:
            status = "fail"
        return KpiEvaluation(
            name=name,
            status=status,
            value=value,
            threshold=f"pass={sorted(pass_when)}, warn={sorted(warn_when)}",
            critical=critical,
            note=note,
        )

    @staticmethod
    def _bool_kpi(name: str, ok: bool, *, critical: bool, note: str) -> KpiEvaluation:
        return KpiEvaluation(
            name=name,
            status="pass" if ok else "fail",
            value=str(ok).lower(),
            threshold="must be true",
            critical=critical,
            note=note,
        )
