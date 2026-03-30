from __future__ import annotations

from decimal import Decimal

from app.config.settings import Settings
from app.exchanges.dex.hyperevm import MockableV3Adapter, PoolModel


class UniswapV3BaseAdapter(MockableV3Adapter):
    venue = "uniswap_v3_base"


class PancakeV3BaseAdapter(MockableV3Adapter):
    venue = "pancakeswap_v3_base"


class AerodromeBaseAdapter(MockableV3Adapter):
    venue = "aerodrome_base"


def build_base_adapters(settings: Settings) -> dict[str, MockableV3Adapter]:
    uni_pool = PoolModel(
        pool_id="base_uni_v3_virtual_usdc_100",
        fee_bps=100,
        mid_price=settings.mock_base_virtual_usdc_mid,
        liquidity_usd=Decimal("250000"),
    )
    cake_pool = PoolModel(
        pool_id="base_cake_v3_virtual_usdc_100",
        fee_bps=100,
        mid_price=settings.mock_base_virtual_usdc_mid,
        liquidity_usd=Decimal("200000"),
    )
    aero_pool = PoolModel(
        pool_id="base_aero_virtual_usdc_100",
        fee_bps=100,
        mid_price=settings.mock_base_virtual_usdc_mid,
        liquidity_usd=Decimal("150000"),
    )
    return {
        "uniswap_v3_base": UniswapV3BaseAdapter(settings, {uni_pool.pool_id: uni_pool}),
        "pancakeswap_v3_base": PancakeV3BaseAdapter(settings, {cake_pool.pool_id: cake_pool}),
        "aerodrome_base": AerodromeBaseAdapter(settings, {aero_pool.pool_id: aero_pool}),
    }