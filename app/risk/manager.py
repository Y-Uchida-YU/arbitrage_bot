from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.config.settings import RunMode, Settings
from app.quote_engine.types import OpportunityDecision, RouteQuote
from app.utils.confidence import (
    balance_confidence_at_least,
    fee_confidence_at_least,
    normalize_balance_confidence,
    normalize_fee_confidence,
    normalize_quote_match_status,
)


@dataclass(slots=True)
class HealthSnapshot:
    rpc_error_rate_5m: Decimal = Decimal("0")
    gas_now: Decimal = Decimal("0")
    gas_p90: Decimal = Decimal("1")
    liquidity_change_pct: Decimal = Decimal("0")
    quote_stale_seconds: Decimal = Decimal("0")
    health_age_seconds: Decimal = Decimal("999")
    alert_failures: int = 0
    db_reachable: bool = False
    db_known: bool = False
    rpc_reachable: bool = False
    rpc_known: bool = False
    signing_ok: bool = False
    signing_known: bool = False
    fee_known: bool = False
    fee_known_status: str = "unknown"
    fee_provenance: str = ""
    quote_match: bool = False
    quote_match_known: bool = False
    quote_match_status: str = "unknown"
    balance_match: bool = False
    balance_match_known: bool = False
    balance_match_status: str = "unknown"
    balance_failure_reason: str = ""
    clock_skew_ok: bool = False
    contract_revert_rate: Decimal = Decimal("0")


@dataclass(slots=True)
class RouteStats:
    consecutive_failures: int = 0
    consecutive_losses: int = 0
    executions: deque[datetime] | None = None
    last_failure_category: str = ""
    last_failure_reason: str = ""
    last_failure_at: datetime | None = None
    last_failure_fatal: bool = False

    def __post_init__(self) -> None:
        if self.executions is None:
            self.executions = deque()


FATAL_FAILURE_CATEGORIES: set[str] = {
    "quote_mismatch",
    "revert",
    "invalid_address",
    "chain_id_mismatch",
    "router_allowlist_violation",
    "stale_critical_data",
    "quote_unavailable",
    "scan_fatal",
}


class GlobalRiskManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.global_kill_switch = settings.global_kill_switch
        self.strategy_paused: set[str] = set()
        self.route_paused: set[str] = set()
        self.pair_paused: set[str] = set()
        self.venue_paused: set[str] = set()
        self.cooldown_until: dict[str, datetime] = {}
        self.route_stats: dict[str, RouteStats] = defaultdict(RouteStats)
        self.daily_realized_pnl = Decimal("0")
        self.day_anchor = datetime.now(timezone.utc).date()

    @staticmethod
    def _as_utc(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def reset_daily_if_needed(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self.day_anchor:
            self.day_anchor = today
            self.daily_realized_pnl = Decimal("0")

    def set_global_kill(self, paused: bool) -> None:
        self.global_kill_switch = paused

    def pause_strategy(self, strategy: str) -> None:
        self.strategy_paused.add(strategy)

    def resume_strategy(self, strategy: str) -> None:
        self.strategy_paused.discard(strategy)

    def pause_route(self, route_id: str) -> None:
        self.route_paused.add(route_id)

    def resume_route(self, route_id: str) -> None:
        self.route_paused.discard(route_id)

    def pause_pair(self, pair: str) -> None:
        self.pair_paused.add(pair)

    def resume_pair(self, pair: str) -> None:
        self.pair_paused.discard(pair)

    def pause_venue(self, venue: str) -> None:
        self.venue_paused.add(venue)

    def resume_venue(self, venue: str) -> None:
        self.venue_paused.discard(venue)

    def clear_cooldown(self, route_id: str | None = None) -> None:
        if route_id:
            self.cooldown_until.pop(route_id, None)
            stats = self.route_stats[route_id]
            stats.consecutive_failures = 0
            stats.last_failure_category = ""
            stats.last_failure_reason = ""
            stats.last_failure_at = None
            stats.last_failure_fatal = False
            return
        self.cooldown_until.clear()
        for stats in self.route_stats.values():
            stats.consecutive_failures = 0
            stats.last_failure_category = ""
            stats.last_failure_reason = ""
            stats.last_failure_at = None
            stats.last_failure_fatal = False

    def mark_failure(self, route_id: str, category: str, reason: str = "") -> None:
        stats = self.route_stats[route_id]
        stats.consecutive_failures += 1
        stats.last_failure_category = category
        stats.last_failure_reason = reason
        stats.last_failure_at = datetime.now(timezone.utc)
        stats.last_failure_fatal = category in FATAL_FAILURE_CATEGORIES

        cooldown = (
            self.settings.route_fatal_failure_cooldown_seconds
            if stats.last_failure_fatal
            else self.settings.route_failure_cooldown_seconds
        )
        self.cooldown_until[route_id] = datetime.now(timezone.utc) + timedelta(seconds=cooldown)

        if stats.last_failure_fatal:
            self.route_paused.add(route_id)

    def mark_success(self, route_id: str, realized_pnl: Decimal) -> None:
        self.reset_daily_if_needed()
        stats = self.route_stats[route_id]
        stats.consecutive_failures = 0
        stats.last_failure_category = ""
        stats.last_failure_reason = ""
        stats.last_failure_at = None
        stats.last_failure_fatal = False

        if realized_pnl < 0:
            stats.consecutive_losses += 1
        else:
            stats.consecutive_losses = 0

        self.daily_realized_pnl += realized_pnl
        now = datetime.now(timezone.utc)
        stats.executions.append(now)
        cutoff = now - timedelta(minutes=10)
        while stats.executions and stats.executions[0] < cutoff:
            stats.executions.popleft()

    def should_stop_for_daily_dd(self, balance_baseline: Decimal) -> bool:
        if balance_baseline <= 0:
            return True
        dd = -self.daily_realized_pnl / balance_baseline
        return dd >= self.settings.global_daily_dd_stop_pct

    def cooldown_remaining_seconds(self, route_id: str) -> int:
        until = self.cooldown_until.get(route_id)
        if until is None:
            return 0
        delta = int((until - datetime.now(timezone.utc)).total_seconds())
        return max(delta, 0)

    def get_route_state(self, route_id: str) -> dict[str, str | int | bool]:
        stats = self.route_stats[route_id]
        cooldown_until = self.cooldown_until.get(route_id)
        return {
            "route_id": route_id,
            "consecutive_failures": stats.consecutive_failures,
            "consecutive_losses": stats.consecutive_losses,
            "last_failure_category": stats.last_failure_category,
            "last_failure_reason": stats.last_failure_reason,
            "last_failure_fatal": stats.last_failure_fatal,
            "last_failure_at": stats.last_failure_at.isoformat() if stats.last_failure_at else "",
            "cooldown_until": cooldown_until.isoformat() if cooldown_until else "",
            "cooldown_remaining_seconds": self.cooldown_remaining_seconds(route_id),
            "route_paused": route_id in self.route_paused,
        }

    def hydrate_route_state(
        self,
        route_id: str,
        paused: bool,
        cooldown_until: datetime | None,
        last_failure_category: str,
        last_failure_reason: str,
        last_failure_fatal: bool,
        last_failure_at: datetime | None,
        consecutive_failures: int,
        consecutive_losses: int,
    ) -> None:
        stats = self.route_stats[route_id]
        stats.consecutive_failures = max(0, int(consecutive_failures))
        stats.consecutive_losses = max(0, int(consecutive_losses))
        stats.last_failure_category = last_failure_category
        stats.last_failure_reason = last_failure_reason
        stats.last_failure_fatal = last_failure_fatal
        stats.last_failure_at = self._as_utc(last_failure_at)
        if paused:
            self.route_paused.add(route_id)
        else:
            self.route_paused.discard(route_id)
        cooldown_until_utc = self._as_utc(cooldown_until)
        if cooldown_until_utc and cooldown_until_utc > datetime.now(timezone.utc):
            self.cooldown_until[route_id] = cooldown_until_utc
        else:
            self.cooldown_until.pop(route_id, None)

    def evaluate(
        self,
        quote: RouteQuote,
        mode: RunMode,
        quote_freshness_limit: int,
        health: HealthSnapshot,
        wallet_balance_usdc: Decimal,
        reference_deviation_bps: Decimal,
        depeg_detected: bool,
        smaller_pool_liquidity_usdc: Decimal,
    ) -> OpportunityDecision:
        checks: dict[str, bool] = {}

        checks["global_pause"] = not self.global_kill_switch
        if not checks["global_pause"]:
            return OpportunityDecision(False, "global_pause", checks)

        checks["strategy_pause"] = quote.strategy not in self.strategy_paused
        if not checks["strategy_pause"]:
            return OpportunityDecision(False, "strategy_paused", checks)

        checks["route_pause"] = quote.route_id not in self.route_paused
        if not checks["route_pause"]:
            return OpportunityDecision(False, "route_disabled", checks)

        checks["pair_pause"] = quote.pair not in self.pair_paused
        if not checks["pair_pause"]:
            return OpportunityDecision(False, "pair_disabled", checks)

        venues = quote.metadata.get("venues", "")
        venue_tokens = [v.strip() for v in venues.split("->") if v.strip()]
        checks["venue_pause"] = all(v not in self.venue_paused for v in venue_tokens)
        if not checks["venue_pause"]:
            return OpportunityDecision(False, "venue_disabled", checks)

        checks["quote_unavailable"] = quote.metadata.get("quote_unavailable", "false") != "true"
        if not checks["quote_unavailable"]:
            return OpportunityDecision(False, "quote_unavailable", checks)

        checks["health_fresh"] = health.health_age_seconds <= Decimal(self.settings.health_snapshot_stale_seconds)
        if not checks["health_fresh"]:
            return OpportunityDecision(False, "stale_health", checks)

        checks["db_known"] = health.db_known
        if not checks["db_known"]:
            return OpportunityDecision(False, "health_unknown", checks)

        checks["db_reachable"] = health.db_reachable
        if not checks["db_reachable"]:
            return OpportunityDecision(False, "db_unreachable", checks)

        checks["rpc_known"] = health.rpc_known
        if not checks["rpc_known"]:
            return OpportunityDecision(False, "health_unknown", checks)

        checks["rpc_reachable"] = health.rpc_reachable
        if not checks["rpc_reachable"]:
            return OpportunityDecision(False, "rpc_unreachable", checks)

        checks["signing_known"] = health.signing_known
        if not checks["signing_known"]:
            return OpportunityDecision(False, "health_unknown", checks)

        checks["signing_ok"] = health.signing_ok
        if not checks["signing_ok"]:
            return OpportunityDecision(False, "signing_error", checks)

        checks["fee_known"] = health.fee_known
        if not checks["fee_known"]:
            return OpportunityDecision(False, "fee_unknown", checks)

        fee_status = normalize_fee_confidence(health.fee_known_status)
        checks["fee_status_known"] = fee_status != "unknown"
        if not checks["fee_status_known"]:
            return OpportunityDecision(False, "fee_unknown", checks)

        required_fee_status = (
            self.settings.live_min_fee_confidence_status
            if mode == RunMode.LIVE
            else "fallback_only"
        )
        checks["fee_status_verified"] = fee_confidence_at_least(fee_status, required_fee_status)
        if not checks["fee_status_verified"]:
            return OpportunityDecision(False, "fee_unverified", checks)

        quote_match_status = normalize_quote_match_status(health.quote_match_status)
        checks["quote_match_known"] = health.quote_match_known and quote_match_status != "unknown"
        if not checks["quote_match_known"]:
            return OpportunityDecision(False, "health_unknown", checks)

        checks["quote_match"] = health.quote_match and quote_match_status == "matched"
        if not checks["quote_match"]:
            return OpportunityDecision(False, "quote_mismatch", checks)

        balance_status = normalize_balance_confidence(health.balance_match_status)
        checks["balance_match_known"] = health.balance_match_known and balance_status != "unknown"
        if not checks["balance_match_known"]:
            return OpportunityDecision(False, "balance_unverified", checks)

        checks["balance_match"] = health.balance_match and balance_status != "mismatch"
        if not checks["balance_match"]:
            failure_reason = health.balance_failure_reason.strip().lower()
            if failure_reason == "wallet_balance_mismatch":
                return OpportunityDecision(False, "wallet_balance_mismatch", checks)
            if failure_reason == "inventory_drift":
                return OpportunityDecision(False, "inventory_drift", checks)
            return OpportunityDecision(False, "balance_mismatch", checks)

        required_balance_status = self.settings.live_min_balance_confidence_status if mode == RunMode.LIVE else "internal_ok"
        checks["balance_status_verified"] = balance_confidence_at_least(balance_status, required_balance_status)
        if not checks["balance_status_verified"]:
            return OpportunityDecision(False, "balance_unverified", checks)

        checks["clock_skew_ok"] = health.clock_skew_ok
        if not checks["clock_skew_ok"]:
            return OpportunityDecision(False, "clock_skew", checks)

        checks["contract_revert_rate"] = health.contract_revert_rate <= Decimal("0.2")
        if not checks["contract_revert_rate"]:
            return OpportunityDecision(False, "contract_revert_rate_high", checks)

        checks["alert_health"] = health.alert_failures < self.settings.alert_failure_stop_threshold
        if not checks["alert_health"]:
            return OpportunityDecision(False, "alert_subsystem_failure", checks)

        checks["quote_fresh"] = quote.quote_age_seconds <= Decimal(quote_freshness_limit)
        if not checks["quote_fresh"]:
            return OpportunityDecision(False, "stale_quote", checks)

        checks["pool_health"] = quote.metadata.get("pool_health", "false") == "true"
        if not checks["pool_health"]:
            return OpportunityDecision(False, "pool_unhealthy", checks)

        checks["rpc_error_rate"] = health.rpc_error_rate_5m <= self.settings.rpc_error_rate_stop_pct_5m
        if not checks["rpc_error_rate"]:
            return OpportunityDecision(False, "rpc_error_spike", checks)

        gas_baseline = health.gas_p90 if health.gas_p90 > 0 else Decimal("1")
        checks["gas_spike"] = health.gas_now <= gas_baseline * self.settings.gas_spike_multiplier
        if not checks["gas_spike"]:
            return OpportunityDecision(False, "gas_spike", checks)

        checks["liq_drop"] = abs(health.liquidity_change_pct) <= self.settings.liquidity_drop_stop_pct
        if not checks["liq_drop"]:
            return OpportunityDecision(False, "liquidity_too_low", checks)

        checks["depeg_guard"] = (not depeg_detected) and (abs(reference_deviation_bps) <= self.settings.depeg_threshold_bps)
        if not checks["depeg_guard"]:
            return OpportunityDecision(False, "depeg_guard", checks)

        checks["notional_limit"] = quote.initial_amount <= self.settings.live_max_notional_usdc
        if not checks["notional_limit"]:
            return OpportunityDecision(False, "notional_too_large", checks)

        checks["liquidity_available"] = smaller_pool_liquidity_usdc > 0
        if not checks["liquidity_available"]:
            return OpportunityDecision(False, "liquidity_unavailable", checks)

        checks["pool_share_limit"] = (
            quote.initial_amount / smaller_pool_liquidity_usdc <= self.settings.live_max_notional_pct_of_smaller_pool
        )
        if not checks["pool_share_limit"]:
            return OpportunityDecision(False, "pool_share_too_large", checks)

        checks["wallet_balance"] = wallet_balance_usdc >= quote.initial_amount
        if not checks["wallet_balance"]:
            return OpportunityDecision(False, "insufficient_balance", checks)

        stats = self.route_stats[quote.route_id]
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=10)
        while stats.executions and stats.executions[0] < cutoff:
            stats.executions.popleft()

        checks["route_rate_limit"] = len(stats.executions) < self.settings.live_max_trades_per_route_per_10m
        if not checks["route_rate_limit"]:
            return OpportunityDecision(False, "cooldown", checks)

        # strict semantics: threshold=1 blocks after first failure
        checks["consecutive_failures"] = (
            stats.consecutive_failures < self.settings.live_max_consecutive_failures_per_route
        )
        if not checks["consecutive_failures"]:
            return OpportunityDecision(False, "too_many_failures", checks)

        checks["consecutive_losses"] = stats.consecutive_losses < self.settings.live_max_consecutive_losses_per_route
        if not checks["consecutive_losses"]:
            return OpportunityDecision(False, "too_many_losses", checks)

        route_cooldown = self.cooldown_until.get(quote.route_id)
        checks["cooldown"] = not route_cooldown or now >= route_cooldown
        if not checks["cooldown"]:
            return OpportunityDecision(False, "cooldown", checks)

        if mode == RunMode.LIVE:
            checks["mode_allowed"] = self.settings.live_enable_flag
            if not checks["mode_allowed"]:
                return OpportunityDecision(False, "live_disabled", checks)

            checks["modeled_edge"] = quote.modeled_net_edge_bps >= Decimal(self.settings.live_min_net_edge_bps)
            if not checks["modeled_edge"]:
                return OpportunityDecision(False, "below_threshold", checks)

            checks["persist"] = quote.persisted_seconds >= Decimal(self.settings.live_min_edge_persist_seconds)
            if not checks["persist"]:
                return OpportunityDecision(False, "edge_not_persistent", checks)

            checks["slippage"] = quote.expected_slippage_bps <= Decimal(self.settings.live_max_slippage_bps)
            if not checks["slippage"]:
                return OpportunityDecision(False, "slippage_too_high", checks)

            checks["profit_abs"] = quote.modeled_net_edge_amount >= self.settings.live_min_profit_absolute_usdc
            if not checks["profit_abs"]:
                return OpportunityDecision(False, "below_min_profit", checks)

        else:
            checks["modeled_edge"] = quote.modeled_net_edge_bps >= Decimal(self.settings.shadow_min_net_edge_bps)
            if not checks["modeled_edge"]:
                return OpportunityDecision(False, "below_threshold", checks)

            checks["persist"] = quote.persisted_seconds >= Decimal(self.settings.shadow_min_edge_persist_seconds)
            if not checks["persist"]:
                return OpportunityDecision(False, "edge_not_persistent", checks)

            checks["slippage"] = quote.expected_slippage_bps <= Decimal(self.settings.shadow_max_slippage_bps)
            if not checks["slippage"]:
                return OpportunityDecision(False, "slippage_too_high", checks)

        return OpportunityDecision(True, "", checks)
