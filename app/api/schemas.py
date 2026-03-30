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
    status: str
    blocked_reason: str


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
