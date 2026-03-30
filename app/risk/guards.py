from __future__ import annotations

from decimal import Decimal


def stale_quote_guard(quote_age_seconds: Decimal, max_age_seconds: int) -> bool:
    return quote_age_seconds <= Decimal(max_age_seconds)


def slippage_guard(expected_slippage_bps: Decimal, max_slippage_bps: int) -> bool:
    return expected_slippage_bps <= Decimal(max_slippage_bps)


def depeg_guard(reference_deviation_bps: Decimal, threshold_bps: int) -> bool:
    return abs(reference_deviation_bps) <= Decimal(threshold_bps)


def gas_spike_guard(gas_now: Decimal, gas_p90: Decimal, multiplier: Decimal) -> bool:
    baseline = gas_p90 if gas_p90 > 0 else Decimal("1")
    return gas_now <= baseline * multiplier


def liquidity_deterioration_guard(change_pct: Decimal, stop_pct: Decimal) -> bool:
    return abs(change_pct) <= stop_pct