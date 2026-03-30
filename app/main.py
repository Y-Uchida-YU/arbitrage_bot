from __future__ import annotations

import argparse
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from collections.abc import AsyncIterator

import uvicorn
from fastapi import FastAPI

from app.backtest.engine import BacktestEngine
from app.api.router import router as api_router
from app.app_state import build_app_state
from app.config.settings import get_settings
from app.dashboard.router import router as dashboard_router
from app.db.repository import Repository
from app.db.session import close_engine, get_engine, get_sessionmaker
from app.db.init_db import create_all, schema_ready
from app.models import core as _models  # noqa: F401
from app.utils.logging import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings)

    engine = get_engine()
    session_factory = get_sessionmaker()

    if settings.auto_create_schema:
        await create_all(engine)
    else:
        ready = await schema_ready(engine)
        if not ready:
            raise RuntimeError(
                "Database schema is not ready. Run Alembic migrations or set AUTO_CREATE_SCHEMA=true for local/dev only."
            )
    async with session_factory() as session:
        repo = Repository(session)
        await repo.seed_defaults()

    services = build_app_state(settings, session_factory)
    app.state.services = services

    await services.runner.start()
    logger.info("application_started")
    try:
        yield
    finally:
        try:
            await services.runner.stop()
        except Exception:
            logger.exception("runner_stop_failed")
        finally:
            await close_engine()
        logger.info("application_stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="Safe Arbitrage Bot", lifespan=lifespan)
    app.include_router(api_router)
    app.include_router(dashboard_router)
    return app


app = create_app()


def _parse_iso8601_utc(raw: str) -> datetime:
    candidate = raw.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(candidate)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def run_backtest_cli(args: argparse.Namespace) -> None:
    settings = get_settings()
    setup_logging(settings)
    engine = get_engine()
    session_factory = get_sessionmaker()

    if settings.auto_create_schema:
        await create_all(engine)
    else:
        ready = await schema_ready(engine)
        if not ready:
            raise RuntimeError(
                "Database schema is not ready. Run Alembic migrations or set AUTO_CREATE_SCHEMA=true for local/dev only."
            )

    async with session_factory() as session:
        repo = Repository(session)
        await repo.seed_defaults()
        runner = BacktestEngine(settings)
        result = await runner.run(
            repo,
            strategy=args.strategy,
            route_id=args.route_id,
            pair=args.pair,
            start_ts=_parse_iso8601_utc(args.start_ts),
            end_ts=_parse_iso8601_utc(args.end_ts),
            parameter_set_id=args.parameter_set_id,
            notes=args.notes or "",
            replay_mode=args.replay_mode or "opportunities",
        )
        print(json.dumps(result, default=str))
    await close_engine()


def run() -> None:
    parser = argparse.ArgumentParser(prog="app.main")
    sub = parser.add_subparsers(dest="command")
    backtest = sub.add_parser("backtest", help="run replay/backtest against saved observations")
    backtest.add_argument("--strategy", required=True)
    backtest.add_argument("--route-id", required=True)
    backtest.add_argument("--pair", required=True)
    backtest.add_argument("--start-ts", required=True, help="ISO8601 UTC datetime")
    backtest.add_argument("--end-ts", required=True, help="ISO8601 UTC datetime")
    backtest.add_argument("--parameter-set-id", required=False)
    backtest.add_argument("--notes", required=False)
    backtest.add_argument(
        "--replay-mode",
        required=False,
        default="opportunities",
        choices=["opportunities", "market_snapshots"],
    )

    args = parser.parse_args()
    if args.command == "backtest":
        asyncio.run(run_backtest_cli(args))
        return

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run()
