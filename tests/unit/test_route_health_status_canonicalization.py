from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.repository import Repository


@pytest.mark.asyncio
async def test_route_health_snapshot_persists_canonical_statuses() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        repo = Repository(session)
        await repo.seed_defaults()
        route = (await repo.list_routes())[0]

        row = await repo.insert_route_health_snapshot(
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
            fee_known_status="GOOD",
            quote_match_status="bad",
            balance_match_status="true",
            support_status="yes",
            cooldown_active=False,
            paused=False,
            metadata_json="{}",
        )

        assert row.fee_known_status == "config_only"
        assert row.quote_match_status == "mismatch"
        assert row.balance_match_status == "internal_ok"
        assert row.support_status == "supported"

        latest = await repo.latest_route_health_snapshot(route.id)
        assert latest is not None
        assert latest.fee_known_status == "config_only"
        assert latest.quote_match_status == "mismatch"
        assert latest.balance_match_status == "internal_ok"
        assert latest.support_status == "supported"

    await engine.dispose()

