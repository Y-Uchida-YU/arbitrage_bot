from __future__ import annotations

from decimal import Decimal

from app.config.settings import Settings
from app.exchanges.cex.base import CEXAdapter
from app.exchanges.cex.bybit import BybitSpotAdapter
from app.exchanges.cex.mexc import MEXCSpotAdapter
from app.exchanges.cex.mock import MockCEXAdapter
from app.exchanges.dex.base import DEXAdapter
from app.exchanges.dex.base_chain import build_base_mock_adapters, build_base_real_adapters
from app.exchanges.dex.hyperevm import (
    HybraV3Adapter,
    HybraV4ObserverAdapter,
    PoolModel,
    RamsesV3Adapter,
    RealHybraV3Adapter,
    RealHybraV4ObserverAdapter,
    RealRamsesV3Adapter,
)


def _build_hyperevm_mock_adapters(settings: Settings) -> dict[str, DEXAdapter]:
    mid = settings.mock_hyperevm_usdc_usdt0_mid

    ramses_forward = PoolModel(
        pool_id="ramses_v3_usdc_usdt0_5",
        fee_bps=5,
        mid_price=mid * Decimal("1.006"),
        liquidity_usd=Decimal("500000"),
        token_in_symbol="USDC",
        token_out_symbol="USDT0",
    )
    ramses_reverse = PoolModel(
        pool_id="ramses_v3_usdt0_usdc_5",
        fee_bps=5,
        mid_price=(Decimal("1") / mid) * Decimal("0.994"),
        liquidity_usd=Decimal("500000"),
        token_in_symbol="USDT0",
        token_out_symbol="USDC",
    )
    hybra_forward = PoolModel(
        pool_id="hybra_v3_usdc_usdt0_5",
        fee_bps=5,
        mid_price=mid * Decimal("0.994"),
        liquidity_usd=Decimal("450000"),
        token_in_symbol="USDC",
        token_out_symbol="USDT0",
    )
    hybra_reverse = PoolModel(
        pool_id="hybra_v3_usdt0_usdc_5",
        fee_bps=5,
        mid_price=(Decimal("1") / mid) * Decimal("1.006"),
        liquidity_usd=Decimal("450000"),
        token_in_symbol="USDT0",
        token_out_symbol="USDC",
    )

    ramses = RamsesV3Adapter(settings, {ramses_forward.pool_id: ramses_forward, ramses_reverse.pool_id: ramses_reverse})
    hybra = HybraV3Adapter(settings, {hybra_forward.pool_id: hybra_forward, hybra_reverse.pool_id: hybra_reverse})
    hybra_v4 = HybraV4ObserverAdapter(
        settings,
        {
            "hybra_v4_observer_usdc_usdt0": PoolModel(
                pool_id="hybra_v4_observer_usdc_usdt0",
                fee_bps=5,
                mid_price=mid,
                liquidity_usd=Decimal("250000"),
                token_in_symbol="USDC",
                token_out_symbol="USDT0",
            )
        },
    )

    return {
        "ramses_v3": ramses,
        "hybra_v3": hybra,
        "hybra_v4_observer": hybra_v4,
    }


def _build_hyperevm_real_adapters(settings: Settings) -> dict[str, DEXAdapter]:
    ramses_pool_forward = PoolModel(
        pool_id="ramses_v3_usdc_usdt0_5",
        fee_bps=settings.hyperevm_ramses_fee_bps,
        mid_price=Decimal("0"),
        liquidity_usd=Decimal("0"),
        pool_address=settings.hyperevm_ramses_pool_usdc_usdt0,
        token_in_symbol="USDC",
        token_out_symbol="USDT0",
        token_in_address=settings.hyperevm_usdc,
        token_out_address=settings.hyperevm_usdt0,
        token_in_decimals=settings.hyperevm_usdc_decimals,
        token_out_decimals=settings.hyperevm_usdt0_decimals,
    )
    ramses_pool_reverse = PoolModel(
        pool_id="ramses_v3_usdt0_usdc_5",
        fee_bps=settings.hyperevm_ramses_fee_bps,
        mid_price=Decimal("0"),
        liquidity_usd=Decimal("0"),
        pool_address=settings.hyperevm_ramses_pool_usdc_usdt0,
        token_in_symbol="USDT0",
        token_out_symbol="USDC",
        token_in_address=settings.hyperevm_usdt0,
        token_out_address=settings.hyperevm_usdc,
        token_in_decimals=settings.hyperevm_usdt0_decimals,
        token_out_decimals=settings.hyperevm_usdc_decimals,
    )
    hybra_pool_forward = PoolModel(
        pool_id="hybra_v3_usdc_usdt0_5",
        fee_bps=settings.hyperevm_hybra_fee_bps,
        mid_price=Decimal("0"),
        liquidity_usd=Decimal("0"),
        pool_address=settings.hyperevm_hybra_pool_usdc_usdt0,
        token_in_symbol="USDC",
        token_out_symbol="USDT0",
        token_in_address=settings.hyperevm_usdc,
        token_out_address=settings.hyperevm_usdt0,
        token_in_decimals=settings.hyperevm_usdc_decimals,
        token_out_decimals=settings.hyperevm_usdt0_decimals,
    )
    hybra_pool_reverse = PoolModel(
        pool_id="hybra_v3_usdt0_usdc_5",
        fee_bps=settings.hyperevm_hybra_fee_bps,
        mid_price=Decimal("0"),
        liquidity_usd=Decimal("0"),
        pool_address=settings.hyperevm_hybra_pool_usdc_usdt0,
        token_in_symbol="USDT0",
        token_out_symbol="USDC",
        token_in_address=settings.hyperevm_usdt0,
        token_out_address=settings.hyperevm_usdc,
        token_in_decimals=settings.hyperevm_usdt0_decimals,
        token_out_decimals=settings.hyperevm_usdc_decimals,
    )

    return {
        "ramses_v3": RealRamsesV3Adapter(
            settings,
            settings.hyperevm_rpc_url,
            settings.hyperevm_ramses_quoter,
            {
                ramses_pool_forward.pool_id: ramses_pool_forward,
                ramses_pool_reverse.pool_id: ramses_pool_reverse,
            },
            chain_slug="hyperliquid",
            quoter_mode=settings.hyperevm_ramses_quoter_mode,
        ),
        "hybra_v3": RealHybraV3Adapter(
            settings,
            settings.hyperevm_rpc_url,
            settings.hyperevm_hybra_quoter,
            {
                hybra_pool_forward.pool_id: hybra_pool_forward,
                hybra_pool_reverse.pool_id: hybra_pool_reverse,
            },
            chain_slug="hyperliquid",
            quoter_mode=settings.hyperevm_hybra_quoter_mode,
        ),
        "hybra_v4_observer": RealHybraV4ObserverAdapter(
            settings,
            settings.hyperevm_rpc_url,
            settings.hyperevm_hybra_quoter,
            {hybra_pool_forward.pool_id: hybra_pool_forward},
            chain_slug="hyperliquid",
            quoter_mode=settings.hyperevm_hybra_quoter_mode,
        ),
    }


def build_hyperevm_dex_adapters(settings: Settings) -> dict[str, DEXAdapter]:
    if settings.use_mock_market_data:
        return _build_hyperevm_mock_adapters(settings)
    return _build_hyperevm_real_adapters(settings)


def build_cex_adapters(settings: Settings) -> dict[str, CEXAdapter]:
    if settings.use_mock_market_data:
        return {
            "bybit": MockCEXAdapter("bybit", settings),
            "mexc": MockCEXAdapter("mexc", settings),
        }
    return {
        "bybit": BybitSpotAdapter(settings),
        "mexc": MEXCSpotAdapter(settings),
    }


def build_shadow_dex_adapters(settings: Settings) -> dict[str, DEXAdapter]:
    if settings.use_mock_market_data:
        return build_base_mock_adapters(settings)
    return build_base_real_adapters(settings)
