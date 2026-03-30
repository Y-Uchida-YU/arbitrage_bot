from __future__ import annotations

from decimal import Decimal

import httpx

from app.config.settings import Settings
from app.exchanges.cex.base import CEXAdapter


class BybitSpotAdapter(CEXAdapter):
    venue = "bybit"

    def __init__(self, settings: Settings, timeout_seconds: float = 3.0) -> None:
        self.settings = settings
        self.base_url = "https://api.bybit.com"
        self.timeout_seconds = timeout_seconds

    def normalize_symbol(self, raw_symbol: str) -> str:
        return raw_symbol.replace("/", "").replace("-", "").upper()

    async def get_best_bid_ask(self, symbol: str) -> tuple[Decimal, Decimal]:
        normalized = self.normalize_symbol(symbol)
        url = f"{self.base_url}/v5/market/tickers"
        params = {"category": "spot", "symbol": normalized}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        items = payload.get("result", {}).get("list", [])
        if not items:
            raise ValueError(f"bybit ticker missing for {normalized}")
        item = items[0]
        return Decimal(item["bid1Price"]), Decimal(item["ask1Price"])

    async def get_orderbook_top(self, symbol: str, depth_n: int) -> list[tuple[Decimal, Decimal]]:
        normalized = self.normalize_symbol(symbol)
        url = f"{self.base_url}/v5/market/orderbook"
        params = {"category": "spot", "symbol": normalized, "limit": str(max(1, min(depth_n, 25)))}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        bids = payload.get("result", {}).get("b", [])
        asks = payload.get("result", {}).get("a", [])
        top: list[tuple[Decimal, Decimal]] = []
        for row in bids[:depth_n]:
            top.append((Decimal(row[0]), Decimal(row[1])))
        for row in asks[:depth_n]:
            top.append((Decimal(row[0]), Decimal(row[1])))
        return top

    async def get_trading_fee(self, symbol: str, side: str, maker_or_taker: str) -> int:
        _ = side
        _ = symbol
        mt = maker_or_taker.lower()
        if mt == "maker":
            return self.settings.bybit_maker_fee_bps_fallback
        return self.settings.bybit_taker_fee_bps_fallback

    async def get_market_status(self, symbol: str) -> str:
        try:
            await self.get_best_bid_ask(symbol)
        except Exception:
            return "unknown"
        return "trading"