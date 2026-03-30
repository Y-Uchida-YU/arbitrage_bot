from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.repository import Repository
from app.models.core import Opportunity, Route


@pytest.mark.asyncio
async def test_blocked_reason_summary() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        repo = Repository(session)

        route = Route(
            strategy="hyperevm_dex_dex",
            name="r1",
            pair="USDC/USDt0",
            direction="forward",
            venue_a="ramses_v3",
            venue_b="hybra_v3",
            pool_a="p1",
            pool_b="p2",
            router_a="r1",
            router_b="r2",
            fee_tier_a_bps=5,
            fee_tier_b_bps=5,
            max_notional_usdc=Decimal("100"),
            enabled=True,
            is_live_allowed=True,
            kill_switch=False,
        )
        session.add(route)
        await session.commit()
        await session.refresh(route)

        session.add_all(
            [
                Opportunity(
                    run_id="run1",
                    idempotency_key="k1",
                    timestamp=datetime.now(timezone.utc),
                    strategy="hyperevm_dex_dex",
                    mode="paper",
                    pair="USDC/USDt0",
                    direction="forward",
                    route_id=route.id,
                    venues="ramses_v3->hybra_v3",
                    raw_edge_bps=Decimal("10"),
                    modeled_edge_bps=Decimal("8"),
                    expected_pnl_abs=Decimal("0.1"),
                    expected_slippage_bps=Decimal("1"),
                    gas_estimate_usdc=Decimal("0.01"),
                    quote_age_seconds=Decimal("1"),
                    status="blocked",
                    blocked_reason="quote_unavailable",
                    pool_health_ok=False,
                    persisted_seconds=Decimal("0"),
                    payload_json="{}",
                ),
                Opportunity(
                    run_id="run2",
                    idempotency_key="k2",
                    timestamp=datetime.now(timezone.utc),
                    strategy="hyperevm_dex_dex",
                    mode="paper",
                    pair="USDC/USDt0",
                    direction="forward",
                    route_id=route.id,
                    venues="ramses_v3->hybra_v3",
                    raw_edge_bps=Decimal("10"),
                    modeled_edge_bps=Decimal("8"),
                    expected_pnl_abs=Decimal("0.1"),
                    expected_slippage_bps=Decimal("1"),
                    gas_estimate_usdc=Decimal("0.01"),
                    quote_age_seconds=Decimal("1"),
                    status="blocked",
                    blocked_reason="quote_unavailable",
                    pool_health_ok=False,
                    persisted_seconds=Decimal("0"),
                    payload_json="{}",
                ),
            ]
        )
        await session.commit()

        summary = await repo.blocked_reason_summary(since_minutes=60)
        assert summary
        assert summary[0]["blocked_reason"] == "quote_unavailable"
        assert int(summary[0]["count"]) >= 2

    await engine.dispose()