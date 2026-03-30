from __future__ import annotations

from decimal import Decimal

import httpx

from app.config.settings import Settings
from app.exchanges.cex.base import CEXAdapter


class MEXCSpotAdapter(CEXAdapter):
    venue = "mexc"

    def __init__(self, settings: Settings, timeout_seconds: float = 3.0) -> None:
        self.settings = settings
        self.base_url = "https://api.mexc.com"
        self.timeout_seconds = timeout_seconds

    def normalize_symbol(self, raw_symbol: str) -> str:
        return raw_symbol.replace("/", "").replace("-", "").upper()

    async def get_best_bid_ask(self, symbol: str) -> tuple[Decimal, Decimal]:
        normalized = self.normalize_symbol(symbol)
        url = f"{self.base_url}/api/v3/ticker/bookTicker"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url, params={"symbol": normalized})
            response.raise_for_status()
            payload = response.json()
        if "bidPrice" not in payload or "askPrice" not in payload:
            raise ValueError(f"mexc ticker missing for {normalized}")
        return Decimal(payload["bidPrice"]), Decimal(payload["askPrice"])

    async def get_orderbook_top(self, symbol: str, depth_n: int) -> list[tuple[Decimal, Decimal]]:
        normalized = self.normalize_symbol(symbol)
        url = f"{self.base_url}/api/v3/depth"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url, params={"symbol": normalized, "limit": str(max(5, depth_n))})
            response.raise_for_status()
            payload = response.json()
        bids = payload.get("bids", [])
        asks = payload.get("asks", [])
        top: list[tuple[Decimal, Decimal]] = []
        for row in bids[:depth_n]:
            top.append((Decimal(row[0]), Decimal(row[1])))
        for row in asks[:depth_n]:
            top.append((Decimal(row[0]), Decimal(row[1])))
        return top

    async def get_trading_fee(self, symbol: str, side: str, maker_or_taker: str) -> int:
        _ = side
        _ = symbol
        if maker_or_taker.lower() == "maker":
            return self.settings.mexc_maker_fee_bps_fallback
        return self.settings.mexc_taker_fee_bps_fallback

    async def get_market_status(self, symbol: str) -> str:
        try:
            await self.get_best_bid_ask(symbol)
        except Exception:
            return "unknown"
        return "trading"