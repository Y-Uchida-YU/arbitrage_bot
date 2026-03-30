from __future__ import annotations

from decimal import Decimal

import httpx

from app.config.settings import Settings
from app.exchanges.cex.base import CEXAdapter
from app.exchanges.errors import AdapterError, SymbolNormalizeError


class MEXCSpotAdapter(CEXAdapter):
    venue = "mexc"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = "https://api.mexc.com"

    def normalize_symbol(self, raw_symbol: str) -> str:
        normalized = raw_symbol.replace("/", "").replace("-", "").upper().strip()
        if not normalized.isalnum() or len(normalized) < 6:
            raise SymbolNormalizeError("symbol_normalize_failed", f"invalid symbol: {raw_symbol}")
        return normalized

    async def get_best_bid_ask(self, symbol: str) -> tuple[Decimal, Decimal]:
        normalized = self.normalize_symbol(symbol)
        payload = await self._request_json("/api/v3/ticker/bookTicker", {"symbol": normalized})
        bid = payload.get("bidPrice")
        ask = payload.get("askPrice")
        if bid is None or ask is None:
            raise AdapterError("partial_response", f"mexc bid/ask missing for {normalized}")
        return Decimal(str(bid)), Decimal(str(ask))

    async def get_orderbook_top(self, symbol: str, depth_n: int) -> list[tuple[Decimal, Decimal]]:
        normalized = self.normalize_symbol(symbol)
        payload = await self._request_json(
            "/api/v3/depth",
            {"symbol": normalized, "limit": str(max(5, min(depth_n, 50)))},
        )
        bids = payload.get("bids", [])
        asks = payload.get("asks", [])
        if not isinstance(bids, list) or not isinstance(asks, list):
            raise AdapterError("partial_response", f"mexc orderbook malformed for {normalized}")

        top: list[tuple[Decimal, Decimal]] = []
        for row in bids[:depth_n]:
            if len(row) < 2:
                continue
            top.append((Decimal(str(row[0])), Decimal(str(row[1]))))
        for row in asks[:depth_n]:
            if len(row) < 2:
                continue
            top.append((Decimal(str(row[0])), Decimal(str(row[1]))))
        return top

    async def get_trading_fee(self, symbol: str, side: str, maker_or_taker: str) -> int:
        fee, _provenance = await self.get_trading_fee_details(symbol, side, maker_or_taker)
        return fee

    async def get_trading_fee_details(self, symbol: str, side: str, maker_or_taker: str) -> tuple[int, str]:
        _ = symbol
        _ = side
        if maker_or_taker.lower() == "maker":
            return self.settings.mexc_maker_fee_bps_fallback, "fallback_only"
        return self.settings.mexc_taker_fee_bps_fallback, "fallback_only"

    async def get_market_status(self, symbol: str) -> str:
        normalized = self.normalize_symbol(symbol)
        payload = await self._request_json("/api/v3/exchangeInfo", {"symbol": normalized})
        symbols = payload.get("symbols", [])
        if not symbols:
            return "unknown"
        status = str(symbols[0].get("status", "unknown")).lower()
        if status == "trading":
            return "trading"
        return status

    async def _request_json(self, path: str, params: dict[str, str]) -> dict:
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for _ in range(max(1, self.settings.cex_request_retries)):
            try:
                async with httpx.AsyncClient(timeout=self.settings.cex_request_timeout_seconds) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    payload = response.json()
                return payload
            except Exception as exc:
                last_exc = exc
                continue

        raise AdapterError("network_error", f"mexc request failed: {last_exc}")
