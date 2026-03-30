from decimal import Decimal

from app.config.settings import Settings
from app.quote_engine.types import RouteQuote
from app.risk.manager import GlobalRiskManager, HealthSnapshot


def _quote() -> RouteQuote:
    return RouteQuote(
        route_id="route-x",
        strategy="hyperevm_dex_dex",
        pair="USDC/USDt0",
        direction="forward",
        initial_amount=Decimal("100"),
        final_amount=Decimal("101"),
        raw_spread_amount=Decimal("1"),
        raw_edge_bps=Decimal("90"),
        modeled_net_edge_amount=Decimal("0.8"),
        modeled_net_edge_bps=Decimal("80"),
        expected_slippage_bps=Decimal("1"),
        gas_cost_usdc=Decimal("0.02"),
        quote_age_seconds=Decimal("1"),
        all_costs=Decimal("0.2"),
        persisted_seconds=Decimal("12"),
        metadata={
            "pool_health": "true",
            "venues": "ramses_v3->hybra_v3",
            "smaller_pool_liquidity_usdc": "500000",
        },
    )


def _healthy_snapshot() -> HealthSnapshot:
    return HealthSnapshot(
        rpc_error_rate_5m=Decimal("0"),
        gas_now=Decimal("10"),
        gas_p90=Decimal("20"),
        liquidity_change_pct=Decimal("0"),
        quote_stale_seconds=Decimal("0"),
        health_age_seconds=Decimal("0"),
        alert_failures=0,
        db_reachable=True,
        db_known=True,
        rpc_reachable=True,
        rpc_known=True,
        signing_ok=True,
        signing_known=True,
        fee_known=True,
        fee_known_status="chain_verified",
        quote_match=True,
        quote_match_known=True,
        quote_match_status="matched",
        balance_match=True,
        balance_match_known=True,
        balance_match_status="wallet_verified",
        clock_skew_ok=True,
        contract_revert_rate=Decimal("0"),
    )


def test_failure_threshold_blocks_after_one_failure() -> None:
    settings = Settings(live_enable_flag=True, live_max_consecutive_failures_per_route=1)
    risk = GlobalRiskManager(settings)

    quote = _quote()
    health = _healthy_snapshot()

    risk.mark_failure(quote.route_id, category="revert", reason="tx revert")

    decision = risk.evaluate(
        quote=quote,
        mode=settings.mode,
        quote_freshness_limit=3,
        health=health,
        wallet_balance_usdc=Decimal("1000"),
        reference_deviation_bps=Decimal("1"),
        depeg_detected=False,
        smaller_pool_liquidity_usdc=Decimal("500000"),
    )
    assert not decision.tradable
    assert decision.blocked_reason in {"too_many_failures", "route_disabled", "cooldown"}


def test_cooldown_remaining_exposed() -> None:
    settings = Settings(route_failure_cooldown_seconds=120)
    risk = GlobalRiskManager(settings)
    risk.mark_failure("route-cd", category="scan_fatal", reason="fatal")
    assert risk.cooldown_remaining_seconds("route-cd") > 0


def test_quote_unavailable_is_explicit_block_reason() -> None:
    settings = Settings()
    risk = GlobalRiskManager(settings)

    quote = _quote()
    quote.metadata["quote_unavailable"] = "true"

    decision = risk.evaluate(
        quote=quote,
        mode=settings.mode,
        quote_freshness_limit=3,
        health=_healthy_snapshot(),
        wallet_balance_usdc=Decimal("1000"),
        reference_deviation_bps=Decimal("1"),
        depeg_detected=False,
        smaller_pool_liquidity_usdc=Decimal("500000"),
    )
    assert not decision.tradable
    assert decision.blocked_reason == "quote_unavailable"


def test_liquidity_pool_share_limit() -> None:
    settings = Settings(live_max_notional_pct_of_smaller_pool=Decimal("0.0002"))
    risk = GlobalRiskManager(settings)

    quote = _quote()

    decision = risk.evaluate(
        quote=quote,
        mode=settings.mode,
        quote_freshness_limit=3,
        health=_healthy_snapshot(),
        wallet_balance_usdc=Decimal("1000"),
        reference_deviation_bps=Decimal("1"),
        depeg_detected=False,
        smaller_pool_liquidity_usdc=Decimal("1000"),
    )
    assert not decision.tradable
    assert decision.blocked_reason == "pool_share_too_large"
