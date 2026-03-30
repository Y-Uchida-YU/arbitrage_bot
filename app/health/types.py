from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class RollingStats:
    p50: Decimal = Decimal("0")
    p90: Decimal = Decimal("0")
    latest: Decimal = Decimal("0")


@dataclass(slots=True)
class VenueQuoteHealth:
    venue: str
    supported: bool
    last_success_ts: datetime | None
    quote_unavailable_count_5m: int
    degraded_reason: str = ""


@dataclass(slots=True)
class CommissioningHealthSnapshot:
    rpc_latency_ms: Decimal
    rpc_error_rate_5m: Decimal
    db_latency_ms: Decimal
    quote_latency_ms: Decimal
    gas_now: Decimal
    gas_p50: Decimal
    gas_p90: Decimal
    liquidity_change_pct: Decimal
    quote_age_seconds: Decimal
    alert_send_success_rate: Decimal
    contract_revert_rate: Decimal
    market_data_staleness_seconds: Decimal
    heartbeat_lag_seconds: Decimal
    route_smaller_pool_liquidity_usdc: Decimal
    quote_unavailable_venues: list[str] = field(default_factory=list)