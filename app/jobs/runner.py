from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import suppress
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.alerts.service import AlertService
from app.config.settings import RunMode, Settings
from app.db.repository import Repository
from app.execution.live import LiveDryRunExecutionEngine
from app.execution.paper import PaperExecutionEngine
from app.health.collector import HealthCollector
from app.models.core import Route
from app.quote_engine.engine import HyperDexDexQuoteEngine, ShadowCexDexQuoteEngine
from app.quote_engine.types import RouteQuote
from app.risk.manager import FATAL_FAILURE_CATEGORIES, GlobalRiskManager, HealthSnapshot
from app.utils.logging import enrich_log_kwargs
from app.utils.metrics import metrics_store

logger = logging.getLogger(__name__)


class BotRunner:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker,
        alert_service: AlertService,
        risk_manager: GlobalRiskManager,
        hyper_engine: HyperDexDexQuoteEngine,
        shadow_engine: ShadowCexDexQuoteEngine,
        paper_engine: PaperExecutionEngine,
        live_engine: LiveDryRunExecutionEngine,
        health_collector: HealthCollector,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.alert_service = alert_service
        self.risk_manager = risk_manager
        self.hyper_engine = hyper_engine
        self.shadow_engine = shadow_engine
        self.paper_engine = paper_engine
        self.live_engine = live_engine
        self.health_collector = health_collector
        self._tasks: list[asyncio.Task] = []
        self._stop_event = asyncio.Event()
        self.last_heartbeat: datetime = datetime.now(timezone.utc)

    async def start(self) -> None:
        self._stop_event.clear()
        self._tasks = [
            asyncio.create_task(self._scan_loop(), name="scan_loop"),
            asyncio.create_task(self._health_loop(), name="health_loop"),
        ]
        async with self.session_factory() as session:
            repo = Repository(session)
            runtime_states = await repo.list_route_runtime_states()
            for row in runtime_states:
                self.risk_manager.hydrate_route_state(
                    route_id=row.route_id,
                    paused=row.paused,
                    cooldown_until=row.cooldown_until,
                    last_failure_category=row.last_failure_category,
                    last_failure_reason=row.last_failure_reason,
                    last_failure_fatal=row.last_failure_fatal,
                    last_failure_at=row.last_failure_at,
                    consecutive_failures=row.consecutive_failures,
                    consecutive_losses=row.consecutive_losses,
                )
            sent = await self.alert_service.send(session, "INFO", "startup", "bot runner started")
            self.health_collector.record_alert_result(sent)

    async def stop(self) -> None:
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        try:
            async with self.session_factory() as session:
                sent = await self.alert_service.send(session, "INFO", "shutdown", "bot runner stopped")
                self.health_collector.record_alert_result(sent)
        except Exception:
            logger.exception("runner_shutdown_alert_failed", **enrich_log_kwargs(action="shutdown_alert_error"))

    async def _scan_loop(self) -> None:
        while not self._stop_event.is_set():
            loop_start = time.perf_counter()
            self.last_heartbeat = datetime.now(timezone.utc)
            self.health_collector.set_heartbeat(self.last_heartbeat)

            try:
                async with self.session_factory() as session:
                    repo = Repository(session)
                    ctrl = await repo.get_runtime_control()
                    current_mode = RunMode(ctrl.mode)
                    self.risk_manager.set_global_kill(ctrl.global_pause)

                    routes = await repo.get_routes(enabled_only=True)
                    wallet_balance = await repo.get_wallet_usdc_balance()

                    if self.risk_manager.should_stop_for_daily_dd(wallet_balance):
                        self.risk_manager.set_global_kill(True)
                        await repo.set_global_pause(True)
                        await repo.write_kill_switch_event("global", "global", "trigger", "daily_dd_stop")
                        sent = await self.alert_service.send(
                            session,
                            "WARN",
                            "daily_dd_stop",
                            "daily drawdown threshold reached; new entries stopped",
                        )
                        self.health_collector.record_alert_result(sent)

                    for route in routes:
                        strategy_mode = current_mode if route.strategy == "hyperevm_dex_dex" else RunMode.PAPER
                        stale_limit = (
                            self.settings.global_stale_quote_stop_seconds
                            if route.strategy == "hyperevm_dex_dex"
                            else self.settings.shadow_stale_quote_seconds
                        )

                        quote: RouteQuote
                        quote_start = time.perf_counter()
                        try:
                            if route.strategy == "hyperevm_dex_dex":
                                amount = min(route.max_notional_usdc, self.settings.live_max_notional_usdc)
                                quote = await self.hyper_engine.quote_route(route, amount, mode_profile=strategy_mode)
                            elif route.strategy == "base_virtual_shadow":
                                quote = await self.shadow_engine.quote_route(route, self.settings.shadow_notional_usdc)
                            else:
                                continue

                            q_latency_ms = Decimal(str((time.perf_counter() - quote_start) * 1000))
                            self.health_collector.record_quote_probe(
                                venue=route.venue_a,
                                latency_ms=q_latency_ms,
                                quote_age_seconds=quote.quote_age_seconds,
                                ok=True,
                                quote_unavailable=False,
                            )
                            self.health_collector.record_quote_probe(
                                venue=route.venue_b,
                                latency_ms=q_latency_ms,
                                quote_age_seconds=quote.quote_age_seconds,
                                ok=True,
                                quote_unavailable=False,
                            )
                            liq = Decimal(quote.metadata.get("smaller_pool_liquidity_usdc", "0"))
                            self.health_collector.record_liquidity(route.id, liq)

                        except Exception as quote_exc:
                            quote = self._build_unavailable_quote(route, strategy_mode, str(quote_exc))
                            q_latency_ms = Decimal(str((time.perf_counter() - quote_start) * 1000))
                            self.health_collector.record_quote_probe(
                                venue=route.venue_a,
                                latency_ms=q_latency_ms,
                                quote_age_seconds=quote.quote_age_seconds,
                                ok=False,
                                quote_unavailable=True,
                            )
                            self.health_collector.record_quote_probe(
                                venue=route.venue_b,
                                latency_ms=q_latency_ms,
                                quote_age_seconds=quote.quote_age_seconds,
                                ok=False,
                                quote_unavailable=True,
                            )

                        fee_known = self._parse_tristate_bool(quote.metadata.get("fee_known"))
                        quote_match = self._parse_tristate_bool(quote.metadata.get("quote_match"))
                        balance_match = await self._probe_balance_match(repo)
                        signing_ok = self._probe_signing_ok(route)
                        self.health_collector.set_quality_status(
                            signing_ok=signing_ok,
                            fee_known=fee_known,
                            quote_match=quote_match,
                            balance_match=balance_match,
                        )

                        health = self.health_collector.to_risk_snapshot(route.id)
                        smaller_pool = Decimal(quote.metadata.get("smaller_pool_liquidity_usdc", "0"))

                        decision = self.risk_manager.evaluate(
                            quote=quote,
                            mode=strategy_mode,
                            quote_freshness_limit=stale_limit,
                            health=health,
                            wallet_balance_usdc=wallet_balance,
                            reference_deviation_bps=quote.raw_edge_bps,
                            depeg_detected=False,
                            smaller_pool_liquidity_usdc=smaller_pool,
                        )
                        quote.metadata["risk_checks"] = ",".join(
                            [f"{k}:{'1' if v else '0'}" for k, v in sorted(decision.checks.items())]
                        )

                        status = "eligible" if decision.tradable else "blocked"
                        opp = await repo.insert_opportunity(
                            quote,
                            mode=strategy_mode.value,
                            status=status,
                            blocked_reason=decision.blocked_reason,
                        )
                        await self._write_market_observations(repo, route, quote)
                        await self._write_route_health_snapshot(
                            repo=repo,
                            route=route,
                            strategy_mode=strategy_mode,
                            health=health,
                            quote=quote,
                        )

                        if not decision.tradable:
                            if decision.blocked_reason in FATAL_FAILURE_CATEGORIES:
                                self.risk_manager.mark_failure(
                                    route.id,
                                    category=decision.blocked_reason,
                                    reason=f"opportunity blocked: {decision.blocked_reason}",
                                )
                                await self._persist_route_runtime_state(repo, route.id)
                            logger.info(
                                "opportunity_blocked",
                                **enrich_log_kwargs(
                                    strategy=route.strategy,
                                    pair=route.pair,
                                    route=route.id,
                                    mode=strategy_mode.value,
                                    action="blocked",
                                    opportunity_id=opp.id,
                                ),
                            )
                            continue

                        if strategy_mode == RunMode.STOPPED:
                            continue

                        attempt = await repo.insert_trade_attempt(
                            opportunity_id=opp.id,
                            route_id=route.id,
                            strategy=route.strategy,
                            mode=strategy_mode.value,
                            input_amount=quote.initial_amount,
                            expected_output_amount=quote.final_amount,
                            expected_pnl=quote.modeled_net_edge_amount,
                            status="submitted",
                            failure_category="",
                            is_fatal_failure=False,
                            cooldown_triggered=False,
                        )

                        failure_category = ""
                        execution_result: dict[str, str | bool]
                        if strategy_mode == RunMode.PAPER:
                            execution_result = await self.paper_engine.execute(quote)
                            realized = Decimal(str(execution_result.get("realized_pnl", "0")))
                            tx_status = "success" if bool(execution_result.get("ok")) else "failed"
                            tx_hash = str(execution_result.get("tx_hash", "paper"))
                            if tx_status == "failed":
                                failure_category = "revert"
                        else:
                            execution_result = await self.live_engine.dry_run(quote)
                            if bool(execution_result.get("ok")):
                                tx_status = "dry_run"
                                failure_category = ""
                            else:
                                tx_status = "dry_run_blocked"
                                failure_category = str(execution_result.get("blocked_reason", "scan_fatal"))
                            tx_hash = "live-dry-run"
                            realized = Decimal("0")

                        category = failure_category or ""
                        is_failed = tx_status in {"failed", "reverted", "dry_run_blocked"}
                        if is_failed:
                            category = category or "scan_fatal"
                            self.risk_manager.mark_failure(
                                route.id,
                                category=category,
                                reason=f"tx_status={tx_status}",
                            )
                            await self._persist_route_runtime_state(repo, route.id)
                        else:
                            self.risk_manager.mark_success(route.id, realized)
                            await self._persist_route_runtime_state(repo, route.id)

                        cooldown_triggered = self.risk_manager.cooldown_remaining_seconds(route.id) > 0
                        fatal_failure = category in FATAL_FAILURE_CATEGORIES if category else False
                        attempt_status = tx_status

                        await repo.update_trade_attempt_outcome(
                            attempt_id=attempt.id,
                            status=attempt_status,
                            blocked_reason=category if is_failed else "",
                            failure_category=category if is_failed else "",
                            is_fatal_failure=fatal_failure if is_failed else False,
                            cooldown_triggered=cooldown_triggered if is_failed else False,
                            notes=f"result={execution_result}",
                        )

                        await repo.insert_execution(
                            attempt_id=attempt.id,
                            route_id=route.id,
                            strategy=route.strategy,
                            mode=strategy_mode.value,
                            tx_status=tx_status,
                            tx_hash=tx_hash,
                            input_amount=quote.initial_amount,
                            output_amount=quote.final_amount,
                            expected_pnl=quote.modeled_net_edge_amount,
                            realized_pnl=realized,
                            failure_category=category,
                            is_fatal_failure=fatal_failure,
                            cooldown_triggered=cooldown_triggered,
                            notes=f"failure_category={category};result={execution_result}",
                        )
                        self.health_collector.record_execution_result(tx_status)

                        if is_failed:
                            sent = await self.alert_service.send(
                                session,
                                "ERROR",
                                "trade_reverted",
                                f"route={route.name} tx_status={tx_status} category={category}",
                            )
                            self.health_collector.record_alert_result(sent)
                        else:
                            sent = await self.alert_service.send(
                                session,
                                "INFO",
                                "trade_executed",
                                f"route={route.name} tx_status={tx_status}",
                            )
                            self.health_collector.record_alert_result(sent)

            except Exception as exc:
                logger.exception("scan_loop_failed", **enrich_log_kwargs(action="scan_loop_error"))
                async with self.session_factory() as session:
                    sent = await self.alert_service.send(session, "ERROR", "scan_loop", f"scan loop failure: {exc}")
                    self.health_collector.record_alert_result(sent)

            elapsed = time.perf_counter() - loop_start
            sleep_for = max(0.1, self.settings.quote_poll_interval_seconds - elapsed)
            await asyncio.sleep(sleep_for)

    async def _health_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                async with self.session_factory() as session:
                    repo = Repository(session)

                    rpc_latency_hyper, rpc_ok_hyper = await self._probe_rpc(self.settings.hyperevm_rpc_url)
                    rpc_latency_base, rpc_ok_base = await self._probe_rpc(self.settings.base_rpc_url)
                    combined_rpc_latency = (
                        (rpc_latency_hyper + rpc_latency_base) / Decimal("2")
                        if rpc_ok_hyper and rpc_ok_base
                        else (rpc_latency_hyper if rpc_ok_hyper else rpc_latency_base)
                    )
                    self.health_collector.record_rpc_probe(combined_rpc_latency, rpc_ok_hyper and rpc_ok_base)

                    try:
                        db_latency = await self._probe_db_latency(session)
                        self.health_collector.record_db_latency(db_latency, ok=True)
                    except Exception:
                        db_latency = Decimal("0")
                        self.health_collector.record_db_latency(db_latency, ok=False)

                    gas_gwei = await self._probe_gas_gwei(self.settings.hyperevm_rpc_url)
                    self.health_collector.record_gas(gas_gwei)

                    global_snapshot = self.health_collector.build_snapshot("global")
                    metrics_store.record("rpc_latency_ms", global_snapshot.rpc_latency_ms)
                    metrics_store.record("rpc_error_rate", global_snapshot.rpc_error_rate_5m)
                    metrics_store.record("db_latency_ms", global_snapshot.db_latency_ms)
                    metrics_store.record("quote_latency_ms", global_snapshot.quote_latency_ms)
                    metrics_store.record("gas_now", global_snapshot.gas_now)
                    metrics_store.record("gas_p50", global_snapshot.gas_p50)
                    metrics_store.record("gas_p90", global_snapshot.gas_p90)
                    metrics_store.record("liquidity_change_pct", global_snapshot.liquidity_change_pct)
                    metrics_store.record("quote_age_seconds", global_snapshot.quote_age_seconds)
                    metrics_store.record("alert_send_success_rate", global_snapshot.alert_send_success_rate)
                    metrics_store.record("contract_revert_rate", global_snapshot.contract_revert_rate)
                    metrics_store.record("market_data_staleness_seconds", global_snapshot.market_data_staleness_seconds)
                    metrics_store.record("heartbeat_lag_seconds", global_snapshot.heartbeat_lag_seconds)
                    metrics_store.record("quote_unavailable_count", Decimal(len(global_snapshot.quote_unavailable_venues)))

                    await repo.write_health_metric("rpc_latency_ms", global_snapshot.rpc_latency_ms)
                    await repo.write_health_metric("rpc_error_rate", global_snapshot.rpc_error_rate_5m)
                    await repo.write_health_metric("db_latency_ms", global_snapshot.db_latency_ms)
                    await repo.write_health_metric("quote_latency_ms", global_snapshot.quote_latency_ms)
                    await repo.write_health_metric("gas_now", global_snapshot.gas_now)
                    await repo.write_health_metric("gas_p50", global_snapshot.gas_p50)
                    await repo.write_health_metric("gas_p90", global_snapshot.gas_p90)
                    await repo.write_health_metric("liquidity_change_pct", global_snapshot.liquidity_change_pct)
                    await repo.write_health_metric("quote_age_seconds", global_snapshot.quote_age_seconds)
                    await repo.write_health_metric("alert_send_success_rate", global_snapshot.alert_send_success_rate)
                    await repo.write_health_metric("contract_revert_rate", global_snapshot.contract_revert_rate)
                    await repo.write_health_metric("market_data_staleness_seconds", global_snapshot.market_data_staleness_seconds)
                    await repo.write_health_metric("heartbeat_lag_seconds", global_snapshot.heartbeat_lag_seconds)
                    await repo.write_health_metric("quote_unavailable_count", Decimal(len(global_snapshot.quote_unavailable_venues)))
            except Exception:
                logger.exception("health_loop_failed", **enrich_log_kwargs(action="health_loop_error"))

            await asyncio.sleep(self.settings.health_poll_interval_seconds)

    async def _probe_rpc(self, rpc_url: str) -> tuple[Decimal, bool]:
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_blockNumber",
            "params": [],
            "id": 1,
        }
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.post(rpc_url, json=payload)
                response.raise_for_status()
                data = response.json()
            ok = data.get("result") is not None and data.get("error") is None
            latency = Decimal(str((time.perf_counter() - start) * 1000))
            return latency, ok
        except Exception:
            latency = Decimal(str((time.perf_counter() - start) * 1000))
            return latency, False

    async def _probe_gas_gwei(self, rpc_url: str) -> Decimal:
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_gasPrice",
            "params": [],
            "id": 2,
        }
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.post(rpc_url, json=payload)
                response.raise_for_status()
                data = response.json()
            result = data.get("result")
            if not result:
                return Decimal("0")
            wei = int(result, 16)
            return (Decimal(wei) / Decimal("1000000000")).quantize(Decimal("0.000001"))
        except Exception:
            return Decimal("0")

    async def _probe_db_latency(self, session: AsyncSession) -> Decimal:
        start = time.perf_counter()
        await session.execute(text("SELECT 1"))
        return Decimal(str((time.perf_counter() - start) * 1000))

    async def _probe_balance_match(self, repo: Repository) -> bool | None:
        try:
            balances = await repo.list_balances()
            if not balances:
                return None
            for bal in balances:
                if bal.available < 0 or bal.reserved < 0 or bal.total < 0:
                    return False
                if bal.available + bal.reserved > bal.total:
                    return False
            return True
        except Exception:
            return None

    async def _persist_route_runtime_state(self, repo: Repository, route_id: str) -> None:
        state = self.risk_manager.get_route_state(route_id)
        cooldown_until = None
        last_failure_at = None
        cooldown_until_raw = str(state.get("cooldown_until", ""))
        if cooldown_until_raw:
            with suppress(ValueError):
                cooldown_until = datetime.fromisoformat(cooldown_until_raw)
        last_failure_raw = str(state.get("last_failure_at", ""))
        if last_failure_raw:
            with suppress(ValueError):
                last_failure_at = datetime.fromisoformat(last_failure_raw)
        await repo.upsert_route_runtime_state(
            route_id=route_id,
            paused=bool(state.get("route_paused", False)),
            cooldown_until=cooldown_until,
            last_failure_category=str(state.get("last_failure_category", "")),
            last_failure_reason=str(state.get("last_failure_reason", "")),
            last_failure_fatal=bool(state.get("last_failure_fatal", False)),
            last_failure_at=last_failure_at,
            consecutive_failures=int(state.get("consecutive_failures", 0)),
            consecutive_losses=int(state.get("consecutive_losses", 0)),
        )

    async def _write_market_observations(self, repo: Repository, route: Route, quote: RouteQuote) -> None:
        source_type = quote.metadata.get("quote_source", "mock")
        gas_gwei = metrics_store.latest("gas_now") or Decimal("0")
        metadata = json.dumps(quote.metadata, sort_keys=True)
        liq = Decimal(quote.metadata.get("smaller_pool_liquidity_usdc", "0"))
        leg1_out = Decimal(quote.metadata.get("leg1_amount_out", "0"))
        leg2_out = Decimal(quote.metadata.get("leg2_amount_out", "0"))
        cex_bid = Decimal(quote.metadata.get("cex_bid", "0"))
        cex_ask = Decimal(quote.metadata.get("cex_ask", "0"))

        await repo.insert_market_snapshot(
            strategy=route.strategy,
            route_id=route.id,
            pair=route.pair,
            venue=route.venue_a,
            context="leg_a",
            bid=cex_bid,
            ask=cex_ask,
            amount_in=quote.initial_amount,
            quoted_amount_out=leg1_out if leg1_out > 0 else quote.final_amount,
            liquidity_usd=liq,
            gas_gwei=gas_gwei,
            quote_age_seconds=quote.quote_age_seconds,
            source_type=source_type,
            metadata_json=metadata,
        )

        await repo.insert_market_snapshot(
            strategy=route.strategy,
            route_id=route.id,
            pair=route.pair,
            venue=route.venue_b,
            context="leg_b",
            bid=cex_bid,
            ask=cex_ask,
            amount_in=leg1_out if leg1_out > 0 else quote.initial_amount,
            quoted_amount_out=leg2_out if leg2_out > 0 else quote.final_amount,
            liquidity_usd=liq,
            gas_gwei=gas_gwei,
            quote_age_seconds=quote.quote_age_seconds,
            source_type=source_type,
            metadata_json=metadata,
        )

    async def _write_route_health_snapshot(
        self,
        repo: Repository,
        route: Route,
        strategy_mode: RunMode,
        health: HealthSnapshot,
        quote: RouteQuote,
    ) -> None:
        route_state = self.risk_manager.get_route_state(route.id)
        fee_known_raw = quote.metadata.get("fee_known", "unknown").lower()
        if fee_known_raw == "true":
            fee_status = "good"
        elif fee_known_raw == "false":
            fee_status = "bad"
        else:
            fee_status = "unknown"
        quote_match_raw = quote.metadata.get("quote_match")
        if quote_match_raw == "true":
            quote_match_status = "good"
        elif quote_match_raw == "false":
            quote_match_status = "bad"
        else:
            quote_match_status = "unknown"
        if health.balance_match_known:
            balance_match_status = "good" if health.balance_match else "bad"
        else:
            balance_match_status = "unknown"
        quote_unavailable_raw = quote.metadata.get("quote_unavailable", "false").lower()
        support_status = "bad" if quote_unavailable_raw == "true" else "good"
        await repo.insert_route_health_snapshot(
            strategy=route.strategy,
            route_id=route.id,
            pair=route.pair,
            rpc_latency_ms=metrics_store.latest("rpc_latency_ms") or Decimal("0"),
            rpc_error_rate_5m=health.rpc_error_rate_5m,
            db_latency_ms=metrics_store.latest("db_latency_ms") or Decimal("0"),
            quote_latency_ms=metrics_store.latest("quote_latency_ms") or Decimal("0"),
            market_data_staleness_seconds=metrics_store.latest("market_data_staleness_seconds") or Decimal("0"),
            contract_revert_rate=health.contract_revert_rate,
            alert_send_success_rate=metrics_store.latest("alert_send_success_rate") or Decimal("0"),
            fee_known_status=fee_status,
            quote_match_status=quote_match_status,
            balance_match_status=balance_match_status,
            support_status=support_status,
            cooldown_active=bool(int(route_state.get("cooldown_remaining_seconds", 0)) > 0),
            paused=bool(route_state.get("route_paused", False)),
            metadata_json=json.dumps(
                {
                    "strategy_mode": strategy_mode.value,
                    "blocked_reason": quote.blocked_reason,
                }
            ),
        )

    @staticmethod
    def _parse_tristate_bool(raw: str | None) -> bool | None:
        if raw is None:
            return None
        value = raw.strip().lower()
        if value in {"true", "1", "yes"}:
            return True
        if value in {"false", "0", "no"}:
            return False
        return None

    def _build_unavailable_quote(self, route: Route, strategy_mode: RunMode, reason: str) -> RouteQuote:
        return RouteQuote(
            route_id=route.id,
            strategy=route.strategy,
            pair=route.pair,
            direction=route.direction,
            initial_amount=Decimal("0"),
            final_amount=Decimal("0"),
            raw_spread_amount=Decimal("0"),
            raw_edge_bps=Decimal("0"),
            modeled_net_edge_amount=Decimal("0"),
            modeled_net_edge_bps=Decimal("0"),
            expected_slippage_bps=Decimal("0"),
            gas_cost_usdc=Decimal("0"),
            quote_age_seconds=Decimal("999"),
            all_costs=Decimal("0"),
            persisted_seconds=Decimal("0"),
            status="blocked",
            blocked_reason="quote_unavailable",
            metadata={
                "pool_health": "false",
                "quote_unavailable": "true",
                "quote_unavailable_reason": reason,
                "fee_known": "unknown",
                "quote_match": "unknown",
                "smaller_pool_liquidity_usdc": "0",
                "venues": f"{route.venue_a}->{route.venue_b}",
                "mode_profile": strategy_mode.value,
            },
        )

    def _probe_signing_ok(self, route: Route) -> bool | None:
        if route.strategy != "hyperevm_dex_dex":
            return True
        client = self.live_engine.arb_client
        if client is None:
            return None
        try:
            return client.validate_chain()
        except Exception:
            return False
