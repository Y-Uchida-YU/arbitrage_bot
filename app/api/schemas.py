from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime


class ControlRequest(BaseModel):
    token: str = Field(min_length=1)


class EnableRouteRequest(ControlRequest):
    route_id: str


class DisableRouteRequest(ControlRequest):
    route_id: str


class ModeSwitchRequest(ControlRequest):
    target_mode: str
    live_confirmation_token: str | None = None


class VenueControlRequest(ControlRequest):
    venue: str


class CooldownControlRequest(ControlRequest):
    route_id: str | None = None


class StrategyControlRequest(ControlRequest):
    strategy: str


class OpportunityOut(BaseModel):
    id: str
    timestamp: datetime
    strategy: str
    pair: str
    direction: str
    venues: str
    raw_edge_bps: Decimal
    modeled_edge_bps: Decimal
    expected_pnl_abs: Decimal
    expected_slippage_bps: Decimal
    gas_estimate_usdc: Decimal
    quote_age_seconds: Decimal
    persisted_seconds: Decimal
    pool_health_ok: bool
    status: str
    blocked_reason: str
    payload_json: str
    quote_source: str = ""
    risk_checks: str = ""
    quote_unavailable_reason: str = ""


class TradeOut(BaseModel):
    id: str
    created_at: datetime
    strategy: str
    mode: str
    route_id: str
    input_amount: Decimal
    expected_output_amount: Decimal
    expected_pnl: Decimal
    status: str
    blocked_reason: str
    failure_category: str
    is_fatal_failure: bool
    cooldown_triggered: bool
    notes: str


class ExecutionOut(BaseModel):
    id: str
    created_at: datetime
    strategy: str
    mode: str
    route_id: str
    tx_hash: str
    tx_status: str
    revert_reason: str
    failure_category: str
    is_fatal_failure: bool
    cooldown_triggered: bool
    input_amount: Decimal
    output_amount: Decimal
    expected_pnl: Decimal
    realized_pnl: Decimal
    gas_used: Decimal
    latency_ms: int
    notes: str


class BalanceOut(BaseModel):
    id: str
    venue: str
    token: str
    available: Decimal
    reserved: Decimal
    total: Decimal
    usd_value: Decimal
    updated_at: datetime


class InventoryOut(BaseModel):
    id: str
    timestamp: datetime
    token: str
    venue: str
    available: Decimal
    reserved: Decimal
    total: Decimal
    usd_value: Decimal
    target_allocation_pct: Decimal
    deviation_pct: Decimal


class MetricOut(BaseModel):
    id: str
    timestamp: datetime
    name: str
    value: Decimal
    status: str
    labels_json: str


class MarketSnapshotOut(BaseModel):
    id: str
    timestamp: datetime
    strategy: str
    route_id: str
    pair: str
    venue: str
    context: str
    bid: Decimal
    ask: Decimal
    amount_in: Decimal
    quoted_amount_out: Decimal
    liquidity_usd: Decimal
    gas_gwei: Decimal
    quote_age_seconds: Decimal
    source_type: str
    metadata_json: str


class RouteHealthSnapshotOut(BaseModel):
    id: str
    timestamp: datetime
    strategy: str
    route_id: str
    pair: str
    rpc_latency_ms: Decimal
    rpc_error_rate_5m: Decimal
    db_latency_ms: Decimal
    quote_latency_ms: Decimal
    market_data_staleness_seconds: Decimal
    contract_revert_rate: Decimal
    alert_send_success_rate: Decimal
    fee_known_status: str
    quote_match_status: str
    balance_match_status: str
    support_status: str
    cooldown_active: bool
    paused: bool
    metadata_json: str


class RouteOut(BaseModel):
    id: str
    strategy: str
    name: str
    pair: str
    direction: str
    venue_a: str
    venue_b: str
    enabled: bool
    kill_switch: bool
    is_live_allowed: bool
    quoter_fee_tier_a: int
    quoter_fee_tier_b: int
    pool_fee_tier_a: int
    pool_fee_tier_b: int
    economic_fee_bps_a: int
    economic_fee_bps_b: int


class CooldownOut(BaseModel):
    route_id: str
    cooldown_until: str
    cooldown_remaining_seconds: int
    consecutive_failures: int
    consecutive_losses: int
    last_failure_category: str
    last_failure_reason: str
    last_failure_fatal: bool
    last_failure_at: str
    route_paused: bool


class BacktestRunRequest(ControlRequest):
    strategy: str
    route_id: str
    pair: str
    start_ts: datetime
    end_ts: datetime
    parameter_set_id: str | None = None
    notes: str = ""
    replay_mode: str = "opportunities"


class BacktestRunOut(BaseModel):
    id: str
    run_id: str
    strategy: str
    route_id: str
    pair: str
    parameter_set_id: str | None
    start_ts: datetime
    end_ts: datetime
    status: str
    notes: str
    created_at: datetime
    finished_at: datetime | None


class BacktestResultOut(BaseModel):
    id: str
    backtest_run_id: str
    signals: int
    eligible_count: int
    blocked_count: int
    simulated_pnl: Decimal
    hit_rate: Decimal
    avg_modeled_edge_bps: Decimal
    avg_realized_like_pnl: Decimal
    max_drawdown: Decimal
    worst_sequence: int
    missed_opportunities: int
    replay_mode: str = "unknown"
    blocked_reason_json: str
    metadata_json: str
    created_at: datetime


class BacktestTradeOut(BaseModel):
    id: str
    backtest_run_id: str
    route_id: str
    timestamp: datetime
    status: str
    blocked_reason: str
    modeled_edge_bps: Decimal
    expected_pnl: Decimal
    simulated_pnl: Decimal
    metadata_json: str


class RouteReadinessOut(BaseModel):
    route_id: str
    strategy: str
    support_status: str
    fee_known_status: str
    balance_match_status: str
    quote_match_status: str
    cooldown_active: bool
    fatal_paused: bool
    observation_count: int
    last_observation_at: datetime | None
    quote_unavailable_rate: Decimal
    recent_blocked_reasons: list[dict[str, object]]
    backtest_run_count: int
    last_backtest_status: str
    last_backtest_pnl: Decimal
    last_backtest_mode: str
    readiness_grade: str
    readiness_blockers: list[str]
    human_action_items: list[str]


class ReadinessSummaryOut(BaseModel):
    red_count: int
    yellow_count: int
    green_count: int
    total_routes: int
    latest_backtest_mode: str


class KpiEvaluationOut(BaseModel):
    name: str
    status: str
    value: str
    threshold: str
    critical: bool
    note: str = ""


class CommissioningRouteOut(BaseModel):
    route_id: str
    strategy: str
    route_type: str
    phase: str
    readiness_grade: str
    promotion_gate_status: str
    observation_window_days: Decimal
    market_snapshot_count: int
    opportunity_count: int
    quote_unavailable_rate: Decimal
    health_unknown_rate: Decimal
    fee_unverified_rate: Decimal
    balance_unverified_rate: Decimal
    quote_mismatch_rate: Decimal
    backtest_run_count_total: int
    backtest_run_count_market_snapshots: int
    backtest_run_count_opportunities: int
    fatal_pause_count: int
    cooldown_event_count: int
    blocked_reason_top_n: list[dict[str, object]]
    latest_backtest_pnl: Decimal
    median_backtest_pnl: Decimal
    worst_backtest_drawdown: Decimal
    latest_readiness_grade: str
    kpi_evaluations: list[KpiEvaluationOut]
    gate_blockers: list[str]
    human_action_items: list[str]


class CommissioningSummaryOut(BaseModel):
    total_routes: int
    routes_not_ready: int
    routes_observation_ready: int
    routes_review_ready: int
    routes_promotion_blocked: int
    live_intent_routes: int
    shadow_routes: int
    latest_backtest_mode: str
    phase_counts: dict[str, int]
    gate_fail_route_count: int
    gate_warn_route_count: int


class CommissioningRankingOut(BaseModel):
    rank: int
    route_id: str
    strategy: str
    route_type: str
    phase: str
    promotion_gate_status: str
    readiness_grade: str
    score: Decimal
    gate_blockers: list[str]
    human_action_items: list[str]
    key_kpis: dict[str, Decimal | int]
