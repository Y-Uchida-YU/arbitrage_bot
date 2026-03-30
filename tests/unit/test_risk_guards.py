from decimal import Decimal

from app.risk.guards import depeg_guard, gas_spike_guard, slippage_guard, stale_quote_guard


def test_stale_quote_guard() -> None:
    assert stale_quote_guard(Decimal("2"), 3)
    assert not stale_quote_guard(Decimal("4"), 3)


def test_slippage_guard() -> None:
    assert slippage_guard(Decimal("2"), 2)
    assert not slippage_guard(Decimal("3"), 2)


def test_depeg_guard() -> None:
    assert depeg_guard(Decimal("49"), 50)
    assert not depeg_guard(Decimal("51"), 50)


def test_gas_spike_guard() -> None:
    assert gas_spike_guard(Decimal("40"), Decimal("30"), Decimal("1.5"))
    assert not gas_spike_guard(Decimal("50"), Decimal("30"), Decimal("1.5"))