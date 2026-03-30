from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.base import Base
from app.db.init_db import schema_ready


@pytest.mark.asyncio
async def test_schema_ready_requires_full_required_tables() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE runtime_controls (
                    id TEXT PRIMARY KEY,
                    mode TEXT,
                    global_pause INTEGER,
                    strategy_pause INTEGER,
                    pair_pause INTEGER,
                    route_pause INTEGER,
                    live_guard_armed INTEGER,
                    cooldown_until TEXT,
                    updated_at TEXT
                )
                """
            )
        )
    assert await schema_ready(engine) is False
    await engine.dispose()


@pytest.mark.asyncio
async def test_schema_ready_true_after_full_create_all() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    assert await schema_ready(engine) is True
    await engine.dispose()
