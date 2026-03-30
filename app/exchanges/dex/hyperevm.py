from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.config.settings import Settings
from app.exchanges.dex.base import DEXAdapter


@dataclass(slots=True)
class PoolModel:
    pool_id: str
    fee_bps: int
    mid_price: Decimal
    liquidity_usd: Decimal
    healthy: bool = True


class MockableV3Adapter(DEXAdapter):
    venue = "unknown"

    def __init__(self, settings: Settings, pools: dict[str, PoolModel]) -> None:
        self.settings = settings
        self.pools = pools

    async def quote_exact_input(self, token_in: str, token_out: str, amount_in: Decimal) -> Decimal:
        _ = token_in
        _ = token_out
        pool = self._pick_pool()
        if not self.settings.use_mock_market_data:
            raise RuntimeError("on-chain quoter disabled: mock quotes disabled and live quoter not configured")
        gross_out = amount_in * pool.mid_price
        fee = gross_out * Decimal(pool.fee_bps) / Decimal(10000)
        return (gross_out - fee).quantize(Decimal("0.00000001"))

    async def quote_exact_output(self, token_in: str, token_out: str, amount_out: Decimal) -> Decimal:
        _ = token_in
        _ = token_out
        pool = self._pick_pool()
        if not self.settings.use_mock_market_data:
            raise RuntimeError("on-chain quoter disabled: mock quotes disabled and live quoter not configured")
        gross_in = amount_out / pool.mid_price
        fee = gross_in * Decimal(pool.fee_bps) / Decimal(10000)
        return (gross_in + fee).quantize(Decimal("0.00000001"))

    async def estimate_gas(self, route: dict[str, str]) -> int:
        _ = route
        return 230000

    async def get_pool_state(self, pool_id: str) -> dict[str, Decimal | str | bool]:
        pool = self.pools.get(pool_id)
        if pool is None:
            return {"pool_id": pool_id, "healthy": False, "liquidity_usd": Decimal("0")}
        return {
            "pool_id": pool.pool_id,
            "fee_bps": Decimal(pool.fee_bps),
            "mid_price": pool.mid_price,
            "liquidity_usd": pool.liquidity_usd,
            "healthy": pool.healthy,
        }

    async def get_fee_bps(self, pool_id: str) -> int:
        pool = self.pools.get(pool_id)
        if pool is None:
            raise ValueError(f"unknown pool: {pool_id}")
        return pool.fee_bps

    async def get_liquidity_snapshot(self, pool_id: str) -> dict[str, Decimal]:
        pool = self.pools.get(pool_id)
        if pool is None:
            return {"liquidity_usd": Decimal("0")}
        return {"liquidity_usd": pool.liquidity_usd}

    async def is_pool_healthy(self, pool_id: str) -> bool:
        pool = self.pools.get(pool_id)
        return bool(pool and pool.healthy and pool.liquidity_usd > 0)

    def _pick_pool(self) -> PoolModel:
        pool = next(iter(self.pools.values()), None)
        if pool is None:
            raise ValueError("no pools configured")
        return pool


class RamsesV3Adapter(MockableV3Adapter):
    venue = "ramses_v3"


class HybraV3Adapter(MockableV3Adapter):
    venue = "hybra_v3"


class HybraV4ObserverAdapter(MockableV3Adapter):
    venue = "hybra_v4_observer"