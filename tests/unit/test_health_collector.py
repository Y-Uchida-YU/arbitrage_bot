from decimal import Decimal

from app.health.collector import HealthCollector


def test_health_collector_rolling_metrics() -> None:
    collector = HealthCollector()
    collector.record_rpc_probe(Decimal("40"), True)
    collector.record_rpc_probe(Decimal("80"), False)
    collector.record_gas(Decimal("0.04"))
    collector.record_gas(Decimal("0.06"))
    collector.record_quote_probe("bybit", Decimal("20"), Decimal("1"), ok=True, quote_unavailable=False)
    collector.record_liquidity("route-1", Decimal("500000"))
    collector.record_alert_result(True)
    collector.record_execution_result("reverted")

    snap = collector.build_snapshot("route-1")

    assert snap.rpc_error_rate_5m > 0
    assert snap.gas_p90 >= snap.gas_p50
    assert snap.route_smaller_pool_liquidity_usdc == Decimal("500000")


def test_health_collector_quote_unavailable_venue_listed() -> None:
    collector = HealthCollector()
    collector.record_quote_probe("ramses_v3", Decimal("5"), Decimal("1"), ok=False, quote_unavailable=True)
    snap = collector.build_snapshot("route-x")
    assert "ramses_v3" in snap.quote_unavailable_venues


def test_venue_quote_health_exposes_last_success() -> None:
    collector = HealthCollector()
    collector.record_quote_probe("bybit", Decimal("8"), Decimal("1"), ok=True, quote_unavailable=False)
    collector.record_quote_probe("ramses_v3", Decimal("7"), Decimal("1"), ok=False, quote_unavailable=True)

    rows = collector.venue_quote_health()
    assert rows

    bybit = next(x for x in rows if x.venue == "bybit")
    assert bybit.last_success_ts is not None
    assert bybit.quote_unavailable_count_5m == 0

    ramses = next(x for x in rows if x.venue == "ramses_v3")
    assert ramses.quote_unavailable_count_5m >= 1
