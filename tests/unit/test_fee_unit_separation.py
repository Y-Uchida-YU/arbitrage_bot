from __future__ import annotations

from decimal import Decimal

import pytest

from app.config.settings import RunMode, Settings
from app.exchanges.factory import build_hyperevm_dex_adapters
from app.models.core import Route
from app.quote_engine.edge import ModeledEdgeCalculator
from app.quote_engine.engine import HyperDexDexQuoteEngine


@pytest.mark.asyncio
async def test_fee_units_are_separated_between_quoter_and_economic_costs() -> None:
    settings = Settings(
        use_mock_market_data=True,
        gas_price_gwei_default=Decimal("0"),
        gas_token_price_usdc=Decimal("0"),
        cost_quote_drift_buffer_bps=0,
        cost_slippage_buffer_bps=0,
        cost_router_overhead_bps=0,
        cost_failed_tx_allowance_bps=0,
        cost_safety_margin_bps=0,
    )

    route = Route(
        id="route-fee-sep",
        strategy="hyperevm_dex_dex",
        name="fee_sep",
        pair="USDC/USDt0",
        direction="forward",
        venue_a="ramses_v3",
        venue_b="hybra_v3",
        pool_a="ramses_v3_usdc_usdt0_5",
        pool_b="hybra_v3_usdt0_usdc_5",
        router_a="0x0000000000000000000000000000000000000010",
        router_b="0x0000000000000000000000000000000000000010",
        fee_tier_a_bps=5,
        fee_tier_b_bps=5,
        quoter_fee_tier_a=1,
        quoter_fee_tier_b=2,
        pool_fee_tier_a=3,
        pool_fee_tier_b=4,
        economic_fee_bps_a=200,
        economic_fee_bps_b=300,
        max_notional_usdc=Decimal("100"),
        enabled=True,
        is_live_allowed=True,
        kill_switch=False,
    )

    engine = HyperDexDexQuoteEngine(
        settings=settings,
        edge_calculator=ModeledEdgeCalculator(settings),
        dex_adapters=build_hyperevm_dex_adapters(settings),
    )

    quote = await engine.quote_route(route, Decimal("100"), mode_profile=RunMode.PAPER)

    assert quote.metadata["quoter_fee_tier_a"] == "1"
    assert quote.metadata["quoter_fee_tier_b"] == "2"
    assert quote.metadata["economic_fee_bps_a"] == "200"
    assert quote.metadata["economic_fee_bps_b"] == "300"

    # 200 + 300 bps of 100 USDC = 5 USDC cost baseline.
    assert quote.all_costs >= Decimal("5")
