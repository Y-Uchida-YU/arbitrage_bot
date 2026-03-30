from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import RunMode
from app.models.core import (
    Balance,
    ConfigAuditLog,
    Execution,
    FeeProfile,
    HealthMetric,
    InventorySnapshot,
    KillSwitchEvent,
    Opportunity,
    Route,
    RuntimeControl,
    Strategy,
    TradeAttempt,
)
from app.quote_engine.types import RouteQuote
from app.utils.ids import new_idempotency_key, new_run_id


class Repository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def seed_defaults(self) -> None:
        has_strategy = await self.session.scalar(select(func.count(Strategy.id)))
        if not has_strategy:
            self.session.add_all(
                [
                    Strategy(name="hyperevm_dex_dex", mode="paper", enabled=True, description="HyperEVM DEX-DEX"),
                    Strategy(name="base_virtual_shadow", mode="paper", enabled=True, description="Base CEX-DEX shadow"),
                ]
            )

        has_route = await self.session.scalar(select(func.count(Route.id)))
        if not has_route:
            self.session.add_all(
                [
                    Route(
                        strategy="hyperevm_dex_dex",
                        name="ramses_to_hybra_usdc_roundtrip",
                        pair="USDC/USDt0",
                        direction="forward",
                        venue_a="ramses_v3",
                        venue_b="hybra_v3",
                        pool_a="ramses_v3_usdc_usdt0_5",
                        pool_b="hybra_v3_usdt0_usdc_5",
                        router_a="0x0000000000000000000000000000000000000010",
                        router_b="0x0000000000000000000000000000000000000010",
                        fee_tier_a_bps=5,
                        fee_tier_b_bps=5,
                        is_live_allowed=True,
                    ),
                    Route(
                        strategy="hyperevm_dex_dex",
                        name="hybra_to_ramses_usdc_roundtrip",
                        pair="USDC/USDt0",
                        direction="reverse",
                        venue_a="hybra_v3",
                        venue_b="ramses_v3",
                        pool_a="hybra_v3_usdc_usdt0_5",
                        pool_b="ramses_v3_usdt0_usdc_5",
                        router_a="0x0000000000000000000000000000000000000010",
                        router_b="0x0000000000000000000000000000000000000010",
                        fee_tier_a_bps=5,
                        fee_tier_b_bps=5,
                        is_live_allowed=True,
                    ),
                    Route(
                        strategy="base_virtual_shadow",
                        name="bybit_vs_uniswap_base",
                        pair="VIRTUAL/USDC",
                        direction="dex_to_cex",
                        venue_a="bybit",
                        venue_b="uniswap_v3_base",
                        pool_a="bybit_spot",
                        pool_b="base_uni_v3_virtual_usdc_100",
                        router_a="bybit",
                        router_b="uniswap_v3_base",
                        fee_tier_a_bps=10,
                        fee_tier_b_bps=100,
                        is_live_allowed=False,
                    ),
                    Route(
                        strategy="base_virtual_shadow",
                        name="mexc_vs_pancake_base",
                        pair="VIRTUAL/USDC",
                        direction="dex_to_cex",
                        venue_a="mexc",
                        venue_b="pancakeswap_v3_base",
                        pool_a="mexc_spot",
                        pool_b="base_cake_v3_virtual_usdc_100",
                        router_a="mexc",
                        router_b="pancake_v3_base",
                        fee_tier_a_bps=5,
                        fee_tier_b_bps=100,
                        is_live_allowed=False,
                    ),
                ]
            )

        has_control = await self.session.scalar(select(func.count(RuntimeControl.id)))
        if not has_control:
            self.session.add(RuntimeControl(mode="paper", global_pause=False))

        has_balance = await self.session.scalar(select(func.count(Balance.id)))
        if not has_balance:
            self.session.add(Balance(venue="hyperevm_wallet", token="USDC", available=Decimal("1000"), total=Decimal("1000"), usd_value=Decimal("1000")))

        has_fee = await self.session.scalar(select(func.count(FeeProfile.id)))
        if not has_fee:
            self.session.add_all(
                [
                    FeeProfile(venue="bybit", symbol="VIRTUALUSDC", maker_or_taker="maker", fee_bps=10, is_fallback=True),
                    FeeProfile(venue="bybit", symbol="VIRTUALUSDC", maker_or_taker="taker", fee_bps=15, is_fallback=True),
                    FeeProfile(venue="mexc", symbol="VIRTUALUSDC", maker_or_taker="maker", fee_bps=0, is_fallback=True),
                    FeeProfile(venue="mexc", symbol="VIRTUALUSDC", maker_or_taker="taker", fee_bps=5, is_fallback=True),
                ]
            )

        await self.session.commit()

    async def get_runtime_control(self) -> RuntimeControl:
        row = await self.session.scalar(select(RuntimeControl).order_by(RuntimeControl.updated_at.desc()))
        if row is None:
            row = RuntimeControl(mode="paper", global_pause=False)
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
        return row

    async def set_mode(self, mode: RunMode) -> RuntimeControl:
        ctrl = await self.get_runtime_control()
        before = ctrl.mode
        ctrl.mode = mode.value
        ctrl.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(ctrl)
        await self.write_config_audit(
            actor="api",
            action="switch_mode",
            target="runtime_controls.mode",
            before_json=f'{{\"mode\":\"{before}\"}}',
            after_json=f'{{\"mode\":\"{ctrl.mode}\"}}',
            notes="manual mode switch",
        )
        return ctrl

    async def set_global_pause(self, value: bool) -> RuntimeControl:
        ctrl = await self.get_runtime_control()
        ctrl.global_pause = value
        ctrl.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(ctrl)
        return ctrl

    async def write_kill_switch_event(self, scope: str, scope_ref: str, action: str, reason: str) -> None:
        self.session.add(
            KillSwitchEvent(
                run_id=new_run_id(),
                scope=scope,
                scope_ref=scope_ref,
                action=action,
                reason=reason,
            )
        )
        await self.session.commit()

    async def set_route_enabled(self, route_id: str, enabled: bool) -> bool:
        before_route = await self.session.scalar(select(Route).where(Route.id == route_id))
        before_enabled = bool(before_route.enabled) if before_route is not None else None
        result = await self.session.execute(update(Route).where(Route.id == route_id).values(enabled=enabled))
        await self.session.commit()
        if before_enabled is not None and result.rowcount > 0:
            await self.write_config_audit(
                actor="api",
                action="set_route_enabled",
                target=f"routes.{route_id}.enabled",
                before_json=f'{{\"enabled\":{str(before_enabled).lower()}}}',
                after_json=f'{{\"enabled\":{str(enabled).lower()}}}',
                notes="manual route control",
            )
        return result.rowcount > 0

    async def get_routes(self, strategy: str | None = None, enabled_only: bool = True) -> list[Route]:
        query = select(Route)
        if strategy:
            query = query.where(Route.strategy == strategy)
        if enabled_only:
            query = query.where(Route.enabled.is_(True), Route.kill_switch.is_(False))
        rows = await self.session.scalars(query.order_by(Route.created_at.asc()))
        return list(rows)

    async def list_routes(self) -> list[Route]:
        rows = await self.session.scalars(select(Route).order_by(Route.strategy.asc(), Route.name.asc()))
        return list(rows)

    async def get_wallet_usdc_balance(self) -> Decimal:
        bal = await self.session.scalar(
            select(Balance).where(Balance.venue == "hyperevm_wallet", Balance.token == "USDC")
        )
        if bal is None:
            return Decimal("0")
        return bal.available

    async def insert_opportunity(
        self,
        quote: RouteQuote,
        mode: str,
        status: str,
        blocked_reason: str,
    ) -> Opportunity:
        run_id = new_run_id()
        opp = Opportunity(
            run_id=run_id,
            idempotency_key=new_idempotency_key("opp"),
            strategy=quote.strategy,
            mode=mode,
            pair=quote.pair,
            direction=quote.direction,
            route_id=quote.route_id,
            venues=quote.metadata.get("venues", ""),
            raw_edge_bps=quote.raw_edge_bps,
            modeled_edge_bps=quote.modeled_net_edge_bps,
            expected_pnl_abs=quote.modeled_net_edge_amount,
            expected_slippage_bps=quote.expected_slippage_bps,
            gas_estimate_usdc=quote.gas_cost_usdc,
            quote_age_seconds=quote.quote_age_seconds,
            status=status,
            blocked_reason=blocked_reason,
            pool_health_ok=quote.metadata.get("pool_health", "false") == "true",
            persisted_seconds=quote.persisted_seconds,
            payload_json=str(quote.metadata),
        )
        self.session.add(opp)
        await self.session.commit()
        await self.session.refresh(opp)
        return opp

    async def insert_trade_attempt(
        self,
        opportunity_id: str,
        route_id: str,
        strategy: str,
        mode: str,
        input_amount: Decimal,
        expected_output_amount: Decimal,
        expected_pnl: Decimal,
        status: str,
        blocked_reason: str = "",
        failure_category: str = "",
        is_fatal_failure: bool = False,
        cooldown_triggered: bool = False,
        notes: str = "",
    ) -> TradeAttempt:
        attempt = TradeAttempt(
            opportunity_id=opportunity_id,
            run_id=new_run_id(),
            idempotency_key=new_idempotency_key("attempt"),
            route_id=route_id,
            strategy=strategy,
            mode=mode,
            input_amount=input_amount,
            expected_output_amount=expected_output_amount,
            expected_pnl=expected_pnl,
            status=status,
            blocked_reason=blocked_reason,
            failure_category=failure_category,
            is_fatal_failure=is_fatal_failure,
            cooldown_triggered=cooldown_triggered,
            notes=notes,
        )
        self.session.add(attempt)
        await self.session.commit()
        await self.session.refresh(attempt)
        return attempt

    async def insert_execution(
        self,
        attempt_id: str,
        route_id: str,
        strategy: str,
        mode: str,
        tx_status: str,
        tx_hash: str,
        input_amount: Decimal,
        output_amount: Decimal,
        expected_pnl: Decimal,
        realized_pnl: Decimal,
        revert_reason: str = "",
        failure_category: str = "",
        is_fatal_failure: bool = False,
        cooldown_triggered: bool = False,
        gas_used: Decimal = Decimal("0"),
        latency_ms: int = 0,
        notes: str = "",
    ) -> Execution:
        execution = Execution(
            attempt_id=attempt_id,
            run_id=new_run_id(),
            route_id=route_id,
            strategy=strategy,
            mode=mode,
            tx_hash=tx_hash,
            tx_status=tx_status,
            revert_reason=revert_reason,
            failure_category=failure_category,
            is_fatal_failure=is_fatal_failure,
            cooldown_triggered=cooldown_triggered,
            input_amount=input_amount,
            output_amount=output_amount,
            expected_pnl=expected_pnl,
            realized_pnl=realized_pnl,
            gas_used=gas_used,
            latency_ms=latency_ms,
            notes=notes,
        )
        self.session.add(execution)
        await self.session.commit()
        await self.session.refresh(execution)
        return execution

    async def update_trade_attempt_outcome(
        self,
        attempt_id: str,
        status: str,
        blocked_reason: str = "",
        failure_category: str = "",
        is_fatal_failure: bool = False,
        cooldown_triggered: bool = False,
        notes: str = "",
    ) -> None:
        attempt = await self.session.scalar(select(TradeAttempt).where(TradeAttempt.id == attempt_id))
        if attempt is None:
            return
        attempt.status = status
        attempt.blocked_reason = blocked_reason
        attempt.failure_category = failure_category
        attempt.is_fatal_failure = is_fatal_failure
        attempt.cooldown_triggered = cooldown_triggered
        if notes:
            attempt.notes = notes
        await self.session.commit()

    async def list_opportunities(
        self,
        strategy: str | None = None,
        pair: str | None = None,
        venue: str | None = None,
        route_id: str | None = None,
        blocked_reason: str | None = None,
        limit: int = 200,
    ) -> list[Opportunity]:
        query = select(Opportunity)
        if strategy:
            query = query.where(Opportunity.strategy == strategy)
        if pair:
            query = query.where(Opportunity.pair == pair)
        if venue:
            query = query.where(Opportunity.venues.contains(venue))
        if route_id:
            query = query.where(Opportunity.route_id == route_id)
        if blocked_reason:
            query = query.where(Opportunity.blocked_reason == blocked_reason)
        rows = await self.session.scalars(query.order_by(Opportunity.created_at.desc()).limit(limit))
        return list(rows)

    async def list_trades(self, limit: int = 200) -> list[TradeAttempt]:
        rows = await self.session.scalars(select(TradeAttempt).order_by(TradeAttempt.created_at.desc()).limit(limit))
        return list(rows)

    async def list_executions(self, limit: int = 200) -> list[Execution]:
        rows = await self.session.scalars(select(Execution).order_by(Execution.created_at.desc()).limit(limit))
        return list(rows)

    async def list_balances(self) -> list[Balance]:
        rows = await self.session.scalars(select(Balance).order_by(Balance.venue.asc(), Balance.token.asc()))
        return list(rows)

    async def list_inventory(self, limit: int = 200) -> list[InventorySnapshot]:
        rows = await self.session.scalars(
            select(InventorySnapshot).order_by(InventorySnapshot.timestamp.desc()).limit(limit)
        )
        return list(rows)

    async def list_health_metrics(self, limit: int = 200) -> list[HealthMetric]:
        rows = await self.session.scalars(select(HealthMetric).order_by(HealthMetric.timestamp.desc()).limit(limit))
        return list(rows)

    async def blocked_reason_summary(self, since_minutes: int = 60) -> list[dict[str, object]]:
        since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        rows = await self.session.execute(
            select(Opportunity.blocked_reason, func.count(Opportunity.id))
            .where(Opportunity.created_at >= since, Opportunity.blocked_reason != "")
            .group_by(Opportunity.blocked_reason)
            .order_by(func.count(Opportunity.id).desc())
        )
        return [
            {
                "blocked_reason": reason,
                "count": int(count),
            }
            for reason, count in rows.all()
        ]

    async def quote_unavailable_count(self, since_minutes: int = 60) -> int:
        since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        value = await self.session.scalar(
            select(func.count(Opportunity.id)).where(
                Opportunity.created_at >= since,
                Opportunity.blocked_reason == "quote_unavailable",
            )
        )
        return int(value or 0)

    async def unhealthy_venues_count(self, since_minutes: int = 60) -> int:
        since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        rows = await self.session.execute(
            select(Opportunity.venues)
            .where(Opportunity.created_at >= since, Opportunity.blocked_reason.in_(["pool_unhealthy", "quote_unavailable"]))
            .distinct()
        )
        venues: set[str] = set()
        for (value,) in rows.all():
            for venue in str(value).split("->"):
                venue = venue.strip()
                if venue:
                    venues.add(venue)
        return len(venues)

    async def write_health_metric(self, name: str, value: Decimal, status: str = "ok", labels_json: str = "{}") -> HealthMetric:
        metric = HealthMetric(run_id=new_run_id(), name=name, value=value, status=status, labels_json=labels_json)
        self.session.add(metric)
        await self.session.commit()
        await self.session.refresh(metric)
        return metric

    async def write_config_audit(
        self,
        actor: str,
        action: str,
        target: str,
        before_json: str,
        after_json: str,
        notes: str = "",
    ) -> None:
        self.session.add(
            ConfigAuditLog(
                actor=actor,
                action=action,
                target=target,
                before_json=before_json,
                after_json=after_json,
                notes=notes,
            )
        )
        await self.session.commit()

    async def overview(self) -> dict[str, object]:
        ctrl = await self.get_runtime_control()

        total_realized = await self.session.scalar(select(func.coalesce(func.sum(Execution.realized_pnl), 0)))
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_realized = await self.session.scalar(
            select(func.coalesce(func.sum(Execution.realized_pnl), 0)).where(Execution.created_at >= today_start)
        )

        trades_total = await self.session.scalar(select(func.count(TradeAttempt.id)))
        exec_total = await self.session.scalar(select(func.count(Execution.id)))
        exec_success = await self.session.scalar(select(func.count(Execution.id)).where(Execution.tx_status.in_(["success", "dry_run"])))
        exec_reverted = await self.session.scalar(select(func.count(Execution.id)).where(Execution.tx_status.in_(["reverted", "failed", "dry_run_blocked"])))

        latest_opps = await self.session.scalar(
            select(func.count(Opportunity.id)).where(Opportunity.created_at >= datetime.now(timezone.utc) - timedelta(minutes=5))
        )

        balances = await self.list_balances()
        quote_unavailable = await self.quote_unavailable_count(since_minutes=60)
        unhealthy_venues = await self.unhealthy_venues_count(since_minutes=60)

        success_rate = Decimal("0")
        failure_rate = Decimal("0")
        if exec_total and exec_total > 0:
            success_rate = Decimal(exec_success or 0) / Decimal(exec_total)
            failure_rate = Decimal(exec_reverted or 0) / Decimal(exec_total)

        return {
            "current_mode": ctrl.mode,
            "global_status": "stopped" if ctrl.global_pause else "healthy",
            "realized_pnl": Decimal(total_realized or 0),
            "unrealized_pnl": Decimal("0"),
            "today_pnl": Decimal(today_realized or 0),
            "cumulative_pnl": Decimal(total_realized or 0),
            "trade_count": int(trades_total or 0),
            "success_rate": success_rate,
            "failure_rate": failure_rate,
            "reverted_tx_count": int(exec_reverted or 0),
            "open_exposures": 0,
            "wallet_balances": [
                {
                    "venue": b.venue,
                    "token": b.token,
                    "available": b.available,
                    "reserved": b.reserved,
                    "total": b.total,
                    "usd_value": b.usd_value,
                }
                for b in balances
            ],
            "inventory_by_venue": [
                {"venue": b.venue, "token": b.token, "amount": b.total, "usd_value": b.usd_value}
                for b in balances
            ],
            "latest_opportunities_count": int(latest_opps or 0),
            "quote_unavailable_count": quote_unavailable,
            "unhealthy_venues_count": unhealthy_venues,
            "active_kill_switches": ["global_pause"] if ctrl.global_pause else [],
        }
