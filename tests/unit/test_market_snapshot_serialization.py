from __future__ import annotations

import json
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.repository import Repository


@pytest.mark.asyncio
async def test_market_snapshot_serialization_roundtrip() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        repo = Repository(session)
        await repo.seed_defaults()
        routes = await repo.list_routes()
        route = routes[0]

        payload = {
            "quote_source": "real",
            "quote_unavailable_reason": "unsupported quoter",
            "risk_checks": "fee_known:0,quote_match:0",
        }

        row = await repo.insert_market_snapshot(
            strategy=route.strategy,
            route_id=route.id,
            pair=route.pair,
            venue=route.venue_a,
            context="leg_a",
            bid=Decimal("1"),
            ask=Decimal("1.0001"),
            amount_in=Decimal("100"),
            quoted_amount_out=Decimal("99.9"),
            liquidity_usd=Decimal("500000"),
            gas_gwei=Decimal("0.1"),
            quote_age_seconds=Decimal("0.5"),
            source_type="real",
            metadata_json=json.dumps(payload, sort_keys=True),
        )

        assert row.source_type == "real"

        loaded = await repo.list_market_snapshots(route_id=route.id, limit=10)
        assert loaded
        parsed = json.loads(loaded[0].metadata_json)
        assert parsed["quote_source"] == "real"
        assert parsed["quote_unavailable_reason"] == "unsupported quoter"

    await engine.dispose()
