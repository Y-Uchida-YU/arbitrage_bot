from __future__ import annotations

from decimal import Decimal

from app.config.settings import Settings
from app.exchanges.dex.hyperevm import MockV3Adapter, PoolModel, RealV3LikeAdapter


class UniswapV3BaseAdapter(MockV3Adapter):
    venue = "uniswap_v3_base"


class PancakeV3BaseAdapter(MockV3Adapter):
    venue = "pancakeswap_v3_base"


class AerodromeBaseAdapter(MockV3Adapter):
    venue = "aerodrome_base"


class RealUniswapV3BaseAdapter(RealV3LikeAdapter):
    venue = "uniswap_v3_base"


class RealPancakeV3BaseAdapter(RealV3LikeAdapter):
    venue = "pancakeswap_v3_base"


class RealAerodromeBaseAdapter(RealV3LikeAdapter):
    venue = "aerodrome_base"


def build_base_mock_adapters(settings: Settings) -> dict[str, MockV3Adapter]:
    uni_pool = PoolModel(
        pool_id="base_uni_v3_virtual_usdc_100",
        fee_bps=100,
        mid_price=settings.mock_base_virtual_usdc_mid,
        liquidity_usd=Decimal("250000"),
        token_in_symbol="USDC",
        token_out_symbol="VIRTUAL",
    )
    cake_pool = PoolModel(
        pool_id="base_cake_v3_virtual_usdc_100",
        fee_bps=100,
        mid_price=settings.mock_base_virtual_usdc_mid,
        liquidity_usd=Decimal("200000"),
        token_in_symbol="USDC",
        token_out_symbol="VIRTUAL",
    )
    aero_pool = PoolModel(
        pool_id="base_aero_virtual_usdc_100",
        fee_bps=100,
        mid_price=settings.mock_base_virtual_usdc_mid,
        liquidity_usd=Decimal("150000"),
        token_in_symbol="USDC",
        token_out_symbol="VIRTUAL",
    )
    return {
        "uniswap_v3_base": UniswapV3BaseAdapter(settings, {uni_pool.pool_id: uni_pool}),
        "pancakeswap_v3_base": PancakeV3BaseAdapter(settings, {cake_pool.pool_id: cake_pool}),
        "aerodrome_base": AerodromeBaseAdapter(settings, {aero_pool.pool_id: aero_pool}),
    }


def build_base_real_adapters(settings: Settings) -> dict[str, RealV3LikeAdapter]:
    uni_pool = PoolModel(
        pool_id="base_uni_v3_virtual_usdc_100",
        fee_bps=settings.base_uniswap_v3_fee_bps,
        mid_price=Decimal("0"),
        liquidity_usd=Decimal("0"),
        pool_address=settings.base_uniswap_v3_pool,
        token_in_symbol="USDC",
        token_out_symbol="VIRTUAL",
        token_in_address=settings.base_usdc_address,
        token_out_address=settings.base_virtual_address,
        token_in_decimals=settings.base_usdc_decimals,
        token_out_decimals=settings.base_virtual_decimals,
    )
    cake_pool = PoolModel(
        pool_id="base_cake_v3_virtual_usdc_100",
        fee_bps=settings.base_pancake_v3_fee_bps,
        mid_price=Decimal("0"),
        liquidity_usd=Decimal("0"),
        pool_address=settings.base_pancake_v3_pool,
        token_in_symbol="USDC",
        token_out_symbol="VIRTUAL",
        token_in_address=settings.base_usdc_address,
        token_out_address=settings.base_virtual_address,
        token_in_decimals=settings.base_usdc_decimals,
        token_out_decimals=settings.base_virtual_decimals,
    )
    aero_pool = PoolModel(
        pool_id="base_aero_virtual_usdc_100",
        fee_bps=settings.base_aerodrome_fee_bps,
        mid_price=Decimal("0"),
        liquidity_usd=Decimal("0"),
        pool_address=settings.base_aerodrome_pool,
        token_in_symbol="USDC",
        token_out_symbol="VIRTUAL",
        token_in_address=settings.base_usdc_address,
        token_out_address=settings.base_virtual_address,
        token_in_decimals=settings.base_usdc_decimals,
        token_out_decimals=settings.base_virtual_decimals,
    )

    return {
        "uniswap_v3_base": RealUniswapV3BaseAdapter(
            settings,
            settings.base_rpc_url,
            settings.base_uniswap_quoter,
            {uni_pool.pool_id: uni_pool},
            chain_slug="base",
            quoter_mode=settings.base_uniswap_quoter_mode,
        ),
        "pancakeswap_v3_base": RealPancakeV3BaseAdapter(
            settings,
            settings.base_rpc_url,
            settings.base_pancake_quoter,
            {cake_pool.pool_id: cake_pool},
            chain_slug="base",
            quoter_mode=settings.base_pancake_quoter_mode,
        ),
        "aerodrome_base": RealAerodromeBaseAdapter(
            settings,
            settings.base_rpc_url,
            settings.base_aerodrome_quoter,
            {aero_pool.pool_id: aero_pool},
            chain_slug="base",
            quoter_mode=settings.base_aerodrome_quoter_mode,
        ),
    }