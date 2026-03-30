from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal


class DEXAdapter(ABC):
    venue: str
    supported: bool = True
    support_reason: str = ""

    @abstractmethod
    async def quote_exact_input(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        fee_tier: int | None = None,
        pool_id: str | None = None,
    ) -> Decimal:
        raise NotImplementedError

    @abstractmethod
    async def quote_exact_output(
        self,
        token_in: str,
        token_out: str,
        amount_out: Decimal,
        fee_tier: int | None = None,
        pool_id: str | None = None,
    ) -> Decimal:
        raise NotImplementedError

    @abstractmethod
    async def estimate_gas(self, route: dict[str, str]) -> int:
        raise NotImplementedError

    @abstractmethod
    async def get_pool_state(self, pool_id: str) -> dict[str, Decimal | str | bool]:
        raise NotImplementedError

    @abstractmethod
    async def get_fee_bps(self, pool_id: str) -> int:
        raise NotImplementedError

    @abstractmethod
    async def get_liquidity_snapshot(self, pool_id: str) -> dict[str, Decimal]:
        raise NotImplementedError

    @abstractmethod
    async def is_pool_healthy(self, pool_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_last_quote_timestamp(self) -> float | None:
        raise NotImplementedError
