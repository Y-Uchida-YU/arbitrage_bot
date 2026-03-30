from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal


@dataclass(slots=True)
class MetricPoint:
    ts: datetime
    value: Decimal


class MetricsStore:
    def __init__(self) -> None:
        self._series: dict[str, deque[MetricPoint]] = defaultdict(deque)

    def record(self, name: str, value: Decimal) -> None:
        now = datetime.now(timezone.utc)
        dq = self._series[name]
        dq.append(MetricPoint(now, value))
        cutoff = now - timedelta(hours=24)
        while dq and dq[0].ts < cutoff:
            dq.popleft()

    def latest(self, name: str) -> Decimal | None:
        dq = self._series.get(name)
        if not dq:
            return None
        return dq[-1].value

    def get_series(self, name: str, limit: int = 100) -> list[MetricPoint]:
        dq = self._series.get(name)
        if not dq:
            return []
        return list(dq)[-limit:]

    def snapshot(self) -> dict[str, Decimal | None]:
        return {k: (v[-1].value if v else None) for k, v in self._series.items()}


metrics_store = MetricsStore()