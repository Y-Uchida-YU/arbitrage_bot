from __future__ import annotations

from collections.abc import Iterable

FEE_CONFIDENCE_ORDER: tuple[str, ...] = (
    "unknown",
    "fallback_only",
    "config_only",
    "venue_declared",
    "acct_verified",
    "chain_verified",
)

BALANCE_CONFIDENCE_ORDER: tuple[str, ...] = (
    "unknown",
    "mismatch",
    "internal_ok",
    "db_inventory_ok",
    "wallet_verified",
    "venue_verified",
)

QUOTE_MATCH_ORDER: tuple[str, ...] = (
    "unknown",
    "mismatch",
    "matched",
)

FEE_CONFIDENCE_RANK = {name: idx for idx, name in enumerate(FEE_CONFIDENCE_ORDER)}
BALANCE_CONFIDENCE_RANK = {name: idx for idx, name in enumerate(BALANCE_CONFIDENCE_ORDER)}
QUOTE_MATCH_RANK = {name: idx for idx, name in enumerate(QUOTE_MATCH_ORDER)}


def normalize_fee_confidence(raw: str | None) -> str:
    if raw is None:
        return "unknown"
    value = raw.strip().lower()
    if value in FEE_CONFIDENCE_RANK:
        return value
    return "unknown"


def normalize_balance_confidence(raw: str | None) -> str:
    if raw is None:
        return "unknown"
    value = raw.strip().lower()
    if value in BALANCE_CONFIDENCE_RANK:
        return value
    return "unknown"


def normalize_quote_match_status(raw: str | None) -> str:
    if raw is None:
        return "unknown"
    value = raw.strip().lower()
    if value in QUOTE_MATCH_RANK:
        return value
    if value in {"true", "1", "yes"}:
        return "matched"
    if value in {"false", "0", "no"}:
        return "mismatch"
    return "unknown"


def fee_confidence_at_least(actual: str, required: str) -> bool:
    return FEE_CONFIDENCE_RANK[normalize_fee_confidence(actual)] >= FEE_CONFIDENCE_RANK[
        normalize_fee_confidence(required)
    ]


def balance_confidence_at_least(actual: str, required: str) -> bool:
    return BALANCE_CONFIDENCE_RANK[normalize_balance_confidence(actual)] >= BALANCE_CONFIDENCE_RANK[
        normalize_balance_confidence(required)
    ]


def min_fee_confidence(statuses: Iterable[str]) -> str:
    normalized = [normalize_fee_confidence(value) for value in statuses]
    if not normalized:
        return "unknown"
    return min(normalized, key=lambda x: FEE_CONFIDENCE_RANK[x])


def min_balance_confidence(statuses: Iterable[str]) -> str:
    normalized = [normalize_balance_confidence(value) for value in statuses]
    if not normalized:
        return "unknown"
    return min(normalized, key=lambda x: BALANCE_CONFIDENCE_RANK[x])
