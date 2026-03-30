from decimal import Decimal

from app.config.settings import Settings
from app.quote_engine.types import RouteQuote
from app.risk.manager import GlobalRiskManager, HealthSnapshot


def _quote() -> RouteQuote:
    return RouteQuote(
        route_id="route-health-unknown",
        strategy="hyperevm_dex_dex",
        pair="USDC/USDt0",
        direction="forward",
        initial_amount=Decimal("50"),
        final_amount=Decimal("50.2"),
        raw_spread_amount=Decimal("0.2"),
        raw_edge_bps=Decimal("40"),
        modeled_net_edge_amount=Decimal("0.15"),
        modeled_net_edge_bps=Decimal("30"),
        expected_slippage_bps=Decimal("1"),
        gas_cost_usdc=Decimal("0.01"),
        quote_age_seconds=Decimal("1"),
        all_costs=Decimal("0.05"),
        persisted_seconds=Decimal("10"),
        metadata={
            "pool_health": "true",
            "venues": "ramses_v3->hybra_v3",
            "smaller_pool_liquidity_usdc": "500000",
            "quote_unavailable": "false",
        },
    )


def test_unknown_health_is_blocked() -> None:
    settings = Settings()
    risk = GlobalRiskManager(settings)
    quote = _quote()

    health = HealthSnapshot(
        health_age_seconds=Decimal("0"),
        db_known=False,
        rpc_known=True,
        rpc_reachable=True,
        signing_known=True,
        signing_ok=True,
        fee_known=True,
        quote_match_known=True,
        quote_match=True,
        balance_match_known=True,
        balance_match=True,
        clock_skew_ok=True,
    )

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
    assert decision.blocked_reason == "health_unknown"
