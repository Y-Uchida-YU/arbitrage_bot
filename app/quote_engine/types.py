from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class QuoteLeg:
    venue: str
    pool_id: str
    token_in: str
    token_out: str
    amount_in: Decimal
    amount_out: Decimal
    fee_bps: int
    gas_units: int
    quote_ts: datetime
    slippage_bps: Decimal = Decimal("0")


@dataclass(slots=True)
class RouteQuote:
    route_id: str
    strategy: str
    pair: str
    direction: str
    initial_amount: Decimal
    final_amount: Decimal
    raw_spread_amount: Decimal
    raw_edge_bps: Decimal
    modeled_net_edge_amount: Decimal
    modeled_net_edge_bps: Decimal
    expected_slippage_bps: Decimal
    gas_cost_usdc: Decimal
    quote_age_seconds: Decimal
    all_costs: Decimal
    persisted_seconds: Decimal
    status: str = "detected"
    blocked_reason: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class OpportunityDecision:
    tradable: bool
    blocked_reason: str
    checks: dict[str, bool]