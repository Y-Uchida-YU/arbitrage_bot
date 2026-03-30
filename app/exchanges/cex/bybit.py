from __future__ import annotations

from decimal import Decimal

import httpx

from app.config.settings import Settings
from app.exchanges.cex.base import CEXAdapter
from app.exchanges.errors import AdapterError, SymbolNormalizeError


class BybitSpotAdapter(CEXAdapter):
    venue = "bybit"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = "https://api.bybit.com"

    def normalize_symbol(self, raw_symbol: str) -> str:
        normalized = raw_symbol.replace("/", "").replace("-", "").upper().strip()
        if not normalized.isalnum() or len(normalized) < 6:
            raise SymbolNormalizeError("symbol_normalize_failed", f"invalid symbol: {raw_symbol}")
        return normalized

    async def get_best_bid_ask(self, symbol: str) -> tuple[Decimal, Decimal]:
        normalized = self.normalize_symbol(symbol)
        payload = await self._request_json(
            "/v5/market/tickers",
            {"category": "spot", "symbol": normalized},
        )
        items = payload.get("result", {}).get("list", [])
        if not items:
            raise AdapterError("partial_response", f"bybit ticker missing for {normalized}")

        bid = items[0].get("bid1Price")
        ask = items[0].get("ask1Price")
        if bid is None or ask is None:
            raise AdapterError("partial_response", f"bid/ask missing for {normalized}")
        return Decimal(str(bid)), Decimal(str(ask))

    async def get_orderbook_top(self, symbol: str, depth_n: int) -> list[tuple[Decimal, Decimal]]:
        normalized = self.normalize_symbol(symbol)
        payload = await self._request_json(
            "/v5/market/orderbook",
            {"category": "spot", "symbol": normalized, "limit": str(max(1, min(depth_n, 50)))},
        )

        bids = payload.get("result", {}).get("b", [])
        asks = payload.get("result", {}).get("a", [])
        if not isinstance(bids, list) or not isinstance(asks, list):
            raise AdapterError("partial_response", f"orderbook malformed for {normalized}")

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
        _ = side
        _ = symbol
        mt = maker_or_taker.lower()
        if mt == "maker":
            return self.settings.bybit_maker_fee_bps_fallback, "fallback_only"
        return self.settings.bybit_taker_fee_bps_fallback, "fallback_only"

    async def get_market_status(self, symbol: str) -> str:
        normalized = self.normalize_symbol(symbol)
        payload = await self._request_json(
            "/v5/market/instruments-info",
            {"category": "spot", "symbol": normalized},
        )
        rows = payload.get("result", {}).get("list", [])
        if not rows:
            return "unknown"
        status = str(rows[0].get("status", "unknown")).lower()
        if status in {"trading", "settling"}:
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
                if payload.get("retCode") not in (None, 0):
                    raise AdapterError("venue_error", f"bybit retCode={payload.get('retCode')}")
                return payload
            except Exception as exc:
                last_exc = exc
                continue

        raise AdapterError("network_error", f"bybit request failed: {last_exc}")
