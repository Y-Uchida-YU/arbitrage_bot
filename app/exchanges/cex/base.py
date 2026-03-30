from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal


class CEXAdapter(ABC):
    venue: str

    @abstractmethod
    async def get_best_bid_ask(self, symbol: str) -> tuple[Decimal, Decimal]:
        raise NotImplementedError

    @abstractmethod
    async def get_orderbook_top(self, symbol: str, depth_n: int) -> list[tuple[Decimal, Decimal]]:
        raise NotImplementedError

    @abstractmethod
    async def get_trading_fee(self, symbol: str, side: str, maker_or_taker: str) -> int:
        raise NotImplementedError

    @abstractmethod
    async def get_trading_fee_details(self, symbol: str, side: str, maker_or_taker: str) -> tuple[int, str]:
        raise NotImplementedError

    @abstractmethod
    async def get_market_status(self, symbol: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def normalize_symbol(self, raw_symbol: str) -> str:
        raise NotImplementedError
