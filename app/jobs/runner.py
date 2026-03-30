from __future__ import annotations

import asyncio
import logging
import random
import time
from contextlib import suppress
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.alerts.service import AlertService
from app.config.settings import RunMode, Settings
from app.db.repository import Repository
from app.execution.live import LiveDryRunExecutionEngine
from app.execution.paper import PaperExecutionEngine
from app.quote_engine.engine import HyperDexDexQuoteEngine, ShadowCexDexQuoteEngine
from app.risk.manager import GlobalRiskManager, HealthSnapshot
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
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.alert_service = alert_service
        self.risk_manager = risk_manager
        self.hyper_engine = hyper_engine
        self.shadow_engine = shadow_engine
        self.paper_engine = paper_engine
        self.live_engine = live_engine
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
            await self.alert_service.send(session, "INFO", "startup", "bot runner started")

    async def stop(self) -> None:
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        async with self.session_factory() as session:
            await self.alert_service.send(session, "INFO", "shutdown", "bot runner stopped")

    async def _scan_loop(self) -> None:
        while not self._stop_event.is_set():
            loop_start = time.perf_counter()
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
                        await self.alert_service.send(
                            session,
                            "WARN",
                            "daily_dd_stop",
                            "daily drawdown threshold reached; new entries stopped",
                        )

                    for route in routes:
                        try:
                            if route.strategy == "hyperevm_dex_dex":
                                amount = min(route.max_notional_usdc, self.settings.live_max_notional_usdc)
                                quote = await self.hyper_engine.quote_route(route, amount)
                                strategy_mode = current_mode
                                stale_limit = self.settings.global_stale_quote_stop_seconds
                            elif route.strategy == "base_virtual_shadow":
                                quote = await self.shadow_engine.quote_route(route, self.settings.shadow_notional_usdc)
                                strategy_mode = RunMode.PAPER
                                stale_limit = self.settings.shadow_stale_quote_seconds
                            else:
                                continue

                            health = self._build_health_snapshot()
                            smaller_pool = Decimal("450000")

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

                            status = "eligible" if decision.tradable else "blocked"
                            opp = await repo.insert_opportunity(
                                quote,
                                mode=strategy_mode.value,
                                status=status,
                                blocked_reason=decision.blocked_reason,
                            )

                            if not decision.tradable:
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
                                if decision.blocked_reason == "depeg_guard":
                                    await self.alert_service.send(
                                        session,
                                        "WARN",
                                        "depeg_stop",
                                        f"route={route.name} blocked by depeg guard",
                                    )
                                if decision.blocked_reason in {"gas_spike", "rpc_error_spike", "pool_unhealthy"}:
                                    await self.alert_service.send(
                                        session,
                                        "WARN",
                                        "abnormal_health",
                                        f"route={route.name} blocked_reason={decision.blocked_reason}",
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
                            )

                            if strategy_mode == RunMode.PAPER:
                                execution_result = await self.paper_engine.execute(quote)
                                realized = Decimal(str(execution_result.get("realized_pnl", "0")))
                                tx_status = "success" if bool(execution_result.get("ok")) else "failed"
                                tx_hash = str(execution_result.get("tx_hash", "paper"))
                            else:
                                execution_result = await self.live_engine.dry_run(quote)
                                realized = Decimal("0")
                                tx_status = "dry_run"
                                tx_hash = "live-dry-run"

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
                                notes=str(execution_result),
                            )

                            if tx_status in {"failed", "reverted"}:
                                self.risk_manager.mark_failure(route.id)
                                await self.alert_service.send(
                                    session,
                                    "ERROR",
                                    "trade_reverted",
                                    f"route={route.name} tx_status={tx_status}",
                                )
                            else:
                                self.risk_manager.mark_success(route.id, realized)
                                await self.alert_service.send(
                                    session,
                                    "INFO",
                                    "trade_executed",
                                    f"route={route.name} tx_status={tx_status}",
                                )

                        except Exception as route_exc:
                            self.risk_manager.mark_failure(route.id)
                            logger.exception(
                                "route_scan_failed",
                                **enrich_log_kwargs(
                                    strategy=route.strategy,
                                    pair=route.pair,
                                    route=route.id,
                                    action="scan_error",
                                ),
                            )
                            await self.alert_service.send(
                                session,
                                "ERROR",
                                "route_scan",
                                f"route={route.name} error={route_exc}",
                            )

            except Exception as exc:
                logger.exception("scan_loop_failed", **enrich_log_kwargs(action="scan_loop_error"))
                async with self.session_factory() as session:
                    await self.alert_service.send(session, "ERROR", "scan_loop", f"scan loop failure: {exc}")

            self.last_heartbeat = datetime.now(timezone.utc)
            elapsed = time.perf_counter() - loop_start
            sleep_for = max(0.1, self.settings.quote_poll_interval_seconds - elapsed)
            await asyncio.sleep(sleep_for)

    async def _health_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                async with self.session_factory() as session:
                    repo = Repository(session)
                    rpc_latency_ms = Decimal(str(40 + random.randint(0, 30)))
                    rpc_error_rate = Decimal("0.01")
                    db_latency_ms = Decimal(str(10 + random.randint(0, 5)))
                    quote_latency_ms = Decimal(str(20 + random.randint(0, 8)))
                    gas_now = Decimal("0.04")
                    dashboard_refresh_latency_ms = Decimal(str(25 + random.randint(0, 5)))
                    market_data_staleness_sec = Decimal("0.5")
                    venue_health = Decimal("1")
                    heartbeat_lag_sec = Decimal(
                        str((datetime.now(timezone.utc) - self.last_heartbeat).total_seconds())
                    )
                    alert_send_success_rate = Decimal("1") if self.alert_service.failure_count == 0 else Decimal("0.5")

                    metrics_store.record("rpc_latency_ms", rpc_latency_ms)
                    metrics_store.record("rpc_error_rate", rpc_error_rate)
                    metrics_store.record("db_latency_ms", db_latency_ms)
                    metrics_store.record("quote_latency_ms", quote_latency_ms)
                    metrics_store.record("gas_now", gas_now)
                    metrics_store.record("dashboard_refresh_latency_ms", dashboard_refresh_latency_ms)
                    metrics_store.record("market_data_staleness_sec", market_data_staleness_sec)
                    metrics_store.record("venue_health", venue_health)
                    metrics_store.record("heartbeat_lag_sec", heartbeat_lag_sec)
                    metrics_store.record("alert_send_success_rate", alert_send_success_rate)

                    await repo.write_health_metric("rpc_latency_ms", rpc_latency_ms)
                    await repo.write_health_metric("rpc_error_rate", rpc_error_rate)
                    await repo.write_health_metric("db_latency_ms", db_latency_ms)
                    await repo.write_health_metric("quote_latency_ms", quote_latency_ms)
                    await repo.write_health_metric("gas_now", gas_now)
                    await repo.write_health_metric("dashboard_refresh_latency_ms", dashboard_refresh_latency_ms)
                    await repo.write_health_metric("market_data_staleness_sec", market_data_staleness_sec)
                    await repo.write_health_metric("venue_health", venue_health)
                    await repo.write_health_metric("heartbeat_lag_sec", heartbeat_lag_sec)
                    await repo.write_health_metric("alert_send_success_rate", alert_send_success_rate)
            except Exception:
                logger.exception("health_loop_failed", **enrich_log_kwargs(action="health_loop_error"))

            await asyncio.sleep(self.settings.health_poll_interval_seconds)

    def _build_health_snapshot(self) -> HealthSnapshot:
        gas_now = metrics_store.latest("gas_now") or Decimal("0.04")
        gas_p90 = Decimal("0.05")
        return HealthSnapshot(
            rpc_error_rate_5m=metrics_store.latest("rpc_error_rate") or Decimal("0.01"),
            gas_now=gas_now,
            gas_p90=gas_p90,
            liquidity_change_pct=Decimal("0.01"),
            quote_stale_seconds=Decimal("0"),
            alert_failures=self.alert_service.failure_count,
            db_reachable=True,
            rpc_reachable=True,
            signing_ok=True,
            fee_known=True,
            quote_match=True,
            balance_match=True,
            clock_skew_ok=True,
            contract_revert_rate=Decimal("0.01"),
        )
