from app.utils.confidence import (
    balance_confidence_at_least,
    fee_confidence_at_least,
    normalize_balance_confidence,
    normalize_fee_confidence,
    normalize_quote_match_status,
    normalize_support_status,
)


def test_fee_confidence_classification_order() -> None:
    assert normalize_fee_confidence("fallback_only") == "fallback_only"
    assert normalize_fee_confidence("CHAIN_VERIFIED") == "chain_verified"
    assert normalize_fee_confidence("not-known") == "unknown"
    assert fee_confidence_at_least("chain_verified", "venue_declared")
    assert not fee_confidence_at_least("fallback_only", "venue_declared")


def test_balance_confidence_classification_order() -> None:
    assert normalize_balance_confidence("db_inventory_ok") == "db_inventory_ok"
    assert normalize_balance_confidence("mismatch") == "mismatch"
    assert normalize_balance_confidence("something_else") == "unknown"
    assert balance_confidence_at_least("wallet_verified", "db_inventory_ok")
    assert not balance_confidence_at_least("internal_ok", "wallet_verified")


def test_legacy_values_normalize_conservatively() -> None:
    assert normalize_support_status("good") == "supported"
    assert normalize_support_status("false") == "unsupported"

    assert normalize_quote_match_status("yes") == "matched"
    assert normalize_quote_match_status("bad") == "mismatch"

    # fee/balance legacy positives are conservative and never overstate verification.
    assert normalize_fee_confidence("good") == "config_only"
    assert normalize_balance_confidence("good") == "internal_ok"

    # legacy negatives should remain fail-safe.
    assert normalize_fee_confidence("bad") == "unknown"
    assert normalize_balance_confidence("bad") in {"unknown", "mismatch"}
