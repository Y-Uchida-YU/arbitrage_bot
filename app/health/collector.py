from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.health.types import CommissioningHealthSnapshot, VenueQuoteHealth
from app.risk.manager import HealthSnapshot
from app.utils.confidence import (
    normalize_balance_confidence,
    normalize_fee_confidence,
    normalize_quote_match_status,
)


@dataclass(slots=True)
class TimedValue:
    ts: datetime
    value: Decimal


@dataclass(slots=True)
class TimedBool:
    ts: datetime
    ok: bool


class HealthCollector:
    def __init__(self) -> None:
        self._rpc_latency: deque[TimedValue] = deque()
        self._rpc_results: deque[TimedBool] = deque()
        self._db_latency: deque[TimedValue] = deque()
        self._db_results: deque[TimedBool] = deque()
        self._quote_latency: deque[TimedValue] = deque()
        self._quote_age: deque[TimedValue] = deque()
        self._gas_series: deque[TimedValue] = deque()
        self._alert_results: deque[TimedBool] = deque()
        self._execution_results: deque[TimedBool] = deque()
        self._venue_last_success: dict[str, datetime] = {}
        self._venue_unavailable_events: dict[str, deque[datetime]] = defaultdict(deque)
        self._route_liquidity: dict[str, deque[TimedValue]] = defaultdict(deque)
        self._heartbeat_ts: datetime = datetime.now(timezone.utc)
        self._last_quality_update: datetime = datetime.now(timezone.utc)
        self._signing_state: str = "unknown"
        self._fee_status: str = "unknown"
        self._fee_provenance: str = ""
        self._quote_match_status: str = "unknown"
        self._balance_status: str = "unknown"
        self._balance_failure_reason: str = ""

    def record_rpc_probe(self, latency_ms: Decimal, ok: bool) -> None:
        now = datetime.now(timezone.utc)
        self._rpc_latency.append(TimedValue(now, latency_ms))
        self._rpc_results.append(TimedBool(now, ok))
        self._trim_all(now)

    def record_db_latency(self, latency_ms: Decimal, ok: bool = True) -> None:
        now = datetime.now(timezone.utc)
        self._db_latency.append(TimedValue(now, latency_ms))
        self._db_results.append(TimedBool(now, ok))
        self._trim_all(now)

    def record_quote_probe(
        self,
        venue: str,
        latency_ms: Decimal,
        quote_age_seconds: Decimal,
        ok: bool,
        quote_unavailable: bool,
    ) -> None:
        now = datetime.now(timezone.utc)
        self._quote_latency.append(TimedValue(now, latency_ms))
        self._quote_age.append(TimedValue(now, quote_age_seconds))
        if ok:
            self._venue_last_success[venue] = now
        if quote_unavailable:
            self._venue_unavailable_events[venue].append(now)
        self._trim_all(now)

    def record_gas(self, gas_gwei: Decimal) -> None:
        now = datetime.now(timezone.utc)
        self._gas_series.append(TimedValue(now, gas_gwei))
        self._trim_all(now)

    def record_liquidity(self, route_id: str, liquidity_usd: Decimal) -> None:
        now = datetime.now(timezone.utc)
        self._route_liquidity[route_id].append(TimedValue(now, liquidity_usd))
        self._trim_all(now)

    def record_alert_result(self, sent_ok: bool) -> None:
        now = datetime.now(timezone.utc)
        self._alert_results.append(TimedBool(now, sent_ok))
        self._trim_all(now)

    def record_execution_result(self, tx_status: str) -> None:
        now = datetime.now(timezone.utc)
        ok = tx_status not in {"reverted", "failed"}
        self._execution_results.append(TimedBool(now, ok))
        self._trim_all(now)

    def set_heartbeat(self, ts: datetime) -> None:
        self._heartbeat_ts = ts

    def set_quality_status(
        self,
        *,
        signing_status: str | None,
        fee_known_status: str | None,
        fee_provenance: str | None,
        quote_match_status: str | None,
        balance_match_status: str | None,
        balance_failure_reason: str | None = None,
    ) -> None:
        self._signing_state = self._normalize_signing_state(signing_status)
        self._fee_status = normalize_fee_confidence(fee_known_status)
        self._fee_provenance = (fee_provenance or "").strip().lower()
        self._quote_match_status = normalize_quote_match_status(quote_match_status)
        self._balance_status = normalize_balance_confidence(balance_match_status)
        self._balance_failure_reason = (balance_failure_reason or "").strip().lower()
        self._last_quality_update = datetime.now(timezone.utc)

    def build_snapshot(self, route_id: str) -> CommissioningHealthSnapshot:
        now = datetime.now(timezone.utc)
        rpc_error_rate = self._error_rate(self._rpc_results)
        alert_success_rate = Decimal("1") - self._error_rate(self._alert_results)
        contract_revert_rate = self._error_rate(self._execution_results)

        gas_now = self._latest_value(self._gas_series)
        gas_p50 = self._quantile(self._gas_series, Decimal("0.50"))
        gas_p90 = self._quantile(self._gas_series, Decimal("0.90"))
        quote_age = self._latest_value(self._quote_age)

        route_liq = self._route_liquidity.get(route_id, deque())
        latest_liq = route_liq[-1].value if route_liq else Decimal("0")
        baseline_liq = self._quantile(route_liq, Decimal("0.50")) if route_liq else Decimal("0")
        liq_change = Decimal("0")
        if baseline_liq > 0:
            liq_change = (latest_liq - baseline_liq) / baseline_liq

        staleness = Decimal("999")
        if self._venue_last_success:
            newest = max(self._venue_last_success.values())
            staleness = Decimal(str((now - newest).total_seconds()))

        unavailable_venues: list[str] = []
        five_min_ago = now - timedelta(minutes=5)
        for venue, dq in self._venue_unavailable_events.items():
            while dq and dq[0] < five_min_ago:
                dq.popleft()
            if dq:
                unavailable_venues.append(venue)

        heartbeat_lag = Decimal(str((now - self._heartbeat_ts).total_seconds()))

        return CommissioningHealthSnapshot(
            rpc_latency_ms=self._latest_value(self._rpc_latency),
            rpc_error_rate_5m=rpc_error_rate,
            db_latency_ms=self._latest_value(self._db_latency),
            quote_latency_ms=self._latest_value(self._quote_latency),
            gas_now=gas_now,
            gas_p50=gas_p50,
            gas_p90=gas_p90,
            liquidity_change_pct=liq_change,
            quote_age_seconds=quote_age,
            alert_send_success_rate=alert_success_rate,
            contract_revert_rate=contract_revert_rate,
            market_data_staleness_seconds=staleness,
            heartbeat_lag_seconds=heartbeat_lag,
            route_smaller_pool_liquidity_usdc=latest_liq,
            quote_unavailable_venues=unavailable_venues,
        )

    def venue_quote_health(self) -> list[VenueQuoteHealth]:
        now = datetime.now(timezone.utc)
        five_min_ago = now - timedelta(minutes=5)
        venues = sorted(set(self._venue_last_success) | set(self._venue_unavailable_events))
        output: list[VenueQuoteHealth] = []

        for venue in venues:
            dq = self._venue_unavailable_events.get(venue, deque())
            while dq and dq[0] < five_min_ago:
                dq.popleft()
            unavailable_count = len(dq)
            last_success_ts = self._venue_last_success.get(venue)
            supported = not (unavailable_count > 0 and last_success_ts is None)
            degraded_reason = "quote_unavailable" if unavailable_count > 0 else ""
            output.append(
                VenueQuoteHealth(
                    venue=venue,
                    supported=supported,
                    last_success_ts=last_success_ts,
                    quote_unavailable_count_5m=unavailable_count,
                    degraded_reason=degraded_reason,
                )
            )

        return output

    def to_risk_snapshot(self, route_id: str) -> HealthSnapshot:
        snap = self.build_snapshot(route_id)
        now = datetime.now(timezone.utc)
        health_age_seconds = Decimal(str((now - self._last_quality_update).total_seconds()))
        rpc_error_rate = self._error_rate(self._rpc_results)
        db_error_rate = self._error_rate(self._db_results)

        rpc_known = bool(self._rpc_results)
        rpc_reachable = bool(self._rpc_results and self._rpc_results[-1].ok and rpc_error_rate < Decimal("0.5"))
        db_known = bool(self._db_results)
        db_reachable = bool(self._db_results and self._db_results[-1].ok and db_error_rate < Decimal("0.5"))

        return HealthSnapshot(
            rpc_error_rate_5m=snap.rpc_error_rate_5m,
            gas_now=snap.gas_now,
            gas_p90=snap.gas_p90,
            liquidity_change_pct=snap.liquidity_change_pct,
            quote_stale_seconds=snap.quote_age_seconds,
            health_age_seconds=health_age_seconds,
            alert_failures=sum(1 for x in self._alert_results if not x.ok),
            db_reachable=db_reachable,
            db_known=db_known,
            rpc_reachable=rpc_reachable,
            rpc_known=rpc_known,
            signing_ok=self._signing_state == "good",
            signing_known=self._signing_state != "unknown",
            fee_known=self._fee_status != "unknown",
            fee_known_status=self._fee_status,
            fee_provenance=self._fee_provenance,
            quote_match=self._quote_match_status == "matched",
            quote_match_known=self._quote_match_status != "unknown",
            quote_match_status=self._quote_match_status,
            balance_match=self._balance_status not in {"unknown", "mismatch"},
            balance_match_known=self._balance_status != "unknown",
            balance_match_status=self._balance_status,
            balance_failure_reason=self._balance_failure_reason,
            clock_skew_ok=snap.heartbeat_lag_seconds < Decimal("10"),
            contract_revert_rate=snap.contract_revert_rate,
        )

    def _trim_all(self, now: datetime) -> None:
        cutoff_5m = now - timedelta(minutes=5)
        cutoff_60m = now - timedelta(hours=1)

        for dq in (
            self._rpc_latency,
            self._rpc_results,
            self._db_latency,
            self._db_results,
            self._quote_latency,
            self._quote_age,
            self._alert_results,
            self._execution_results,
        ):
            while dq and dq[0].ts < cutoff_5m:
                dq.popleft()

        while self._gas_series and self._gas_series[0].ts < cutoff_60m:
            self._gas_series.popleft()

        for dq in self._route_liquidity.values():
            while dq and dq[0].ts < cutoff_60m:
                dq.popleft()

    @staticmethod
    def _latest_value(dq: deque[TimedValue]) -> Decimal:
        if not dq:
            return Decimal("0")
        return dq[-1].value

    @staticmethod
    def _error_rate(dq: deque[TimedBool]) -> Decimal:
        if not dq:
            return Decimal("0")
        total = Decimal(len(dq))
        failures = Decimal(sum(1 for x in dq if not x.ok))
        return failures / total

    @staticmethod
    def _quantile(dq: deque[TimedValue], q: Decimal) -> Decimal:
        if not dq:
            return Decimal("0")
        values = sorted(x.value for x in dq)
        if len(values) == 1:
            return values[0]
        idx = int((Decimal(len(values) - 1) * q).to_integral_value(rounding=ROUND_HALF_UP))
        idx = max(0, min(idx, len(values) - 1))
        return values[idx]

    @staticmethod
    def _normalize_signing_state(value: str | None) -> str:
        normalized = (value or "").strip().lower()
        if normalized in {"good", "bad", "unknown"}:
            return normalized
        if normalized in {"true", "1", "yes"}:
            return "good"
        if normalized in {"false", "0", "no"}:
            return "bad"
        return "unknown"
