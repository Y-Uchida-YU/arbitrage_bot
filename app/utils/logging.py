from __future__ import annotations

import contextvars
import logging
from pathlib import Path
import sys
from typing import Any

from pythonjsonlogger.json import JsonFormatter

from app.config.settings import Settings


correlation_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")
run_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("run_id", default="")


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_ctx.get()
        record.run_id = run_id_ctx.get()
        for key in ("strategy", "pair", "venue", "route", "mode", "action", "opportunity_id", "tx_hash"):
            if not hasattr(record, key):
                setattr(record, key, "")
        return True


def setup_logging(settings: Settings) -> None:
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(settings.log_level.upper())

    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.addFilter(ContextFilter())

    if settings.log_json:
        fmt = (
            "%(asctime)s %(levelname)s %(name)s %(message)s %(strategy)s %(pair)s "
            "%(venue)s %(route)s %(mode)s %(action)s %(correlation_id)s %(run_id)s "
            "%(opportunity_id)s %(tx_hash)s"
        )
        formatter = JsonFormatter(fmt)
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "app.log", encoding="utf-8")
    file_handler.addFilter(ContextFilter())
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


def enrich_log_kwargs(**kwargs: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "strategy": "",
        "pair": "",
        "venue": "",
        "route": "",
        "mode": "",
        "action": "",
        "opportunity_id": "",
        "tx_hash": "",
    }
    base.update(kwargs)
    return {"extra": base}
