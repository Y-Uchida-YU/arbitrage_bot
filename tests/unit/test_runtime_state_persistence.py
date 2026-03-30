from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.repository import Repository
from app.risk.manager import GlobalRiskManager
from app.config.settings import Settings


@pytest.mark.asyncio
async def test_route_runtime_state_persists_and_hydrates() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        repo = Repository(session)
        await repo.seed_defaults()
        routes = await repo.list_routes()
        assert routes
        route_id = routes[0].id

        cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=5)
        await repo.upsert_route_runtime_state(
            route_id=route_id,
            paused=True,
            cooldown_until=cooldown_until,
            last_failure_category="revert",
            last_failure_reason="tx reverted",
            last_failure_fatal=True,
            last_failure_at=datetime.now(timezone.utc),
            consecutive_failures=1,
            consecutive_losses=0,
        )

    async with session_factory() as session:
        repo = Repository(session)
        row = await repo.get_route_runtime_state(route_id)
        assert row is not None
        assert row.paused is True
        assert row.cooldown_until is not None
        assert row.last_failure_category == "revert"
        assert row.last_failure_fatal is True

        risk = GlobalRiskManager(Settings())
        risk.hydrate_route_state(
            route_id=route_id,
            paused=row.paused,
            cooldown_until=row.cooldown_until,
            last_failure_category=row.last_failure_category,
            last_failure_reason=row.last_failure_reason,
            last_failure_fatal=row.last_failure_fatal,
            last_failure_at=row.last_failure_at,
            consecutive_failures=row.consecutive_failures,
            consecutive_losses=row.consecutive_losses,
        )
        hydrated = risk.get_route_state(route_id)
        assert hydrated["route_paused"] is True
        assert hydrated["consecutive_failures"] == 1
        assert hydrated["cooldown_remaining_seconds"] > 0

    await engine.dispose()
