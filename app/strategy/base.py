from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal


class Strategy(ABC):
    name: str

    @abstractmethod
    async def run_once(self, notional: Decimal) -> dict[str, str]:
        raise NotImplementedError