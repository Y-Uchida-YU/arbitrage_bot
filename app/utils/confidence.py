from __future__ import annotations

from collections.abc import Iterable

SUPPORT_STATUS_ORDER: tuple[str, ...] = (
    "unknown",
    "unsupported",
    "supported",
)

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

SUPPORT_STATUS_SET = set(SUPPORT_STATUS_ORDER)
FEE_CONFIDENCE_SET = set(FEE_CONFIDENCE_ORDER)
BALANCE_CONFIDENCE_SET = set(BALANCE_CONFIDENCE_ORDER)
QUOTE_MATCH_SET = set(QUOTE_MATCH_ORDER)

SUPPORT_STATUS_RANK = {name: idx for idx, name in enumerate(SUPPORT_STATUS_ORDER)}
FEE_CONFIDENCE_RANK = {name: idx for idx, name in enumerate(FEE_CONFIDENCE_ORDER)}
BALANCE_CONFIDENCE_RANK = {name: idx for idx, name in enumerate(BALANCE_CONFIDENCE_ORDER)}
QUOTE_MATCH_RANK = {name: idx for idx, name in enumerate(QUOTE_MATCH_ORDER)}


def normalize_support_status(raw: str | None) -> str:
    value = _norm(raw)
    if value in SUPPORT_STATUS_SET:
        return value
    if value in {"good", "ok", "true", "1", "yes"}:
        return "supported"
    if value in {"bad", "false", "0", "no"}:
        return "unsupported"
    return "unknown"


def normalize_fee_confidence(raw: str | None, provenance_hint: str | None = None) -> str:
    value = _norm(raw)
    if value in FEE_CONFIDENCE_SET:
        return value

    hint = _norm(provenance_hint)
    if value in {"fallback", "fallback_fee", "fallback_only"} or hint in {"fallback", "fallback_only"}:
        return "fallback_only"
    if value in {"config", "configured", "config_only", "configured_economic_fee"}:
        return "config_only"
    if value in {"venue_declared", "venue_default", "venue_specific", "symbol_override"}:
        return "venue_declared"
    if value in {"acct_verified", "account_verified"}:
        return "acct_verified"
    if value in {"chain_verified", "chain_pool_fee"}:
        return "chain_verified"

    if value in {"true", "1", "yes", "good"}:
        # Legacy positive flags are not enough evidence for higher levels.
        if hint in {"chain_verified", "chain_pool_fee"}:
            return "chain_verified"
        if hint in {"acct_verified", "account_verified"}:
            return "acct_verified"
        if hint in {"venue_declared", "venue_default", "venue_specific", "symbol_override"}:
            return "venue_declared"
        if hint in {"fallback", "fallback_only"}:
            return "fallback_only"
        return "config_only"
    if value in {"false", "0", "no", "bad"}:
        return "unknown"
    return "unknown"


def normalize_balance_confidence(raw: str | None, evidence_hint: str | None = None) -> str:
    value = _norm(raw)
    if value in BALANCE_CONFIDENCE_SET:
        return value

    hint = _norm(evidence_hint)
    if value in {"wallet_verified", "wallet"} or hint in {"wallet_verified", "wallet"}:
        return "wallet_verified"
    if value in {"venue_verified", "venue"} or hint in {"venue_verified", "venue"}:
        return "venue_verified"
    if value in {"db_inventory_ok", "db_inventory", "inventory"} or hint in {
        "db_inventory_ok",
        "db_inventory",
        "inventory",
    }:
        return "db_inventory_ok"
    if value in {"internal_ok", "internal"} or hint in {"internal_ok", "internal"}:
        return "internal_ok"
    if value in {"mismatch", "inventory_drift", "wallet_balance_mismatch"}:
        return "mismatch"

    if value in {"true", "1", "yes", "good"}:
        # Legacy positive flags should not overstate verification evidence.
        if hint in {"wallet_verified", "venue_verified", "db_inventory_ok", "internal_ok"}:
            return normalize_balance_confidence(hint)
        return "internal_ok"
    if value in {"false", "0", "no", "bad"}:
        if hint in {"inventory_drift", "wallet_balance_mismatch", "mismatch"}:
            return "mismatch"
        return "unknown"
    return "unknown"


def normalize_quote_match_status(raw: str | None) -> str:
    value = _norm(raw)
    if value in QUOTE_MATCH_SET:
        return value
    if value in {"true", "1", "yes", "good"}:
        return "matched"
    if value in {"false", "0", "no", "bad"}:
        return "mismatch"
    return "unknown"


def canonicalize_support_status(raw: str | None) -> str:
    return normalize_support_status(raw)


def canonicalize_fee_status(raw: str | None, provenance_hint: str | None = None) -> str:
    return normalize_fee_confidence(raw, provenance_hint=provenance_hint)


def canonicalize_balance_status(raw: str | None, evidence_hint: str | None = None) -> str:
    return normalize_balance_confidence(raw, evidence_hint=evidence_hint)


def canonicalize_quote_match_status(raw: str | None) -> str:
    return normalize_quote_match_status(raw)


def support_status_at_least(actual: str, required: str) -> bool:
    return SUPPORT_STATUS_RANK[normalize_support_status(actual)] >= SUPPORT_STATUS_RANK[
        normalize_support_status(required)
    ]


def fee_confidence_at_least(actual: str, required: str) -> bool:
    return FEE_CONFIDENCE_RANK[normalize_fee_confidence(actual)] >= FEE_CONFIDENCE_RANK[
        normalize_fee_confidence(required)
    ]


def balance_confidence_at_least(actual: str, required: str) -> bool:
    return BALANCE_CONFIDENCE_RANK[normalize_balance_confidence(actual)] >= BALANCE_CONFIDENCE_RANK[
        normalize_balance_confidence(required)
    ]


def quote_match_status_at_least(actual: str, required: str) -> bool:
    return QUOTE_MATCH_RANK[normalize_quote_match_status(actual)] >= QUOTE_MATCH_RANK[
        normalize_quote_match_status(required)
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


def _norm(raw: str | None) -> str:
    if raw is None:
        return ""
    return raw.strip().lower()
