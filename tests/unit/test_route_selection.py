import asyncio

from app.config.settings import Settings
from app.exchanges.factory import build_hyperevm_dex_adapters


def test_route_selection_has_required_venues() -> None:
    settings = Settings()
    adapters = build_hyperevm_dex_adapters(settings)
    assert "ramses_v3" in adapters
    assert "hybra_v3" in adapters


def test_route_adapter_quote_runs() -> None:
    settings = Settings(use_mock_market_data=True)
    adapters = build_hyperevm_dex_adapters(settings)
    amount_out = asyncio.run(adapters["ramses_v3"].quote_exact_input("USDC", "USDT0", settings.live_max_notional_usdc))
    assert amount_out > 0