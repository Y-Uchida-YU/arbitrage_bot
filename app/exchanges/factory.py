from __future__ import annotations

from decimal import Decimal

from app.config.settings import Settings
from app.exchanges.cex.base import CEXAdapter
from app.exchanges.cex.bybit import BybitSpotAdapter
from app.exchanges.cex.mexc import MEXCSpotAdapter
from app.exchanges.cex.mock import MockCEXAdapter
from app.exchanges.dex.base import DEXAdapter
from app.exchanges.dex.base_chain import build_base_adapters
from app.exchanges.dex.hyperevm import HybraV3Adapter, HybraV4ObserverAdapter, PoolModel, RamsesV3Adapter


def build_hyperevm_dex_adapters(settings: Settings) -> dict[str, DEXAdapter]:
    mid = settings.mock_hyperevm_usdc_usdt0_mid

    ramses_forward = PoolModel(
        pool_id="ramses_v3_usdc_usdt0_5",
        fee_bps=5,
        mid_price=mid * Decimal("1.006"),
        liquidity_usd=Decimal("500000"),
    )
    ramses_reverse = PoolModel(
        pool_id="ramses_v3_usdt0_usdc_5",
        fee_bps=5,
        mid_price=(Decimal("1") / mid) * Decimal("0.994"),
        liquidity_usd=Decimal("500000"),
    )
    hybra_forward = PoolModel(
        pool_id="hybra_v3_usdc_usdt0_5",
        fee_bps=5,
        mid_price=mid * Decimal("0.994"),
        liquidity_usd=Decimal("450000"),
    )
    hybra_reverse = PoolModel(
        pool_id="hybra_v3_usdt0_usdc_5",
        fee_bps=5,
        mid_price=(Decimal("1") / mid) * Decimal("1.006"),
        liquidity_usd=Decimal("450000"),
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
            )
        },
    )

    return {
        "ramses_v3": ramses,
        "hybra_v3": hybra,
        "hybra_v4_observer": hybra_v4,
    }


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
    return build_base_adapters(settings)
