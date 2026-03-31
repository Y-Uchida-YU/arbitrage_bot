from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.backtest.engine import BacktestEngine
from app.config.settings import Settings
from app.db.base import Base
from app.db.repository import Repository
from app.models.core import Opportunity, ParameterSet


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


@pytest.mark.asyncio
async def test_backtest_result_aggregation_and_parameter_set_application() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings()
    bt = BacktestEngine(settings)

    async with session_factory() as session:
        repo = Repository(session)
        await repo.seed_defaults()

        routes = await repo.get_routes(strategy="hyperevm_dex_dex", enabled_only=False)
        assert routes
        route = routes[0]

        now = datetime.now(timezone.utc)
        payload_good = json.dumps(
            {
                "quote_unavailable": "false",
                "fee_known": "true",
                "fee_known_status": "config_only",
                "quote_match": "true",
                "quote_match_status": "matched",
                "balance_match_status": "internal_ok",
                "smaller_pool_liquidity_usdc": "500000",
                "initial_amount": "100",
            },
            sort_keys=True,
        )
        payload_low_edge = payload_good

        session.add_all(
            [
                Opportunity(
                    run_id=_id("run"),
                    idempotency_key=_id("opp"),
                    timestamp=now - timedelta(minutes=2),
                    strategy=route.strategy,
                    mode="paper",
                    pair=route.pair,
                    direction=route.direction,
                    route_id=route.id,
                    venues=f"{route.venue_a}->{route.venue_b}",
                    raw_edge_bps=Decimal("40"),
                    modeled_edge_bps=Decimal("45"),
                    expected_pnl_abs=Decimal("1.5"),
                    expected_slippage_bps=Decimal("1"),
                    gas_estimate_usdc=Decimal("0.01"),
                    quote_age_seconds=Decimal("1"),
                    status="eligible",
                    blocked_reason="",
                    pool_health_ok=True,
                    persisted_seconds=Decimal("15"),
                    payload_json=payload_good,
                ),
                Opportunity(
                    run_id=_id("run"),
                    idempotency_key=_id("opp"),
                    timestamp=now - timedelta(minutes=1),
                    strategy=route.strategy,
                    mode="paper",
                    pair=route.pair,
                    direction=route.direction,
                    route_id=route.id,
                    venues=f"{route.venue_a}->{route.venue_b}",
                    raw_edge_bps=Decimal("10"),
                    modeled_edge_bps=Decimal("5"),
                    expected_pnl_abs=Decimal("0.2"),
                    expected_slippage_bps=Decimal("1"),
                    gas_estimate_usdc=Decimal("0.01"),
                    quote_age_seconds=Decimal("1"),
                    status="blocked",
                    blocked_reason="below_threshold",
                    pool_health_ok=True,
                    persisted_seconds=Decimal("2"),
                    payload_json=payload_low_edge,
                ),
            ]
        )
        await session.commit()

        start_ts = now - timedelta(minutes=5)
        end_ts = now + timedelta(minutes=1)

        result_default = await bt.run(
            repo,
            strategy=route.strategy,
            route_id=route.id,
            pair=route.pair,
            start_ts=start_ts,
            end_ts=end_ts,
            parameter_set_id=None,
            notes="default params",
        )

        assert result_default["status"] == "completed"
        assert int(result_default["signals"]) == 2
        assert int(result_default["eligible_count"]) == 1
        assert int(result_default["blocked_count"]) == 1
        assert result_default["blocked_reasons"].get("below_threshold", 0) >= 1

        custom = ParameterSet(
            name=f"strict-{uuid.uuid4().hex}",
            strategy=route.strategy,
            description="strict threshold",
            is_default=False,
            params_json=json.dumps(
                {
                    "min_modeled_edge_bps": 1000,
                    "max_slippage_bps": 1,
                    "max_quote_age_seconds": 3,
                    "liquidity_cap_ratio": "0.0002",
                },
                sort_keys=True,
            ),
        )
        session.add(custom)
        await session.commit()
        await session.refresh(custom)

        result_strict = await bt.run(
            repo,
            strategy=route.strategy,
            route_id=route.id,
            pair=route.pair,
            start_ts=start_ts,
            end_ts=end_ts,
            parameter_set_id=custom.id,
            notes="strict params",
        )

        assert result_strict["status"] == "completed"
        assert int(result_strict["signals"]) == 2
        assert int(result_strict["eligible_count"]) == 0
        assert int(result_strict["blocked_count"]) == 2

        runs = await repo.list_backtest_runs(limit=10)
        results = await repo.list_backtest_results(limit=10)
        trades = await repo.list_backtest_trades(runs[0].id, limit=100)

        assert len(runs) >= 2
        assert len(results) >= 2
        assert trades

    await engine.dispose()


@pytest.mark.asyncio
async def test_market_snapshot_replay_mode_runs() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings()
    bt = BacktestEngine(settings)

    async with session_factory() as session:
        repo = Repository(session)
        await repo.seed_defaults()
        route = (await repo.get_routes(strategy="hyperevm_dex_dex", enabled_only=False))[0]
        now = datetime.now(timezone.utc)

        await repo.insert_route_health_snapshot(
            strategy=route.strategy,
            route_id=route.id,
            pair=route.pair,
            rpc_latency_ms=Decimal("1"),
            rpc_error_rate_5m=Decimal("0"),
            db_latency_ms=Decimal("1"),
            quote_latency_ms=Decimal("1"),
            market_data_staleness_seconds=Decimal("1"),
            contract_revert_rate=Decimal("0"),
            alert_send_success_rate=Decimal("1"),
            fee_known_status="chain_verified",
            quote_match_status="matched",
            balance_match_status="wallet_verified",
            support_status="supported",
            cooldown_active=False,
            paused=False,
            metadata_json="{}",
        )

        metadata = json.dumps(
            {
                "initial_amount": "100",
                "final_amount": "100.8",
                "fee_known_status": "chain_verified",
                "balance_match_status": "wallet_verified",
                "quote_match_status": "matched",
                "smaller_pool_liquidity_usdc": "500000",
            },
            sort_keys=True,
        )
        await repo.insert_market_snapshot(
            strategy=route.strategy,
            route_id=route.id,
            pair=route.pair,
            venue=route.venue_a,
            context="leg_a",
            bid=Decimal("0"),
            ask=Decimal("0"),
            amount_in=Decimal("100"),
            quoted_amount_out=Decimal("100.4"),
            liquidity_usd=Decimal("500000"),
            gas_gwei=Decimal("0.05"),
            quote_age_seconds=Decimal("1"),
            source_type="real",
            metadata_json=metadata,
        )
        await repo.insert_market_snapshot(
            strategy=route.strategy,
            route_id=route.id,
            pair=route.pair,
            venue=route.venue_b,
            context="leg_b",
            bid=Decimal("0"),
            ask=Decimal("0"),
            amount_in=Decimal("100.4"),
            quoted_amount_out=Decimal("100.8"),
            liquidity_usd=Decimal("500000"),
            gas_gwei=Decimal("0.05"),
            quote_age_seconds=Decimal("1"),
            source_type="real",
            metadata_json=metadata,
        )

        result = await bt.run(
            repo,
            strategy=route.strategy,
            route_id=route.id,
            pair=route.pair,
            start_ts=now - timedelta(minutes=5),
            end_ts=now + timedelta(minutes=5),
            parameter_set_id=None,
            notes="snapshot replay",
            replay_mode="market_snapshots",
        )
        assert result["status"] == "completed"
        assert result["replay_mode"] == "market_snapshots"
        assert int(result["signals"]) >= 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_market_snapshot_replay_normalizes_legacy_statuses() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings()
    bt = BacktestEngine(settings)

    async with session_factory() as session:
        repo = Repository(session)
        await repo.seed_defaults()
        route = (await repo.get_routes(strategy="hyperevm_dex_dex", enabled_only=False))[0]
        now = datetime.now(timezone.utc)

        await repo.insert_route_health_snapshot(
            strategy=route.strategy,
            route_id=route.id,
            pair=route.pair,
            rpc_latency_ms=Decimal("1"),
            rpc_error_rate_5m=Decimal("0"),
            db_latency_ms=Decimal("1"),
            quote_latency_ms=Decimal("1"),
            market_data_staleness_seconds=Decimal("1"),
            contract_revert_rate=Decimal("0"),
            alert_send_success_rate=Decimal("1"),
            fee_known_status="good",
            quote_match_status="good",
            balance_match_status="good",
            support_status="bad",
            cooldown_active=False,
            paused=False,
            metadata_json="{}",
        )

        metadata = json.dumps(
            {
                "initial_amount": "100",
                "final_amount": "100.8",
                "fee_known_status": "true",
                "balance_match_status": "true",
                "quote_match_status": "true",
                "quote_unavailable": "false",
                "smaller_pool_liquidity_usdc": "500000",
            },
            sort_keys=True,
        )
        await repo.insert_market_snapshot(
            strategy=route.strategy,
            route_id=route.id,
            pair=route.pair,
            venue=route.venue_b,
            context="leg_b",
            bid=Decimal("0"),
            ask=Decimal("0"),
            amount_in=Decimal("100.4"),
            quoted_amount_out=Decimal("100.8"),
            liquidity_usd=Decimal("500000"),
            gas_gwei=Decimal("0.05"),
            quote_age_seconds=Decimal("1"),
            source_type="real",
            metadata_json=metadata,
        )

        result = await bt.run(
            repo,
            strategy=route.strategy,
            route_id=route.id,
            pair=route.pair,
            start_ts=now - timedelta(minutes=5),
            end_ts=now + timedelta(minutes=5),
            parameter_set_id=None,
            notes="legacy status normalization",
            replay_mode="market_snapshots",
        )
        assert result["status"] == "completed"
        assert int(result["blocked_count"]) >= 1
        assert result["blocked_reasons"].get("quote_unavailable", 0) >= 1

    await engine.dispose()
