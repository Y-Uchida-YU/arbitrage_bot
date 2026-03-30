from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Opportunity


class ReplayEngine:
    async def replay_expected_pnl(
        self,
        session: AsyncSession,
        strategy: str | None = None,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
    ) -> dict[str, Decimal | int]:
        query = select(Opportunity)
        if strategy:
            query = query.where(Opportunity.strategy == strategy)
        if start_ts:
            query = query.where(Opportunity.timestamp >= start_ts)
        if end_ts:
            query = query.where(Opportunity.timestamp <= end_ts)

        rows = list(await session.scalars(query.order_by(Opportunity.timestamp.asc())))
        total = Decimal("0")
        count = 0
        for row in rows:
            if row.status in {"eligible", "executed"}:
                total += row.expected_pnl_abs
                count += 1

        return {
            "replayed_entries": count,
            "replayed_expected_pnl": total,
        }