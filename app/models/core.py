from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


DECIMAL_38_18 = Numeric(38, 18)
DECIMAL_18_8 = Numeric(18, 8)
DECIMAL_10_5 = Numeric(10, 5)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    mode: Mapped[str] = mapped_column(String(16), default="paper")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Route(Base):
    __tablename__ = "routes"
    __table_args__ = (
        UniqueConstraint("strategy", "name", name="uq_route_strategy_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    strategy: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    pair: Mapped[str] = mapped_column(String(64), index=True)
    direction: Mapped[str] = mapped_column(String(32), default="forward")
    venue_a: Mapped[str] = mapped_column(String(64))
    venue_b: Mapped[str] = mapped_column(String(64))
    pool_a: Mapped[str] = mapped_column(String(128))
    pool_b: Mapped[str] = mapped_column(String(128))
    router_a: Mapped[str] = mapped_column(String(128))
    router_b: Mapped[str] = mapped_column(String(128))
    # Deprecated compatibility fields. Use separated fee semantics below.
    fee_tier_a_bps: Mapped[int] = mapped_column(Integer, default=5)
    fee_tier_b_bps: Mapped[int] = mapped_column(Integer, default=5)
    quoter_fee_tier_a: Mapped[int] = mapped_column(Integer, default=5)
    quoter_fee_tier_b: Mapped[int] = mapped_column(Integer, default=5)
    pool_fee_tier_a: Mapped[int] = mapped_column(Integer, default=5)
    pool_fee_tier_b: Mapped[int] = mapped_column(Integer, default=5)
    economic_fee_bps_a: Mapped[int] = mapped_column(Integer, default=5)
    economic_fee_bps_b: Mapped[int] = mapped_column(Integer, default=5)
    max_notional_usdc: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("100"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_live_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class VenueConfig(Base):
    __tablename__ = "venue_configs"
    __table_args__ = (
        UniqueConstraint("venue", "symbol", name="uq_venue_symbol"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    venue: Mapped[str] = mapped_column(String(64), index=True)
    venue_type: Mapped[str] = mapped_column(String(16), index=True)  # cex/dex
    symbol: Mapped[str] = mapped_column(String(64), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    health_status: Mapped[str] = mapped_column(String(32), default="unknown")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class FeeProfile(Base):
    __tablename__ = "fee_profiles"
    __table_args__ = (
        UniqueConstraint("venue", "symbol", "maker_or_taker", name="uq_fee_profile"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    venue: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(64), default="*")
    maker_or_taker: Mapped[str] = mapped_column(String(16))
    fee_bps: Mapped[int] = mapped_column(Integer)
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        Index("ix_opportunities_route_time", "route_id", "created_at"),
        Index("ix_opportunities_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    strategy: Mapped[str] = mapped_column(String(64), index=True)
    mode: Mapped[str] = mapped_column(String(16), index=True)
    pair: Mapped[str] = mapped_column(String(64), index=True)
    direction: Mapped[str] = mapped_column(String(32))
    route_id: Mapped[str] = mapped_column(String(36), ForeignKey("routes.id"), index=True)
    venues: Mapped[str] = mapped_column(String(128))
    raw_edge_bps: Mapped[Decimal] = mapped_column(DECIMAL_10_5)
    modeled_edge_bps: Mapped[Decimal] = mapped_column(DECIMAL_10_5)
    expected_pnl_abs: Mapped[Decimal] = mapped_column(DECIMAL_18_8)
    expected_slippage_bps: Mapped[Decimal] = mapped_column(DECIMAL_10_5)
    gas_estimate_usdc: Mapped[Decimal] = mapped_column(DECIMAL_18_8)
    quote_age_seconds: Mapped[Decimal] = mapped_column(DECIMAL_10_5)
    status: Mapped[str] = mapped_column(String(32), default="detected")
    blocked_reason: Mapped[str] = mapped_column(String(128), default="")
    pool_health_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    persisted_seconds: Mapped[Decimal] = mapped_column(DECIMAL_10_5, default=Decimal("0"))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TradeAttempt(Base):
    __tablename__ = "trade_attempts"
    __table_args__ = (
        Index("ix_trade_attempts_route_time", "route_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(String(36), ForeignKey("opportunities.id"), index=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    route_id: Mapped[str] = mapped_column(String(36), ForeignKey("routes.id"), index=True)
    strategy: Mapped[str] = mapped_column(String(64), index=True)
    mode: Mapped[str] = mapped_column(String(16), index=True)
    input_amount: Mapped[Decimal] = mapped_column(DECIMAL_18_8)
    expected_output_amount: Mapped[Decimal] = mapped_column(DECIMAL_18_8)
    expected_pnl: Mapped[Decimal] = mapped_column(DECIMAL_18_8)
    status: Mapped[str] = mapped_column(String(32), default="submitted")
    blocked_reason: Mapped[str] = mapped_column(String(128), default="")
    failure_category: Mapped[str] = mapped_column(String(64), default="")
    is_fatal_failure: Mapped[bool] = mapped_column(Boolean, default=False)
    cooldown_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Execution(Base):
    __tablename__ = "executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    attempt_id: Mapped[str] = mapped_column(String(36), ForeignKey("trade_attempts.id"), index=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    route_id: Mapped[str] = mapped_column(String(36), ForeignKey("routes.id"), index=True)
    strategy: Mapped[str] = mapped_column(String(64), index=True)
    mode: Mapped[str] = mapped_column(String(16), index=True)
    tx_hash: Mapped[str] = mapped_column(String(132), default="", index=True)
    tx_status: Mapped[str] = mapped_column(String(32), default="pending")
    revert_reason: Mapped[str] = mapped_column(String(256), default="")
    failure_category: Mapped[str] = mapped_column(String(64), default="")
    is_fatal_failure: Mapped[bool] = mapped_column(Boolean, default=False)
    cooldown_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    input_amount: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    output_amount: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    expected_pnl: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    gas_used: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Balance(Base):
    __tablename__ = "balances"
    __table_args__ = (
        UniqueConstraint("venue", "token", name="uq_balance_venue_token"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    venue: Mapped[str] = mapped_column(String(64), index=True)
    token: Mapped[str] = mapped_column(String(64), index=True)
    available: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    reserved: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    usd_value: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    token: Mapped[str] = mapped_column(String(64), index=True)
    venue: Mapped[str] = mapped_column(String(64), index=True)
    available: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    reserved: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    usd_value: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    target_allocation_pct: Mapped[Decimal] = mapped_column(DECIMAL_10_5, default=Decimal("0"))
    deviation_pct: Mapped[Decimal] = mapped_column(DECIMAL_10_5, default=Decimal("0"))


class HealthMetric(Base):
    __tablename__ = "health_metrics"
    __table_args__ = (
        Index("ix_health_metrics_name_time", "name", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[Decimal] = mapped_column(DECIMAL_18_8)
    status: Mapped[str] = mapped_column(String(32), default="ok")
    labels_json: Mapped[str] = mapped_column(Text, default="{}")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    level: Mapped[str] = mapped_column(String(16), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str] = mapped_column(Text, default="")


class KillSwitchEvent(Base):
    __tablename__ = "kill_switch_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)  # global/strategy/route/pair
    scope_ref: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(32))  # trigger/release
    reason: Mapped[str] = mapped_column(String(256))


class ConfigAuditLog(Base):
    __tablename__ = "config_audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(64), default="system")
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(128))
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    notes: Mapped[str] = mapped_column(Text, default="")


class RouteRuntimeState(Base):
    __tablename__ = "route_runtime_states"
    __table_args__ = (
        UniqueConstraint("route_id", name="uq_route_runtime_state_route"),
        Index("ix_route_runtime_state_updated_at", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    route_id: Mapped[str] = mapped_column(String(36), ForeignKey("routes.id"), index=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_category: Mapped[str] = mapped_column(String(64), default="")
    last_failure_reason: Mapped[str] = mapped_column(String(256), default="")
    last_failure_fatal: Mapped[bool] = mapped_column(Boolean, default=False)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_losses: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RuntimeControl(Base):
    __tablename__ = "runtime_controls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    mode: Mapped[str] = mapped_column(String(16), default="paper")
    global_pause: Mapped[bool] = mapped_column(Boolean, default=False)
    strategy_pause: Mapped[bool] = mapped_column(Boolean, default=False)
    pair_pause: Mapped[bool] = mapped_column(Boolean, default=False)
    route_pause: Mapped[bool] = mapped_column(Boolean, default=False)
    live_guard_armed: Mapped[bool] = mapped_column(Boolean, default=False)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"
    __table_args__ = (
        Index("ix_market_snapshots_time", "timestamp"),
        Index("ix_market_snapshots_route", "route_id", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    strategy: Mapped[str] = mapped_column(String(64), index=True)
    route_id: Mapped[str] = mapped_column(String(36), ForeignKey("routes.id"), index=True)
    pair: Mapped[str] = mapped_column(String(64), index=True)
    venue: Mapped[str] = mapped_column(String(64), index=True)
    context: Mapped[str] = mapped_column(String(64), default="")
    bid: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    ask: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    amount_in: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    quoted_amount_out: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    liquidity_usd: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    gas_gwei: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    quote_age_seconds: Mapped[Decimal] = mapped_column(DECIMAL_10_5, default=Decimal("0"))
    source_type: Mapped[str] = mapped_column(String(16), default="mock")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class RouteHealthSnapshot(Base):
    __tablename__ = "route_health_snapshots"
    __table_args__ = (
        Index("ix_route_health_snapshots_route_time", "route_id", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    strategy: Mapped[str] = mapped_column(String(64), index=True)
    route_id: Mapped[str] = mapped_column(String(36), ForeignKey("routes.id"), index=True)
    pair: Mapped[str] = mapped_column(String(64), index=True)
    rpc_latency_ms: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    rpc_error_rate_5m: Mapped[Decimal] = mapped_column(DECIMAL_10_5, default=Decimal("0"))
    db_latency_ms: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    quote_latency_ms: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    market_data_staleness_seconds: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    contract_revert_rate: Mapped[Decimal] = mapped_column(DECIMAL_10_5, default=Decimal("0"))
    alert_send_success_rate: Mapped[Decimal] = mapped_column(DECIMAL_10_5, default=Decimal("0"))
    fee_known_status: Mapped[str] = mapped_column(String(16), default="unknown")
    quote_match_status: Mapped[str] = mapped_column(String(16), default="unknown")
    balance_match_status: Mapped[str] = mapped_column(String(16), default="unknown")
    support_status: Mapped[str] = mapped_column(String(16), default="unknown")
    cooldown_active: Mapped[bool] = mapped_column(Boolean, default=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ParameterSet(Base):
    __tablename__ = "parameter_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    strategy: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    __table_args__ = (
        Index("ix_backtest_runs_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(64), index=True, default=new_id)
    strategy: Mapped[str] = mapped_column(String(64), index=True)
    route_id: Mapped[str] = mapped_column(String(36), ForeignKey("routes.id"), index=True)
    pair: Mapped[str] = mapped_column(String(64), index=True)
    parameter_set_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("parameter_sets.id"), nullable=True)
    start_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BacktestResult(Base):
    __tablename__ = "backtest_results"
    __table_args__ = (
        UniqueConstraint("backtest_run_id", name="uq_backtest_result_run"),
        Index("ix_backtest_results_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    backtest_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("backtest_runs.id"), index=True)
    signals: Mapped[int] = mapped_column(Integer, default=0)
    eligible_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    simulated_pnl: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    hit_rate: Mapped[Decimal] = mapped_column(DECIMAL_10_5, default=Decimal("0"))
    avg_modeled_edge_bps: Mapped[Decimal] = mapped_column(DECIMAL_10_5, default=Decimal("0"))
    avg_realized_like_pnl: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    max_drawdown: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    worst_sequence: Mapped[int] = mapped_column(Integer, default=0)
    missed_opportunities: Mapped[int] = mapped_column(Integer, default=0)
    blocked_reason_json: Mapped[str] = mapped_column(Text, default="{}")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"
    __table_args__ = (
        Index("ix_backtest_trades_run_time", "backtest_run_id", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    backtest_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("backtest_runs.id"), index=True)
    route_id: Mapped[str] = mapped_column(String(36), ForeignKey("routes.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    status: Mapped[str] = mapped_column(String(32), default="blocked")
    blocked_reason: Mapped[str] = mapped_column(String(128), default="")
    modeled_edge_bps: Mapped[Decimal] = mapped_column(DECIMAL_10_5, default=Decimal("0"))
    expected_pnl: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    simulated_pnl: Mapped[Decimal] = mapped_column(DECIMAL_18_8, default=Decimal("0"))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
