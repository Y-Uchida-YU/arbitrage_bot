from app.config.settings import Settings
from app.exchanges.cex.bybit import BybitSpotAdapter
from app.exchanges.cex.mexc import MEXCSpotAdapter


def test_symbol_normalization() -> None:
    settings = Settings()
    bybit = BybitSpotAdapter(settings)
    mexc = MEXCSpotAdapter(settings)

    assert bybit.normalize_symbol("virtual/usdc") == "VIRTUALUSDC"
    assert mexc.normalize_symbol("VIRTUAL-USDC") == "VIRTUALUSDC"