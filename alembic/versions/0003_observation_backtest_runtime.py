"""fee separation, runtime persistence, observation and backtest tables

Revision ID: 0003_observation_backtest_runtime
Revises: 0002_failure_fields
Create Date: 2026-03-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_observation_backtest_runtime"
down_revision = "0002_failure_fields"
branch_labels = None
depends_on = None


DECIMAL_18_8 = sa.Numeric(18, 8)
DECIMAL_10_5 = sa.Numeric(10, 5)


def upgrade() -> None:
    op.add_column("routes", sa.Column("quoter_fee_tier_a", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("routes", sa.Column("quoter_fee_tier_b", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("routes", sa.Column("pool_fee_tier_a", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("routes", sa.Column("pool_fee_tier_b", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("routes", sa.Column("economic_fee_bps_a", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("routes", sa.Column("economic_fee_bps_b", sa.Integer(), nullable=False, server_default="5"))

    op.execute(
        """
        UPDATE routes
        SET
            quoter_fee_tier_a = fee_tier_a_bps,
            quoter_fee_tier_b = fee_tier_b_bps,
            pool_fee_tier_a = fee_tier_a_bps,
            pool_fee_tier_b = fee_tier_b_bps,
            economic_fee_bps_a = fee_tier_a_bps,
            economic_fee_bps_b = fee_tier_b_bps
        """
    )

    op.create_table(
        "route_runtime_states",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("route_id", sa.String(length=36), sa.ForeignKey("routes.id"), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_category", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("last_failure_reason", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("last_failure_fatal", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_losses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("route_id", name="uq_route_runtime_state_route"),
    )
    op.create_index("ix_route_runtime_state_updated_at", "route_runtime_states", ["updated_at"])

    op.create_table(
        "market_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("route_id", sa.String(length=36), sa.ForeignKey("routes.id"), nullable=False),
        sa.Column("pair", sa.String(length=64), nullable=False),
        sa.Column("venue", sa.String(length=64), nullable=False),
        sa.Column("context", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("bid", DECIMAL_18_8, nullable=False),
        sa.Column("ask", DECIMAL_18_8, nullable=False),
        sa.Column("amount_in", DECIMAL_18_8, nullable=False),
        sa.Column("quoted_amount_out", DECIMAL_18_8, nullable=False),
        sa.Column("liquidity_usd", DECIMAL_18_8, nullable=False),
        sa.Column("gas_gwei", DECIMAL_18_8, nullable=False),
        sa.Column("quote_age_seconds", DECIMAL_10_5, nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False, server_default="mock"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_market_snapshots_time", "market_snapshots", ["timestamp"])
    op.create_index("ix_market_snapshots_route", "market_snapshots", ["route_id", "timestamp"])

    op.create_table(
        "route_health_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("route_id", sa.String(length=36), sa.ForeignKey("routes.id"), nullable=False),
        sa.Column("pair", sa.String(length=64), nullable=False),
        sa.Column("rpc_latency_ms", DECIMAL_18_8, nullable=False),
        sa.Column("rpc_error_rate_5m", DECIMAL_10_5, nullable=False),
        sa.Column("db_latency_ms", DECIMAL_18_8, nullable=False),
        sa.Column("quote_latency_ms", DECIMAL_18_8, nullable=False),
        sa.Column("market_data_staleness_seconds", DECIMAL_18_8, nullable=False),
        sa.Column("contract_revert_rate", DECIMAL_10_5, nullable=False),
        sa.Column("alert_send_success_rate", DECIMAL_10_5, nullable=False),
        sa.Column("fee_known_status", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("quote_match_status", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("balance_match_status", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("support_status", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("cooldown_active", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_route_health_snapshots_route_time", "route_health_snapshots", ["route_id", "timestamp"])

    op.create_table(
        "parameter_sets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("params_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_parameter_sets_strategy", "parameter_sets", ["strategy"])

    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("route_id", sa.String(length=36), sa.ForeignKey("routes.id"), nullable=False),
        sa.Column("pair", sa.String(length=64), nullable=False),
        sa.Column("parameter_set_id", sa.String(length=36), sa.ForeignKey("parameter_sets.id"), nullable=True),
        sa.Column("start_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_backtest_runs_created", "backtest_runs", ["created_at"])

    op.create_table(
        "backtest_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("backtest_run_id", sa.String(length=36), sa.ForeignKey("backtest_runs.id"), nullable=False),
        sa.Column("signals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("eligible_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("simulated_pnl", DECIMAL_18_8, nullable=False),
        sa.Column("hit_rate", DECIMAL_10_5, nullable=False),
        sa.Column("avg_modeled_edge_bps", DECIMAL_10_5, nullable=False),
        sa.Column("avg_realized_like_pnl", DECIMAL_18_8, nullable=False),
        sa.Column("max_drawdown", DECIMAL_18_8, nullable=False),
        sa.Column("worst_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missed_opportunities", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_reason_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("backtest_run_id", name="uq_backtest_result_run"),
    )
    op.create_index("ix_backtest_results_created", "backtest_results", ["created_at"])

    op.create_table(
        "backtest_trades",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("backtest_run_id", sa.String(length=36), sa.ForeignKey("backtest_runs.id"), nullable=False),
        sa.Column("route_id", sa.String(length=36), sa.ForeignKey("routes.id"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="blocked"),
        sa.Column("blocked_reason", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("modeled_edge_bps", DECIMAL_10_5, nullable=False),
        sa.Column("expected_pnl", DECIMAL_18_8, nullable=False),
        sa.Column("simulated_pnl", DECIMAL_18_8, nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_backtest_trades_run_time", "backtest_trades", ["backtest_run_id", "timestamp"])


def downgrade() -> None:
    op.drop_index("ix_backtest_trades_run_time", table_name="backtest_trades")
    op.drop_table("backtest_trades")

    op.drop_index("ix_backtest_results_created", table_name="backtest_results")
    op.drop_table("backtest_results")

    op.drop_index("ix_backtest_runs_created", table_name="backtest_runs")
    op.drop_table("backtest_runs")

    op.drop_index("ix_parameter_sets_strategy", table_name="parameter_sets")
    op.drop_table("parameter_sets")

    op.drop_index("ix_route_health_snapshots_route_time", table_name="route_health_snapshots")
    op.drop_table("route_health_snapshots")

    op.drop_index("ix_market_snapshots_route", table_name="market_snapshots")
    op.drop_index("ix_market_snapshots_time", table_name="market_snapshots")
    op.drop_table("market_snapshots")

    op.drop_index("ix_route_runtime_state_updated_at", table_name="route_runtime_states")
    op.drop_table("route_runtime_states")

    op.drop_column("routes", "economic_fee_bps_b")
    op.drop_column("routes", "economic_fee_bps_a")
    op.drop_column("routes", "pool_fee_tier_b")
    op.drop_column("routes", "pool_fee_tier_a")
    op.drop_column("routes", "quoter_fee_tier_b")
    op.drop_column("routes", "quoter_fee_tier_a")
