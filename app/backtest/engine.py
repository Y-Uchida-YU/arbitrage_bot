from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from app.config.settings import Settings
from app.db.repository import Repository
from app.models.core import MarketSnapshot, Opportunity, RouteHealthSnapshot
from app.utils.confidence import (
    balance_confidence_at_least,
    fee_confidence_at_least,
    normalize_balance_confidence,
    normalize_fee_confidence,
    normalize_quote_match_status,
    normalize_support_status,
)


class BacktestEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def run(
        self,
        repo: Repository,
        *,
        strategy: str,
        route_id: str,
        pair: str,
        start_ts: datetime,
        end_ts: datetime,
        parameter_set_id: str | None,
        notes: str = "",
        replay_mode: str = "opportunities",
    ) -> dict[str, object]:
        params = await self._resolve_params(repo, strategy=strategy, parameter_set_id=parameter_set_id)
        mode = self._normalize_replay_mode(replay_mode)
        run_notes = notes.strip()
        run_notes = f"{run_notes} | replay_mode={mode}" if run_notes else f"replay_mode={mode}"
        run = await repo.create_backtest_run(
            strategy=strategy,
            route_id=route_id,
            pair=pair,
            start_ts=start_ts,
            end_ts=end_ts,
            parameter_set_id=parameter_set_id,
            notes=run_notes,
        )

        try:
            if mode == "market_snapshots":
                market_rows = await repo.list_market_snapshots_for_backtest(
                    strategy=strategy,
                    route_id=route_id,
                    pair=pair,
                    start_ts=start_ts,
                    end_ts=end_ts,
                )
                health_rows = await repo.list_route_health_snapshots_for_backtest(
                    route_id=route_id,
                    start_ts=start_ts,
                    end_ts=end_ts,
                )
                outcome = await self._evaluate_market_snapshot_rows(
                    repo,
                    run_id=run.id,
                    route_id=route_id,
                    rows=market_rows,
                    health_rows=health_rows,
                    params=params,
                )
            else:
                legacy_support_fallback = mode == "opportunities_legacy"
                rows = await repo.list_opportunities_for_backtest(
                    strategy=strategy,
                    route_id=route_id,
                    pair=pair,
                    start_ts=start_ts,
                    end_ts=end_ts,
                )
                outcome = await self._evaluate_opportunity_rows(
                    repo,
                    run_id=run.id,
                    route_id=route_id,
                    rows=rows,
                    params=params,
                    legacy_support_fallback=legacy_support_fallback,
                )

            metadata = {
                "parameter_set": params,
                "replay_mode": mode,
                "penalty_totals": outcome["penalty_totals"],
                "fee_confidence_distribution": outcome["fee_confidence_distribution"],
                "balance_confidence_distribution": outcome["balance_confidence_distribution"],
                "stale_unknown_health_event_count": outcome["stale_unknown_health_event_count"],
            }
            await repo.insert_backtest_result(
                backtest_run_id=run.id,
                signals=outcome["signals"],
                eligible_count=outcome["eligible_count"],
                blocked_count=outcome["blocked_count"],
                simulated_pnl=outcome["simulated_pnl"],
                hit_rate=outcome["hit_rate"],
                avg_modeled_edge_bps=outcome["avg_modeled_edge_bps"],
                avg_realized_like_pnl=outcome["avg_realized_like_pnl"],
                max_drawdown=outcome["max_drawdown"],
                worst_sequence=outcome["worst_sequence"],
                missed_opportunities=outcome["missed_opportunities"],
                blocked_reason_json=json.dumps(outcome["blocked_reasons"], sort_keys=True),
                metadata_json=json.dumps(metadata, sort_keys=True),
            )
            await repo.finish_backtest_run(run.id, "completed")
            return {"run_id": run.id, "status": "completed", "replay_mode": mode, **outcome}
        except Exception as exc:
            await repo.finish_backtest_run(run.id, "failed")
            return {"run_id": run.id, "status": "failed", "replay_mode": mode, "error": str(exc)}

    async def _resolve_params(
        self,
        repo: Repository,
        *,
        strategy: str,
        parameter_set_id: str | None,
    ) -> dict[str, object]:
        if parameter_set_id:
            row = await repo.get_parameter_set(parameter_set_id)
            if row is not None:
                with_params = self._safe_json(row.params_json)
                if with_params:
                    return with_params

        defaults = await repo.list_parameter_sets(strategy=strategy)
        for row in defaults:
            if row.is_default:
                with_params = self._safe_json(row.params_json)
                if with_params:
                    return with_params

        return {
            "min_modeled_edge_bps": self.settings.live_min_net_edge_bps,
            "max_slippage_bps": self.settings.live_max_slippage_bps,
            "max_quote_age_seconds": self.settings.global_stale_quote_stop_seconds,
            "gas_penalty_bps": self.settings.cost_failed_tx_allowance_bps,
            "quote_drift_buffer_bps": self.settings.cost_quote_drift_buffer_bps,
            "latency_penalty_bps": self.settings.cost_router_overhead_bps,
            "liquidity_cap_ratio": str(self.settings.live_max_notional_pct_of_smaller_pool),
            "min_fee_confidence_status": "fallback_only",
            "min_balance_confidence_status": "internal_ok",
            "fallback_fee_penalty_bps": 5,
            "unverified_fee_penalty_bps": 10,
            "unverified_balance_penalty_bps": 10,
            "default_gas_cost_usdc": "0.01",
        }

    async def _evaluate_opportunity_rows(
        self,
        repo: Repository,
        *,
        run_id: str,
        route_id: str,
        rows: list[Opportunity],
        params: dict[str, object],
        legacy_support_fallback: bool,
    ) -> dict[str, object]:
        signals = len(rows)
        eligible_count = 0
        blocked_count = 0
        blocked_reasons: dict[str, int] = {}

        min_edge = Decimal(str(params.get("min_modeled_edge_bps", 0)))
        max_slippage = Decimal(str(params.get("max_slippage_bps", 9999)))
        max_quote_age = Decimal(str(params.get("max_quote_age_seconds", 9999)))
        liquidity_cap_ratio = Decimal(str(params.get("liquidity_cap_ratio", "1")))

        cumulative = Decimal("0")
        peak = Decimal("0")
        max_drawdown = Decimal("0")
        worst_sequence = 0
        current_losing = 0
        positive_fills = 0
        modeled_edge_sum = Decimal("0")
        realized_like_sum = Decimal("0")
        missed = 0
        stale_unknown_health_events = 0
        fee_distribution: dict[str, int] = {}
        balance_distribution: dict[str, int] = {}
        penalty_totals: dict[str, Decimal] = {
            "gas": Decimal("0"),
            "quote_drift": Decimal("0"),
            "latency": Decimal("0"),
            "fallback_fee": Decimal("0"),
            "unverified_fee": Decimal("0"),
            "unverified_balance": Decimal("0"),
        }

        for row in rows:
            payload = self._safe_json(row.payload_json)
            blocked_reason, fee_status, balance_status, quote_unknown = self._recompute_blocked_reason(
                row=row,
                payload=payload,
                min_edge=min_edge,
                max_slippage=max_slippage,
                max_quote_age=max_quote_age,
                liquidity_cap_ratio=liquidity_cap_ratio,
                params=params,
                legacy_support_fallback=legacy_support_fallback,
            )
            fee_distribution[fee_status] = fee_distribution.get(fee_status, 0) + 1
            balance_distribution[balance_status] = balance_distribution.get(balance_status, 0) + 1
            if quote_unknown:
                stale_unknown_health_events += 1

            if blocked_reason:
                status = "blocked"
                simulated_pnl = Decimal("0")
                blocked_count += 1
                blocked_reasons[blocked_reason] = blocked_reasons.get(blocked_reason, 0) + 1
                if row.status == "eligible":
                    missed += 1
            else:
                status = "eligible"
                eligible_count += 1
                expected = Decimal(row.expected_pnl_abs)
                penalties = self._compute_penalties(
                    initial_amount=Decimal(str(payload.get("initial_amount", "0"))),
                    base_expected=expected,
                    fee_status=fee_status,
                    balance_status=balance_status,
                    params=params,
                )
                simulated_pnl = expected - penalties["total"] - Decimal(row.gas_estimate_usdc)
                penalty_totals["gas"] += penalties["gas"]
                penalty_totals["quote_drift"] += penalties["quote_drift"]
                penalty_totals["latency"] += penalties["latency"]
                penalty_totals["fallback_fee"] += penalties["fallback_fee"]
                penalty_totals["unverified_fee"] += penalties["unverified_fee"]
                penalty_totals["unverified_balance"] += penalties["unverified_balance"]
                if simulated_pnl > 0:
                    positive_fills += 1
                modeled_edge_sum += Decimal(row.modeled_edge_bps)
                realized_like_sum += simulated_pnl

                cumulative += simulated_pnl
                if cumulative > peak:
                    peak = cumulative
                drawdown = peak - cumulative
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                if simulated_pnl < 0:
                    current_losing += 1
                    if current_losing > worst_sequence:
                        worst_sequence = current_losing
                else:
                    current_losing = 0

            await repo.insert_backtest_trade(
                backtest_run_id=run_id,
                route_id=route_id,
                timestamp=row.timestamp,
                status=status,
                blocked_reason=blocked_reason,
                modeled_edge_bps=Decimal(row.modeled_edge_bps),
                expected_pnl=Decimal(row.expected_pnl_abs),
                simulated_pnl=simulated_pnl,
                metadata_json=json.dumps(payload, sort_keys=True),
            )

        return self._finalize_outcome(
            signals=signals,
            eligible_count=eligible_count,
            blocked_count=blocked_count,
            blocked_reasons=blocked_reasons,
            cumulative=cumulative,
            positive_fills=positive_fills,
            modeled_edge_sum=modeled_edge_sum,
            realized_like_sum=realized_like_sum,
            max_drawdown=max_drawdown,
            worst_sequence=worst_sequence,
            missed=missed,
            fee_distribution=fee_distribution,
            balance_distribution=balance_distribution,
            stale_unknown_health_events=stale_unknown_health_events,
            penalty_totals=penalty_totals,
        )

    async def _evaluate_market_snapshot_rows(
        self,
        repo: Repository,
        *,
        run_id: str,
        route_id: str,
        rows: list[MarketSnapshot],
        health_rows: list[RouteHealthSnapshot],
        params: dict[str, object],
    ) -> dict[str, object]:
        candidate_rows = [row for row in rows if row.context == "leg_b"]
        signals = len(candidate_rows)
        eligible_count = 0
        blocked_count = 0
        blocked_reasons: dict[str, int] = {}
        fee_distribution: dict[str, int] = {}
        balance_distribution: dict[str, int] = {}
        stale_unknown_health_events = 0
        penalty_totals: dict[str, Decimal] = {
            "gas": Decimal("0"),
            "quote_drift": Decimal("0"),
            "latency": Decimal("0"),
            "fallback_fee": Decimal("0"),
            "unverified_fee": Decimal("0"),
            "unverified_balance": Decimal("0"),
        }

        min_edge = Decimal(str(params.get("min_modeled_edge_bps", 0)))
        max_slippage = Decimal(str(params.get("max_slippage_bps", 9999)))
        max_quote_age = Decimal(str(params.get("max_quote_age_seconds", 9999)))
        liquidity_cap_ratio = Decimal(str(params.get("liquidity_cap_ratio", "1")))
        default_gas_cost = Decimal(str(params.get("default_gas_cost_usdc", "0.01")))
        default_slippage = Decimal(str(params.get("default_slippage_bps", "5")))

        cumulative = Decimal("0")
        peak = Decimal("0")
        max_drawdown = Decimal("0")
        worst_sequence = 0
        current_losing = 0
        positive_fills = 0
        modeled_edge_sum = Decimal("0")
        realized_like_sum = Decimal("0")
        missed = 0

        health_ptr = 0
        current_health: RouteHealthSnapshot | None = None
        ordered_health = sorted(health_rows, key=lambda x: x.timestamp)

        for row in candidate_rows:
            while health_ptr < len(ordered_health) and ordered_health[health_ptr].timestamp <= row.timestamp:
                current_health = ordered_health[health_ptr]
                health_ptr += 1

            payload = self._safe_json(row.metadata_json)
            initial_amount = Decimal(str(payload.get("initial_amount", row.amount_in)))
            final_amount = Decimal(str(payload.get("final_amount", row.quoted_amount_out)))
            if initial_amount <= 0:
                initial_amount = Decimal("0")
            expected_pnl = final_amount - initial_amount
            modeled_edge_bps = self._to_bps(expected_pnl, initial_amount)
            slippage_bps = Decimal(str(payload.get("expected_slippage_bps", default_slippage)))
            quote_age = Decimal(row.quote_age_seconds)
            smaller_liq = Decimal(str(payload.get("smaller_pool_liquidity_usdc", row.liquidity_usd)))
            fee_status = normalize_fee_confidence(
                payload.get("fee_known_status"),
                provenance_hint=payload.get("fee_provenance") or payload.get("fee_source"),
            )
            balance_status = normalize_balance_confidence(
                payload.get("balance_match_status"),
                evidence_hint=payload.get("balance_failure_reason"),
            )
            quote_match_status = normalize_quote_match_status(payload.get("quote_match_status"))
            quote_unavailable = str(payload.get("quote_unavailable", "false")).lower() == "true"
            balance_failure_reason = str(payload.get("balance_failure_reason", "")).strip().lower()
            support_status = normalize_support_status(payload.get("support_status"))

            if current_health is not None:
                if fee_status == "unknown":
                    fee_status = normalize_fee_confidence(current_health.fee_known_status)
                if balance_status == "unknown":
                    balance_status = normalize_balance_confidence(current_health.balance_match_status)
                if quote_match_status == "unknown":
                    quote_match_status = normalize_quote_match_status(current_health.quote_match_status)
                health_support = normalize_support_status(current_health.support_status)
                if health_support != "unknown" or support_status == "unknown":
                    support_status = health_support

            if quote_unavailable and support_status == "unknown":
                support_status = "unsupported"

            fee_distribution[fee_status] = fee_distribution.get(fee_status, 0) + 1
            balance_distribution[balance_status] = balance_distribution.get(balance_status, 0) + 1

            blocked_reason = ""
            if quote_unavailable or support_status == "unsupported":
                blocked_reason = "quote_unavailable"
            elif support_status == "unknown":
                blocked_reason = "health_unknown"
            elif fee_status == "unknown":
                blocked_reason = "fee_unknown"
            elif not fee_confidence_at_least(fee_status, str(params.get("min_fee_confidence_status", "fallback_only"))):
                blocked_reason = "fee_unverified"
            elif balance_status == "unknown":
                blocked_reason = "balance_unverified"
            elif balance_status == "mismatch":
                if balance_failure_reason == "wallet_balance_mismatch":
                    blocked_reason = "wallet_balance_mismatch"
                else:
                    blocked_reason = "inventory_drift"
            elif not balance_confidence_at_least(
                balance_status,
                str(params.get("min_balance_confidence_status", "internal_ok")),
            ):
                blocked_reason = "balance_unverified"
            elif quote_match_status == "unknown":
                blocked_reason = "health_unknown"
            elif quote_match_status != "matched":
                blocked_reason = "quote_mismatch"
            elif modeled_edge_bps < min_edge:
                blocked_reason = "below_threshold"
            elif slippage_bps > max_slippage:
                blocked_reason = "slippage_too_high"
            elif quote_age > max_quote_age:
                blocked_reason = "stale_quote"
            elif smaller_liq <= 0:
                blocked_reason = "liquidity_unavailable"
            elif initial_amount > 0 and initial_amount / smaller_liq > liquidity_cap_ratio:
                blocked_reason = "pool_share_too_large"

            if blocked_reason:
                stale_unknown_health_events += 1 if blocked_reason in {"health_unknown", "quote_unavailable"} else 0
                blocked_count += 1
                blocked_reasons[blocked_reason] = blocked_reasons.get(blocked_reason, 0) + 1
                simulated_pnl = Decimal("0")
                status = "blocked"
            else:
                eligible_count += 1
                penalties = self._compute_penalties(
                    initial_amount=initial_amount,
                    base_expected=expected_pnl,
                    fee_status=fee_status,
                    balance_status=balance_status,
                    params=params,
                )
                gas_cost_usdc = Decimal(str(payload.get("gas_cost_usdc", default_gas_cost)))
                simulated_pnl = expected_pnl - penalties["total"] - gas_cost_usdc
                penalty_totals["gas"] += penalties["gas"]
                penalty_totals["quote_drift"] += penalties["quote_drift"]
                penalty_totals["latency"] += penalties["latency"]
                penalty_totals["fallback_fee"] += penalties["fallback_fee"]
                penalty_totals["unverified_fee"] += penalties["unverified_fee"]
                penalty_totals["unverified_balance"] += penalties["unverified_balance"]
                status = "eligible"

                if simulated_pnl > 0:
                    positive_fills += 1
                modeled_edge_sum += modeled_edge_bps
                realized_like_sum += simulated_pnl
                cumulative += simulated_pnl
                if cumulative > peak:
                    peak = cumulative
                drawdown = peak - cumulative
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                if simulated_pnl < 0:
                    current_losing += 1
                    if current_losing > worst_sequence:
                        worst_sequence = current_losing
                else:
                    current_losing = 0

            trade_metadata = dict(payload)
            trade_metadata["replay_mode"] = "market_snapshots"
            await repo.insert_backtest_trade(
                backtest_run_id=run_id,
                route_id=route_id,
                timestamp=row.timestamp,
                status=status,
                blocked_reason=blocked_reason,
                modeled_edge_bps=modeled_edge_bps,
                expected_pnl=expected_pnl,
                simulated_pnl=simulated_pnl,
                metadata_json=json.dumps(trade_metadata, sort_keys=True),
            )

        return self._finalize_outcome(
            signals=signals,
            eligible_count=eligible_count,
            blocked_count=blocked_count,
            blocked_reasons=blocked_reasons,
            cumulative=cumulative,
            positive_fills=positive_fills,
            modeled_edge_sum=modeled_edge_sum,
            realized_like_sum=realized_like_sum,
            max_drawdown=max_drawdown,
            worst_sequence=worst_sequence,
            missed=missed,
            fee_distribution=fee_distribution,
            balance_distribution=balance_distribution,
            stale_unknown_health_events=stale_unknown_health_events,
            penalty_totals=penalty_totals,
        )

    @staticmethod
    def _safe_json(raw: str) -> dict[str, object]:
        try:
            value = json.loads(raw)
            if isinstance(value, dict):
                return value
        except Exception:
            return {}
        return {}

    @staticmethod
    def _normalize_replay_mode(raw: str) -> str:
        value = raw.strip().lower()
        if value in {"market_snapshots", "market-snapshots", "snapshot", "snapshots"}:
            return "market_snapshots"
        if value in {"opportunities_legacy", "opportunities-legacy", "legacy"}:
            return "opportunities_legacy"
        return "opportunities"

    @staticmethod
    def _to_bps(numerator: Decimal, denominator: Decimal) -> Decimal:
        if denominator <= 0:
            return Decimal("0")
        return (numerator / denominator) * Decimal("10000")

    def _recompute_blocked_reason(
        self,
        *,
        row: Opportunity,
        payload: dict[str, object],
        min_edge: Decimal,
        max_slippage: Decimal,
        max_quote_age: Decimal,
        liquidity_cap_ratio: Decimal,
        params: dict[str, object],
        legacy_support_fallback: bool,
    ) -> tuple[str, str, str, bool]:
        fee_status = normalize_fee_confidence(
            payload.get("fee_known_status"),
            provenance_hint=payload.get("fee_provenance") or payload.get("fee_source"),
        )
        if fee_status == "unknown":
            fee_known_raw = str(payload.get("fee_known", "unknown")).lower()
            if fee_known_raw == "true":
                fee_status = "config_only"
            elif fee_known_raw == "false":
                fee_status = "unknown"
        balance_status = normalize_balance_confidence(
            payload.get("balance_match_status"),
            evidence_hint=payload.get("balance_failure_reason"),
        )
        quote_match_status = normalize_quote_match_status(payload.get("quote_match_status"))
        support_status = normalize_support_status(payload.get("support_status"))
        if quote_match_status == "unknown":
            quote_match_status = normalize_quote_match_status(payload.get("quote_match"))
        quote_unavailable = str(payload.get("quote_unavailable", "false")).lower() == "true"
        if legacy_support_fallback and support_status == "unknown" and not quote_unavailable:
            # Opportunities replay is legacy-friendly; quote_unavailable=false historically implied supported route.
            support_status = "supported"
        if quote_unavailable or support_status == "unsupported":
            return "quote_unavailable", fee_status, balance_status, True
        if support_status == "unknown":
            return "health_unknown", fee_status, balance_status, True
        if fee_status == "unknown":
            return "fee_unknown", fee_status, balance_status, True
        if not fee_confidence_at_least(fee_status, str(params.get("min_fee_confidence_status", "fallback_only"))):
            return "fee_unverified", fee_status, balance_status, False
        if quote_match_status == "unknown":
            return "health_unknown", fee_status, balance_status, True
        if quote_match_status != "matched":
            return "quote_mismatch", fee_status, balance_status, False
        if balance_status == "unknown":
            return "balance_unverified", fee_status, balance_status, True
        if balance_status == "mismatch":
            failure_reason = str(payload.get("balance_failure_reason", "")).strip().lower()
            if failure_reason == "wallet_balance_mismatch":
                return "wallet_balance_mismatch", fee_status, balance_status, False
            return "inventory_drift", fee_status, balance_status, False
        if not balance_confidence_at_least(
            balance_status,
            str(params.get("min_balance_confidence_status", "internal_ok")),
        ):
            return "balance_unverified", fee_status, balance_status, False
        if Decimal(row.modeled_edge_bps) < min_edge:
            return "below_threshold", fee_status, balance_status, False
        if Decimal(row.expected_slippage_bps) > max_slippage:
            return "slippage_too_high", fee_status, balance_status, False
        if Decimal(row.quote_age_seconds) > max_quote_age:
            return "stale_quote", fee_status, balance_status, False

        amount_in = Decimal(str(payload.get("initial_amount", "0")))
        if amount_in <= 0:
            return "health_unknown", fee_status, balance_status, True
        liq = Decimal(str(payload.get("smaller_pool_liquidity_usdc", "0")))
        if liq <= 0:
            return "liquidity_unavailable", fee_status, balance_status, False
        if amount_in / liq > liquidity_cap_ratio:
            return "pool_share_too_large", fee_status, balance_status, False
        return "", fee_status, balance_status, False

    def _compute_penalties(
        self,
        *,
        initial_amount: Decimal,
        base_expected: Decimal,
        fee_status: str,
        balance_status: str,
        params: dict[str, object],
    ) -> dict[str, Decimal]:
        base_amount = max(abs(initial_amount), abs(base_expected), Decimal("0"))
        gas_penalty = base_amount * Decimal(str(params.get("gas_penalty_bps", 0))) / Decimal("10000")
        quote_drift = base_amount * Decimal(str(params.get("quote_drift_buffer_bps", 0))) / Decimal("10000")
        latency = base_amount * Decimal(str(params.get("latency_penalty_bps", 0))) / Decimal("10000")
        fallback_fee = Decimal("0")
        if fee_status == "fallback_only":
            fallback_fee = base_amount * Decimal(str(params.get("fallback_fee_penalty_bps", 0))) / Decimal("10000")
        unverified_fee = Decimal("0")
        if fee_status in {"fallback_only", "config_only"}:
            unverified_fee = base_amount * Decimal(str(params.get("unverified_fee_penalty_bps", 0))) / Decimal("10000")
        unverified_balance = Decimal("0")
        if balance_status in {"unknown", "internal_ok", "db_inventory_ok"}:
            unverified_balance = base_amount * Decimal(str(params.get("unverified_balance_penalty_bps", 0))) / Decimal("10000")
        total = gas_penalty + quote_drift + latency + fallback_fee + unverified_fee + unverified_balance
        return {
            "gas": gas_penalty,
            "quote_drift": quote_drift,
            "latency": latency,
            "fallback_fee": fallback_fee,
            "unverified_fee": unverified_fee,
            "unverified_balance": unverified_balance,
            "total": total,
        }

    @staticmethod
    def _finalize_outcome(
        *,
        signals: int,
        eligible_count: int,
        blocked_count: int,
        blocked_reasons: dict[str, int],
        cumulative: Decimal,
        positive_fills: int,
        modeled_edge_sum: Decimal,
        realized_like_sum: Decimal,
        max_drawdown: Decimal,
        worst_sequence: int,
        missed: int,
        fee_distribution: dict[str, int],
        balance_distribution: dict[str, int],
        stale_unknown_health_events: int,
        penalty_totals: dict[str, Decimal],
    ) -> dict[str, object]:
        hit_rate = Decimal("0")
        avg_edge = Decimal("0")
        avg_realized_like = Decimal("0")
        if eligible_count > 0:
            hit_rate = Decimal(positive_fills) / Decimal(eligible_count)
            avg_edge = modeled_edge_sum / Decimal(eligible_count)
            avg_realized_like = realized_like_sum / Decimal(eligible_count)

        return {
            "signals": signals,
            "eligible_count": eligible_count,
            "blocked_count": blocked_count,
            "blocked_reasons": blocked_reasons,
            "simulated_pnl": cumulative,
            "hit_rate": hit_rate,
            "avg_modeled_edge_bps": avg_edge,
            "avg_realized_like_pnl": avg_realized_like,
            "max_drawdown": max_drawdown,
            "worst_sequence": worst_sequence,
            "missed_opportunities": missed,
            "fee_confidence_distribution": fee_distribution,
            "balance_confidence_distribution": balance_distribution,
            "stale_unknown_health_event_count": stale_unknown_health_events,
            "penalty_totals": {k: str(v) for k, v in penalty_totals.items()},
        }
