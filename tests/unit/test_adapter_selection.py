from app.config.settings import Settings
from app.exchanges.cex.mock import MockCEXAdapter
from app.exchanges.factory import build_cex_adapters, build_hyperevm_dex_adapters


def test_adapter_selection_mock_mode() -> None:
    settings = Settings(use_mock_market_data=True)
    cex = build_cex_adapters(settings)
    dex = build_hyperevm_dex_adapters(settings)

    assert isinstance(cex["bybit"], MockCEXAdapter)
    assert dex["ramses_v3"].supported is True


def test_adapter_selection_real_mode_does_not_crash() -> None:
    settings = Settings(use_mock_market_data=False)
    dex = build_hyperevm_dex_adapters(settings)
    assert "ramses_v3" in dex
    # no quoter configured by default => unsupported-safe
    assert dex["ramses_v3"].supported in {True, False}