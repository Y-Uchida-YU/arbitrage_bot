from __future__ import annotations

from decimal import Decimal

from app.config.settings import Settings
from app.exchanges.cex.base import CEXAdapter
from app.exchanges.errors import SymbolNormalizeError


class MockCEXAdapter(CEXAdapter):
    def __init__(self, venue: str, settings: Settings) -> None:
        self.venue = venue
        self.settings = settings

    def normalize_symbol(self, raw_symbol: str) -> str:
        normalized = raw_symbol.replace("/", "").replace("-", "").upper().strip()
        if not normalized.isalnum() or len(normalized) < 6:
            raise SymbolNormalizeError("symbol_normalize_failed", f"invalid symbol: {raw_symbol}")
        return normalized

    async def get_best_bid_ask(self, symbol: str) -> tuple[Decimal, Decimal]:
        _ = symbol
        mid = self.settings.mock_base_virtual_usdc_mid
        bid = (mid * Decimal("1.030")).quantize(Decimal("0.00000001"))
        ask = (mid * Decimal("1.040")).quantize(Decimal("0.00000001"))
        return bid, ask

    async def get_orderbook_top(self, symbol: str, depth_n: int) -> list[tuple[Decimal, Decimal]]:
        bid, ask = await self.get_best_bid_ask(symbol)
        rows: list[tuple[Decimal, Decimal]] = []
        for i in range(depth_n):
            rows.append((bid - Decimal(i) * Decimal("0.0001"), Decimal("1000")))
            rows.append((ask + Decimal(i) * Decimal("0.0001"), Decimal("1000")))
        return rows

    async def get_trading_fee(self, symbol: str, side: str, maker_or_taker: str) -> int:
        fee, _provenance = await self.get_trading_fee_details(symbol, side, maker_or_taker)
        return fee

    async def get_trading_fee_details(self, symbol: str, side: str, maker_or_taker: str) -> tuple[int, str]:
        _ = symbol
        _ = side
        maker = maker_or_taker == "maker"
        if self.venue == "bybit":
            fee = self.settings.bybit_maker_fee_bps_fallback if maker else self.settings.bybit_taker_fee_bps_fallback
            return fee, "fallback_only"
        fee = self.settings.mexc_maker_fee_bps_fallback if maker else self.settings.mexc_taker_fee_bps_fallback
        return fee, "fallback_only"

    async def get_market_status(self, symbol: str) -> str:
        _ = symbol
        return "trading"
