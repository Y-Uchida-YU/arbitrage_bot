from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

BPS_DIVISOR = Decimal("10000")


def to_bps(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return (numerator / denominator * BPS_DIVISOR).quantize(Decimal("0.00001"), rounding=ROUND_DOWN)


def apply_bps(amount: Decimal, bps: Decimal) -> Decimal:
    return (amount * bps / BPS_DIVISOR).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)