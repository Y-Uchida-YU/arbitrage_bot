"""canonicalize confidence/support statuses in route_health_snapshots

Revision ID: 0004_canonical_status_normalization
Revises: 0003_observation_backtest_runtime
Create Date: 2026-03-31
"""

from __future__ import annotations

from alembic import op


revision = "0004_canonical_status_normalization"
down_revision = "0003_observation_backtest_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE route_health_snapshots
        SET support_status = CASE
            WHEN lower(trim(coalesce(support_status, ''))) IN ('supported', 'good', 'ok', 'true', '1', 'yes') THEN 'supported'
            WHEN lower(trim(coalesce(support_status, ''))) IN ('unsupported', 'bad', 'false', '0', 'no') THEN 'unsupported'
            ELSE 'unknown'
        END
        """
    )

    op.execute(
        """
        UPDATE route_health_snapshots
        SET fee_known_status = CASE
            WHEN lower(trim(coalesce(fee_known_status, ''))) IN ('unknown', '') THEN 'unknown'
            WHEN lower(trim(coalesce(fee_known_status, ''))) = 'fallback_only' THEN 'fallback_only'
            WHEN lower(trim(coalesce(fee_known_status, ''))) IN ('fallback', 'fallback_fee') THEN 'fallback_only'
            WHEN lower(trim(coalesce(fee_known_status, ''))) = 'config_only' THEN 'config_only'
            WHEN lower(trim(coalesce(fee_known_status, ''))) IN ('config', 'configured', 'configured_economic_fee') THEN 'config_only'
            WHEN lower(trim(coalesce(fee_known_status, ''))) = 'venue_declared' THEN 'venue_declared'
            WHEN lower(trim(coalesce(fee_known_status, ''))) IN ('venue_default', 'venue_specific', 'symbol_override') THEN 'venue_declared'
            WHEN lower(trim(coalesce(fee_known_status, ''))) IN ('acct_verified', 'account_verified') THEN 'acct_verified'
            WHEN lower(trim(coalesce(fee_known_status, ''))) IN ('chain_verified', 'chain_pool_fee') THEN 'chain_verified'
            WHEN lower(trim(coalesce(fee_known_status, ''))) IN ('good', 'true', '1', 'yes') THEN 'config_only'
            WHEN lower(trim(coalesce(fee_known_status, ''))) IN ('bad', 'false', '0', 'no') THEN 'unknown'
            ELSE 'unknown'
        END
        """
    )

    op.execute(
        """
        UPDATE route_health_snapshots
        SET balance_match_status = CASE
            WHEN lower(trim(coalesce(balance_match_status, ''))) IN ('unknown', '') THEN 'unknown'
            WHEN lower(trim(coalesce(balance_match_status, ''))) = 'venue_verified' THEN 'venue_verified'
            WHEN lower(trim(coalesce(balance_match_status, ''))) IN ('venue') THEN 'venue_verified'
            WHEN lower(trim(coalesce(balance_match_status, ''))) = 'wallet_verified' THEN 'wallet_verified'
            WHEN lower(trim(coalesce(balance_match_status, ''))) IN ('wallet') THEN 'wallet_verified'
            WHEN lower(trim(coalesce(balance_match_status, ''))) = 'db_inventory_ok' THEN 'db_inventory_ok'
            WHEN lower(trim(coalesce(balance_match_status, ''))) IN ('db_inventory', 'inventory') THEN 'db_inventory_ok'
            WHEN lower(trim(coalesce(balance_match_status, ''))) = 'internal_ok' THEN 'internal_ok'
            WHEN lower(trim(coalesce(balance_match_status, ''))) IN ('internal', 'good', 'true', '1', 'yes') THEN 'internal_ok'
            WHEN lower(trim(coalesce(balance_match_status, ''))) IN ('mismatch', 'inventory_drift', 'wallet_balance_mismatch', 'bad', 'false', '0', 'no') THEN 'mismatch'
            ELSE 'unknown'
        END
        """
    )

    op.execute(
        """
        UPDATE route_health_snapshots
        SET quote_match_status = CASE
            WHEN lower(trim(coalesce(quote_match_status, ''))) IN ('matched', 'good', 'true', '1', 'yes') THEN 'matched'
            WHEN lower(trim(coalesce(quote_match_status, ''))) IN ('mismatch', 'bad', 'false', '0', 'no') THEN 'mismatch'
            ELSE 'unknown'
        END
        """
    )


def downgrade() -> None:
    # Canonicalization is intentionally one-way for safety.
    pass

