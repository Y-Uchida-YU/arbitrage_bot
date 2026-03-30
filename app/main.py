from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import uvicorn
from fastapi import FastAPI

from app.api.router import router as api_router
from app.app_state import build_app_state
from app.config.settings import get_settings
from app.dashboard.router import router as dashboard_router
from app.db.repository import Repository
from app.db.session import close_engine, get_engine, get_sessionmaker
from app.db.init_db import create_all
from app.models import core as _models  # noqa: F401
from app.utils.logging import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings)

    engine = get_engine()
    session_factory = get_sessionmaker()

    await create_all(engine)
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
        await services.runner.stop()
        await close_engine()
        logger.info("application_stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="Safe Arbitrage Bot", lifespan=lifespan)
    app.include_router(api_router)
    app.include_router(dashboard_router)
    return app


app = create_app()


def run() -> None:
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run()
