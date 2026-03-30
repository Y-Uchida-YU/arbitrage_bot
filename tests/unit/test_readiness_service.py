from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config.settings import Settings
from app.db.base import Base
from app.db.repository import Repository
from app.readiness.service import ReadinessService


@pytest.mark.asyncio
async def test_readiness_grading_and_blockers() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        repo = Repository(session)
        await repo.seed_defaults()
        routes = await repo.list_routes()
        assert routes
        unsupported_route = routes[0]
        fallback_route = routes[-1]

        await repo.insert_route_health_snapshot(
            strategy=unsupported_route.strategy,
            route_id=unsupported_route.id,
            pair=unsupported_route.pair,
            rpc_latency_ms=Decimal("1"),
            rpc_error_rate_5m=Decimal("0"),
            db_latency_ms=Decimal("1"),
            quote_latency_ms=Decimal("1"),
            market_data_staleness_seconds=Decimal("1"),
            contract_revert_rate=Decimal("0"),
            alert_send_success_rate=Decimal("1"),
            fee_known_status="unknown",
            quote_match_status="unknown",
            balance_match_status="unknown",
            support_status="unsupported",
            cooldown_active=False,
            paused=False,
            metadata_json="{}",
        )

        for _ in range(30):
            await repo.insert_market_snapshot(
                strategy=fallback_route.strategy,
                route_id=fallback_route.id,
                pair=fallback_route.pair,
                venue=fallback_route.venue_b,
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

        await repo.insert_route_health_snapshot(
            strategy=fallback_route.strategy,
            route_id=fallback_route.id,
            pair=fallback_route.pair,
            rpc_latency_ms=Decimal("1"),
            rpc_error_rate_5m=Decimal("0"),
            db_latency_ms=Decimal("1"),
            quote_latency_ms=Decimal("1"),
            market_data_staleness_seconds=Decimal("1"),
            contract_revert_rate=Decimal("0"),
            alert_send_success_rate=Decimal("1"),
            fee_known_status="fallback_only",
            quote_match_status="matched",
            balance_match_status="db_inventory_ok",
            support_status="supported",
            cooldown_active=False,
            paused=False,
            metadata_json="{}",
        )

        service = ReadinessService(Settings())
        rows = await service.route_readiness_rows(repo)
        row_by_route = {row["route_id"]: row for row in rows}
        assert row_by_route[unsupported_route.id]["readiness_grade"] == "red"
        assert "unsupported_route" in row_by_route[unsupported_route.id]["readiness_blockers"]
        assert row_by_route[fallback_route.id]["readiness_grade"] != "green"
        assert "fee_unverified" in row_by_route[fallback_route.id]["readiness_blockers"]

        summary = await service.readiness_summary(repo)
        assert summary["total_routes"] >= 2
        assert summary["red_count"] >= 1

    await engine.dispose()
