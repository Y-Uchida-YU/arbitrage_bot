from __future__ import annotations

import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Alert

logger = logging.getLogger(__name__)


class AlertService:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url
        self.failure_count = 0

    async def send(self, session: AsyncSession, level: str, category: str, message: str) -> None:
        sent = False
        err = ""
        if self.webhook_url:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.post(self.webhook_url, json={"content": f"[{level}] {category}: {message}"})
                    response.raise_for_status()
                    sent = True
                    self.failure_count = 0
            except Exception as exc:  # pragma: no cover - network dependent
                err = str(exc)
                self.failure_count += 1
                logger.warning("alert_send_failed", extra={"error": err})
        else:
            err = "webhook_not_configured"

        session.add(Alert(run_id="system", level=level, category=category, message=message, sent=sent, error=err))
        await session.commit()