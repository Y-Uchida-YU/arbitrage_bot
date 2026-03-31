from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config.settings import Settings
from app.db.base import Base
from app.db.repository import Repository
from app.models.core import Route
from app.readiness.service import ReadinessService


async def _insert_observations(repo: Repository, route: Route, count: int = 25) -> None:
    for _ in range(count):
        await repo.insert_market_snapshot(
            strategy=route.strategy,
            route_id=route.id,
            pair=route.pair,
            venue=route.venue_b,
            context="leg_b",
            bid=Decimal("1"),
            ask=Decimal("1.01"),
            amount_in=Decimal("100"),
            quoted_amount_out=Decimal("101"),
            liquidity_usd=Decimal("500000"),
            gas_gwei=Decimal("0.05"),
            quote_age_seconds=Decimal("1"),
            source_type="real",
            metadata_json='{"initial_amount":"100","final_amount":"101"}',
        )


async def _insert_health_snapshot(
    repo: Repository,
    route: Route,
    *,
    fee_status: str,
    balance_status: str,
    quote_status: str = "matched",
    support_status: str = "supported",
) -> None:
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
        fee_known_status=fee_status,
        quote_match_status=quote_status,
        balance_match_status=balance_status,
        support_status=support_status,
        cooldown_active=False,
        paused=False,
        metadata_json="{}",
    )


async def _insert_backtest(repo: Repository, route: Route, replay_mode: str) -> None:
    now = datetime.now(timezone.utc)
    run = await repo.create_backtest_run(
        strategy=route.strategy,
        route_id=route.id,
        pair=route.pair,
        start_ts=now - timedelta(minutes=10),
        end_ts=now,
        parameter_set_id=None,
        notes=f"replay_mode={replay_mode}",
    )
    await repo.insert_backtest_result(
        backtest_run_id=run.id,
        signals=1,
        eligible_count=1,
        blocked_count=0,
        simulated_pnl=Decimal("0.1"),
        hit_rate=Decimal("1"),
        avg_modeled_edge_bps=Decimal("1"),
        avg_realized_like_pnl=Decimal("0.1"),
        max_drawdown=Decimal("0"),
        worst_sequence=0,
        missed_opportunities=0,
        blocked_reason_json="{}",
        metadata_json=json.dumps({"replay_mode": replay_mode}, sort_keys=True),
    )
    await repo.finish_backtest_run(run.id, "completed")


@pytest.mark.asyncio
async def test_readiness_strategy_aware_thresholds() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        repo = Repository(session)
        await repo.seed_defaults()
        routes = await repo.list_routes()
        hyper_route = next(route for route in routes if route.strategy == "hyperevm_dex_dex")
        shadow_route = next(route for route in routes if route.strategy == "base_virtual_shadow")

        await _insert_observations(repo, hyper_route, count=25)
        await _insert_observations(repo, shadow_route, count=25)
        await _insert_health_snapshot(
            repo,
            hyper_route,
            fee_status="fallback_only",
            balance_status="internal_ok",
        )
        await _insert_health_snapshot(
            repo,
            shadow_route,
            fee_status="fallback_only",
            balance_status="db_inventory_ok",
        )
        await _insert_backtest(repo, hyper_route, "opportunities")
        await _insert_backtest(repo, shadow_route, "opportunities")

        service = ReadinessService(Settings())
        rows = await service.route_readiness_rows(repo)
        row_by_route = {row["route_id"]: row for row in rows}

        assert row_by_route[hyper_route.id]["readiness_grade"] == "red"
        assert "fee_unverified" in row_by_route[hyper_route.id]["readiness_blockers"]
        assert "balance_unverified" in row_by_route[hyper_route.id]["readiness_blockers"]

        assert row_by_route[shadow_route.id]["readiness_grade"] == "yellow"
        assert "observation_only_route" in row_by_route[shadow_route.id]["readiness_blockers"]
        assert "fee_unverified" not in row_by_route[shadow_route.id]["readiness_blockers"]
        assert "balance_unverified" not in row_by_route[shadow_route.id]["readiness_blockers"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_readiness_summary_uses_latest_backtest_mode_not_latest_observation() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        repo = Repository(session)
        await repo.seed_defaults()
        routes = await repo.list_routes()
        observation_latest_route = routes[0]
        latest_backtest_route = routes[-1]

        await _insert_observations(repo, latest_backtest_route, count=20)
        await _insert_observations(repo, observation_latest_route, count=20)
        await _insert_health_snapshot(
            repo,
            observation_latest_route,
            fee_status="chain_verified",
            balance_status="wallet_verified",
        )
        await _insert_health_snapshot(
            repo,
            latest_backtest_route,
            fee_status="fallback_only",
            balance_status="internal_ok",
        )

        await _insert_backtest(repo, observation_latest_route, "opportunities")
        await _insert_backtest(repo, latest_backtest_route, "market_snapshots")

        service = ReadinessService(Settings())
        summary = await service.readiness_summary(repo)

        assert summary["latest_backtest_mode"] == "market_snapshots"

    await engine.dispose()

