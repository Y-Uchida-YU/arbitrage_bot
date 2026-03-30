import asyncio

from app.config.settings import Settings
from app.exchanges.cex.mock import MockCEXAdapter


def test_fee_calculation_fallbacks() -> None:
    settings = Settings(
        bybit_maker_fee_bps_fallback=10,
        bybit_taker_fee_bps_fallback=15,
        mexc_maker_fee_bps_fallback=0,
        mexc_taker_fee_bps_fallback=5,
    )
    bybit = MockCEXAdapter("bybit", settings)
    mexc = MockCEXAdapter("mexc", settings)

    bybit_maker = asyncio.run(bybit.get_trading_fee("VIRTUALUSDC", "buy", "maker"))
    bybit_taker = asyncio.run(bybit.get_trading_fee("VIRTUALUSDC", "buy", "taker"))
    mexc_maker = asyncio.run(mexc.get_trading_fee("VIRTUALUSDC", "buy", "maker"))
    mexc_taker = asyncio.run(mexc.get_trading_fee("VIRTUALUSDC", "buy", "taker"))

    assert bybit_maker == 10
    assert bybit_taker == 15
    assert mexc_maker == 0
    assert mexc_taker == 5