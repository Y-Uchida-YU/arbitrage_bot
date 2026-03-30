from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base

REQUIRED_TABLES: set[str] = {
    "alerts",
    "balances",
    "backtest_results",
    "backtest_runs",
    "backtest_trades",
    "config_audit_logs",
    "executions",
    "fee_profiles",
    "health_metrics",
    "inventory_snapshots",
    "kill_switch_events",
    "market_snapshots",
    "opportunities",
    "parameter_sets",
    "route_health_snapshots",
    "route_runtime_states",
    "routes",
    "runtime_controls",
    "strategies",
    "trade_attempts",
    "venue_configs",
}


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
            table_names = await conn.run_sync(
                lambda sync_conn: set(inspect(sync_conn).get_table_names())
            )
        return REQUIRED_TABLES.issubset(table_names)
    except Exception:
        return False
