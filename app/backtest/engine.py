from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from app.config.settings import Settings
from app.db.repository import Repository
from app.models.core import Opportunity


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
    ) -> dict[str, object]:
        params = await self._resolve_params(repo, strategy=strategy, parameter_set_id=parameter_set_id)
        run = await repo.create_backtest_run(
            strategy=strategy,
            route_id=route_id,
            pair=pair,
            start_ts=start_ts,
            end_ts=end_ts,
            parameter_set_id=parameter_set_id,
            notes=notes,
        )

        try:
            rows = await repo.list_opportunities_for_backtest(
                strategy=strategy,
                route_id=route_id,
                pair=pair,
                start_ts=start_ts,
                end_ts=end_ts,
            )
            outcome = await self._evaluate_rows(repo, run_id=run.id, route_id=route_id, rows=rows, params=params)
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
                metadata_json=json.dumps({"parameter_set": params}, sort_keys=True),
            )
            await repo.finish_backtest_run(run.id, "completed")
            return {"run_id": run.id, "status": "completed", **outcome}
        except Exception as exc:
            await repo.finish_backtest_run(run.id, "failed")
            return {"run_id": run.id, "status": "failed", "error": str(exc)}

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
        }

    async def _evaluate_rows(
        self,
        repo: Repository,
        *,
        run_id: str,
        route_id: str,
        rows: list[Opportunity],
        params: dict[str, object],
    ) -> dict[str, object]:
        signals = len(rows)
        eligible_count = 0
        blocked_count = 0
        blocked_reasons: dict[str, int] = {}

        min_edge = Decimal(str(params.get("min_modeled_edge_bps", 0)))
        max_slippage = Decimal(str(params.get("max_slippage_bps", 9999)))
        max_quote_age = Decimal(str(params.get("max_quote_age_seconds", 9999)))
        gas_penalty_bps = Decimal(str(params.get("gas_penalty_bps", 0)))
        quote_drift_bps = Decimal(str(params.get("quote_drift_buffer_bps", 0)))
        latency_penalty_bps = Decimal(str(params.get("latency_penalty_bps", 0)))
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

        for row in rows:
            payload = self._safe_json(row.payload_json)
            blocked_reason = self._recompute_blocked_reason(
                row=row,
                payload=payload,
                min_edge=min_edge,
                max_slippage=max_slippage,
                max_quote_age=max_quote_age,
                liquidity_cap_ratio=liquidity_cap_ratio,
            )

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
                penalty_bps = gas_penalty_bps + quote_drift_bps + latency_penalty_bps
                penalty = Decimal(row.expected_pnl_abs) * penalty_bps / Decimal("10000")
                simulated_pnl = expected - penalty - Decimal(row.gas_estimate_usdc)
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
        }

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
    def _recompute_blocked_reason(
        *,
        row: Opportunity,
        payload: dict[str, object],
        min_edge: Decimal,
        max_slippage: Decimal,
        max_quote_age: Decimal,
        liquidity_cap_ratio: Decimal,
    ) -> str:
        if str(payload.get("quote_unavailable", "false")).lower() == "true":
            return "quote_unavailable"
        if str(payload.get("fee_known", "unknown")).lower() != "true":
            return "fee_unknown"
        if str(payload.get("quote_match", "unknown")).lower() != "true":
            return "quote_mismatch"
        if Decimal(row.modeled_edge_bps) < min_edge:
            return "below_threshold"
        if Decimal(row.expected_slippage_bps) > max_slippage:
            return "slippage_too_high"
        if Decimal(row.quote_age_seconds) > max_quote_age:
            return "stale_quote"

        amount_in = Decimal(str(payload.get("initial_amount", "0")))
        if amount_in <= 0:
            return "health_unknown"
        liq = Decimal(str(payload.get("smaller_pool_liquidity_usdc", "0")))
        if liq <= 0:
            return "liquidity_unavailable"
        if amount_in / liq > liquidity_cap_ratio:
            return "pool_share_too_large"
        return ""
