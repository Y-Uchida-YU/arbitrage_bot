from decimal import Decimal

from app.config.settings import Settings
from app.quote_engine.types import RouteQuote
from app.risk.manager import GlobalRiskManager, HealthSnapshot


def _quote() -> RouteQuote:
    return RouteQuote(
        route_id="route-1",
        strategy="hyperevm_dex_dex",
        pair="USDC/USDt0",
        direction="forward",
        initial_amount=Decimal("100"),
        final_amount=Decimal("101"),
        raw_spread_amount=Decimal("1"),
        raw_edge_bps=Decimal("100"),
        modeled_net_edge_amount=Decimal("0.8"),
        modeled_net_edge_bps=Decimal("80"),
        expected_slippage_bps=Decimal("1"),
        gas_cost_usdc=Decimal("0.1"),
        quote_age_seconds=Decimal("1"),
        all_costs=Decimal("0.2"),
        persisted_seconds=Decimal("10"),
        metadata={"pool_health": "true"},
    )


def test_kill_switch_blocks() -> None:
    settings = Settings(live_enable_flag=True)
    risk = GlobalRiskManager(settings)
    risk.set_global_kill(True)

    decision = risk.evaluate(
        quote=_quote(),
        mode=settings.mode,
        quote_freshness_limit=3,
        health=HealthSnapshot(),
        wallet_balance_usdc=Decimal("1000"),
        reference_deviation_bps=Decimal("1"),
        depeg_detected=False,
        smaller_pool_liquidity_usdc=Decimal("100000"),
    )

    assert not decision.tradable
    assert decision.blocked_reason == "global_pause"


def test_route_pause_blocks() -> None:
    settings = Settings(live_enable_flag=True)
    risk = GlobalRiskManager(settings)
    risk.pause_route("route-1")

    decision = risk.evaluate(
        quote=_quote(),
        mode=settings.mode,
        quote_freshness_limit=3,
        health=HealthSnapshot(),
        wallet_balance_usdc=Decimal("1000"),
        reference_deviation_bps=Decimal("1"),
        depeg_detected=False,
        smaller_pool_liquidity_usdc=Decimal("100000"),
    )

    assert not decision.tradable
    assert decision.blocked_reason == "route_disabled"