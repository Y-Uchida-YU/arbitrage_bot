"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="paper"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_strategies_name", "strategies", ["name"])

    op.create_table(
        "routes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("pair", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("venue_a", sa.String(length=64), nullable=False),
        sa.Column("venue_b", sa.String(length=64), nullable=False),
        sa.Column("pool_a", sa.String(length=128), nullable=False),
        sa.Column("pool_b", sa.String(length=128), nullable=False),
        sa.Column("router_a", sa.String(length=128), nullable=False),
        sa.Column("router_b", sa.String(length=128), nullable=False),
        sa.Column("fee_tier_a_bps", sa.Integer(), nullable=False),
        sa.Column("fee_tier_b_bps", sa.Integer(), nullable=False),
        sa.Column("max_notional_usdc", sa.Numeric(18, 8), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_live_allowed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("kill_switch", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("strategy", "name", name="uq_route_strategy_name"),
    )
    op.create_index("ix_routes_pair", "routes", ["pair"])

    op.create_table(
        "venue_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("venue", sa.String(length=64), nullable=False),
        sa.Column("venue_type", sa.String(length=16), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("health_status", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("venue", "symbol", name="uq_venue_symbol"),
    )

    op.create_table(
        "fee_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("venue", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("maker_or_taker", sa.String(length=16), nullable=False),
        sa.Column("fee_bps", sa.Integer(), nullable=False),
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("venue", "symbol", "maker_or_taker", name="uq_fee_profile"),
    )

    op.create_table(
        "opportunities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("pair", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("route_id", sa.String(length=36), sa.ForeignKey("routes.id"), nullable=False),
        sa.Column("venues", sa.String(length=128), nullable=False),
        sa.Column("raw_edge_bps", sa.Numeric(10, 5), nullable=False),
        sa.Column("modeled_edge_bps", sa.Numeric(10, 5), nullable=False),
        sa.Column("expected_pnl_abs", sa.Numeric(18, 8), nullable=False),
        sa.Column("expected_slippage_bps", sa.Numeric(10, 5), nullable=False),
        sa.Column("gas_estimate_usdc", sa.Numeric(18, 8), nullable=False),
        sa.Column("quote_age_seconds", sa.Numeric(10, 5), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("blocked_reason", sa.String(length=128), nullable=False),
        sa.Column("pool_health_ok", sa.Boolean(), nullable=False),
        sa.Column("persisted_seconds", sa.Numeric(10, 5), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_opportunities_route_time", "opportunities", ["route_id", "created_at"])
    op.create_index("ix_opportunities_status", "opportunities", ["status"])

    op.create_table(
        "trade_attempts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("opportunity_id", sa.String(length=36), sa.ForeignKey("opportunities.id"), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("route_id", sa.String(length=36), sa.ForeignKey("routes.id"), nullable=False),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("input_amount", sa.Numeric(18, 8), nullable=False),
        sa.Column("expected_output_amount", sa.Numeric(18, 8), nullable=False),
        sa.Column("expected_pnl", sa.Numeric(18, 8), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("blocked_reason", sa.String(length=128), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trade_attempts_route_time", "trade_attempts", ["route_id", "created_at"])

    op.create_table(
        "executions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("attempt_id", sa.String(length=36), sa.ForeignKey("trade_attempts.id"), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("route_id", sa.String(length=36), sa.ForeignKey("routes.id"), nullable=False),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("tx_hash", sa.String(length=132), nullable=False),
        sa.Column("tx_status", sa.String(length=32), nullable=False),
        sa.Column("revert_reason", sa.String(length=256), nullable=False),
        sa.Column("input_amount", sa.Numeric(18, 8), nullable=False),
        sa.Column("output_amount", sa.Numeric(18, 8), nullable=False),
        sa.Column("expected_pnl", sa.Numeric(18, 8), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(18, 8), nullable=False),
        sa.Column("gas_used", sa.Numeric(18, 8), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_executions_tx_hash", "executions", ["tx_hash"])

    op.create_table(
        "balances",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("venue", sa.String(length=64), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("available", sa.Numeric(18, 8), nullable=False),
        sa.Column("reserved", sa.Numeric(18, 8), nullable=False),
        sa.Column("total", sa.Numeric(18, 8), nullable=False),
        sa.Column("usd_value", sa.Numeric(18, 8), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("venue", "token", name="uq_balance_venue_token"),
    )

    op.create_table(
        "inventory_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("venue", sa.String(length=64), nullable=False),
        sa.Column("available", sa.Numeric(18, 8), nullable=False),
        sa.Column("reserved", sa.Numeric(18, 8), nullable=False),
        sa.Column("total", sa.Numeric(18, 8), nullable=False),
        sa.Column("usd_value", sa.Numeric(18, 8), nullable=False),
        sa.Column("target_allocation_pct", sa.Numeric(10, 5), nullable=False),
        sa.Column("deviation_pct", sa.Numeric(10, 5), nullable=False),
    )

    op.create_table(
        "health_metrics",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Numeric(18, 8), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("labels_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_health_metrics_name_time", "health_metrics", ["name", "timestamp"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("sent", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
    )

    op.create_table(
        "kill_switch_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("scope_ref", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=256), nullable=False),
    )

    op.create_table(
        "config_audit_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=128), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=False),
        sa.Column("after_json", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
    )

    op.create_table(
        "runtime_controls",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("global_pause", sa.Boolean(), nullable=False),
        sa.Column("strategy_pause", sa.Boolean(), nullable=False),
        sa.Column("pair_pause", sa.Boolean(), nullable=False),
        sa.Column("route_pause", sa.Boolean(), nullable=False),
        sa.Column("live_guard_armed", sa.Boolean(), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("runtime_controls")
    op.drop_table("config_audit_logs")
    op.drop_table("kill_switch_events")
    op.drop_table("alerts")
    op.drop_index("ix_health_metrics_name_time", table_name="health_metrics")
    op.drop_table("health_metrics")
    op.drop_table("inventory_snapshots")
    op.drop_table("balances")
    op.drop_index("ix_executions_tx_hash", table_name="executions")
    op.drop_table("executions")
    op.drop_index("ix_trade_attempts_route_time", table_name="trade_attempts")
    op.drop_table("trade_attempts")
    op.drop_index("ix_opportunities_status", table_name="opportunities")
    op.drop_index("ix_opportunities_route_time", table_name="opportunities")
    op.drop_table("opportunities")
    op.drop_table("fee_profiles")
    op.drop_table("venue_configs")
    op.drop_index("ix_routes_pair", table_name="routes")
    op.drop_table("routes")
    op.drop_index("ix_strategies_name", table_name="strategies")
    op.drop_table("strategies")