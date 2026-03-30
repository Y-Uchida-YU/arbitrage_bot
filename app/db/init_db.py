from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base


async def create_all(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_all(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def schema_ready(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1 FROM runtime_controls LIMIT 1"))
        return True
    except Exception:
        return False
