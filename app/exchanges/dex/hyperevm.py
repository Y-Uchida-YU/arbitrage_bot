from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
from web3 import Web3

from app.config.settings import Settings
from app.exchanges.dex.base import DEXAdapter
from app.exchanges.errors import QuoteUnavailableError

_QUOTER_V1_ABI: list[dict[str, Any]] = [
    {
        "name": "quoteExactInputSingle",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "tokenIn", "type": "address"},
            {"name": "tokenOut", "type": "address"},
            {"name": "fee", "type": "uint24"},
            {"name": "amountIn", "type": "uint256"},
            {"name": "sqrtPriceLimitX96", "type": "uint160"},
        ],
        "outputs": [{"name": "amountOut", "type": "uint256"}],
    },
    {
        "name": "quoteExactOutputSingle",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "tokenIn", "type": "address"},
            {"name": "tokenOut", "type": "address"},
            {"name": "fee", "type": "uint24"},
            {"name": "amountOut", "type": "uint256"},
            {"name": "sqrtPriceLimitX96", "type": "uint160"},
        ],
        "outputs": [{"name": "amountIn", "type": "uint256"}],
    },
]

_QUOTER_V2_ABI: list[dict[str, Any]] = [
    {
        "name": "quoteExactInputSingle",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {
                "name": "params",
                "type": "tuple",
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"},
                ],
            }
        ],
        "outputs": [
            {"name": "amountOut", "type": "uint256"},
            {"name": "sqrtPriceX96After", "type": "uint160"},
            {"name": "initializedTicksCrossed", "type": "uint32"},
            {"name": "gasEstimate", "type": "uint256"},
        ],
    },
    {
        "name": "quoteExactOutputSingle",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {
                "name": "params",
                "type": "tuple",
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "amount", "type": "uint256"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"},
                ],
            }
        ],
        "outputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "sqrtPriceX96After", "type": "uint160"},
            {"name": "initializedTicksCrossed", "type": "uint32"},
            {"name": "gasEstimate", "type": "uint256"},
        ],
    },
]

_POOL_V3_ABI: list[dict[str, Any]] = [
    {
        "name": "slot0",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [
            {"name": "sqrtPriceX96", "type": "uint160"},
            {"name": "tick", "type": "int24"},
            {"name": "observationIndex", "type": "uint16"},
            {"name": "observationCardinality", "type": "uint16"},
            {"name": "observationCardinalityNext", "type": "uint16"},
            {"name": "feeProtocol", "type": "uint8"},
            {"name": "unlocked", "type": "bool"},
        ],
    },
    {
        "name": "liquidity",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint128"}],
    },
    {
        "name": "fee",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint24"}],
    },
]

_ERC20_DECIMALS_ABI: list[dict[str, Any]] = [
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    }
]


@dataclass(slots=True)
class PoolModel:
    pool_id: str
    fee_bps: int
    mid_price: Decimal
    liquidity_usd: Decimal
    healthy: bool = True
    pool_address: str = ""
    token_in_symbol: str = ""
    token_out_symbol: str = ""
    token_in_address: str = ""
    token_out_address: str = ""
    token_in_decimals: int = 6
    token_out_decimals: int = 6


class MockV3Adapter(DEXAdapter):
    venue = "unknown"
    supported = True
    support_reason = ""

    def __init__(self, settings: Settings, pools: dict[str, PoolModel]) -> None:
        self.settings = settings
        self.pools = pools
        self._last_quote_ts: float | None = None

    async def quote_exact_input(self, token_in: str, token_out: str, amount_in: Decimal) -> Decimal:
        pool = self._find_pool(token_in, token_out)
        gross_out = amount_in * pool.mid_price
        fee = gross_out * Decimal(pool.fee_bps) / Decimal(10000)
        self._last_quote_ts = time.time()
        return (gross_out - fee).quantize(Decimal("0.00000001"))

    async def quote_exact_output(self, token_in: str, token_out: str, amount_out: Decimal) -> Decimal:
        pool = self._find_pool(token_in, token_out)
        gross_in = amount_out / pool.mid_price
        fee = gross_in * Decimal(pool.fee_bps) / Decimal(10000)
        self._last_quote_ts = time.time()
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
            raise QuoteUnavailableError("quote_unavailable", f"unknown pool: {pool_id}")
        return pool.fee_bps

    async def get_liquidity_snapshot(self, pool_id: str) -> dict[str, Decimal]:
        pool = self.pools.get(pool_id)
        if pool is None:
            return {"liquidity_usd": Decimal("0")}
        return {"liquidity_usd": pool.liquidity_usd}

    async def is_pool_healthy(self, pool_id: str) -> bool:
        pool = self.pools.get(pool_id)
        return bool(pool and pool.healthy and pool.liquidity_usd > 0)

    async def get_last_quote_timestamp(self) -> float | None:
        return self._last_quote_ts

    def _find_pool(self, token_in: str, token_out: str) -> PoolModel:
        normalized_in = token_in.upper().strip()
        normalized_out = token_out.upper().strip()
        for pool in self.pools.values():
            if pool.token_in_symbol.upper() == normalized_in and pool.token_out_symbol.upper() == normalized_out:
                return pool
        first = next(iter(self.pools.values()), None)
        if first is None:
            raise QuoteUnavailableError("quote_unavailable", "no pools configured")
        return first


class RealV3LikeAdapter(DEXAdapter):
    venue = "unknown"

    def __init__(
        self,
        settings: Settings,
        rpc_url: str,
        quoter_address: str,
        pools: dict[str, PoolModel],
        chain_slug: str,
        quoter_mode: str = "v2",
    ) -> None:
        self.settings = settings
        self.rpc_url = rpc_url
        self.quoter_address = quoter_address
        self.pools = pools
        self.chain_slug = chain_slug
        self.quoter_mode = quoter_mode
        self._last_quote_ts: float | None = None
        self._decimals_cache: dict[str, int] = {}

        self.supported = bool(rpc_url.strip() and quoter_address.strip() and bool(pools))
        self.support_reason = "" if self.supported else "missing rpc/quoter/pool configuration"

        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": 4.0})) if self.supported else None
        self.quoter = None
        if self.supported and self.w3 is not None:
            try:
                abi = _QUOTER_V2_ABI if quoter_mode == "v2" else _QUOTER_V1_ABI
                self.quoter = self.w3.eth.contract(address=Web3.to_checksum_address(quoter_address), abi=abi)
            except Exception as exc:
                self.supported = False
                self.support_reason = f"invalid quoter config: {exc}"

    async def quote_exact_input(self, token_in: str, token_out: str, amount_in: Decimal) -> Decimal:
        pool = self._find_pool(token_in, token_out)
        if not self.supported or self.quoter is None or self.w3 is None:
            raise QuoteUnavailableError("quote_unavailable", self.support_reason or "quoter not supported")

        token_in_decimals = await self._token_decimals(pool.token_in_address, pool.token_in_decimals)
        token_out_decimals = await self._token_decimals(pool.token_out_address, pool.token_out_decimals)
        amount_in_wei = int((amount_in * (Decimal(10) ** token_in_decimals)).to_integral_value())

        try:
            amount_out_wei = await self._quote_exact_input_wei(pool, amount_in_wei)
            self._last_quote_ts = time.time()
            return (Decimal(amount_out_wei) / (Decimal(10) ** token_out_decimals)).quantize(Decimal("0.00000001"))
        except Exception as exc:
            raise QuoteUnavailableError("quote_unavailable", f"{self.venue} quote failure: {exc}") from exc

    async def quote_exact_output(self, token_in: str, token_out: str, amount_out: Decimal) -> Decimal:
        pool = self._find_pool(token_in, token_out)
        if not self.supported or self.quoter is None or self.w3 is None:
            raise QuoteUnavailableError("quote_unavailable", self.support_reason or "quoter not supported")

        token_in_decimals = await self._token_decimals(pool.token_in_address, pool.token_in_decimals)
        token_out_decimals = await self._token_decimals(pool.token_out_address, pool.token_out_decimals)
        amount_out_wei = int((amount_out * (Decimal(10) ** token_out_decimals)).to_integral_value())

        try:
            amount_in_wei = await self._quote_exact_output_wei(pool, amount_out_wei)
            self._last_quote_ts = time.time()
            return (Decimal(amount_in_wei) / (Decimal(10) ** token_in_decimals)).quantize(Decimal("0.00000001"))
        except Exception as exc:
            raise QuoteUnavailableError("quote_unavailable", f"{self.venue} quote failure: {exc}") from exc

    async def estimate_gas(self, route: dict[str, str]) -> int:
        _ = route
        return 260000

    async def get_pool_state(self, pool_id: str) -> dict[str, Decimal | str | bool]:
        pool = self.pools.get(pool_id)
        if pool is None or not pool.pool_address or self.w3 is None:
            return {"pool_id": pool_id, "healthy": False, "liquidity_usd": Decimal("0")}
        try:
            contract = self.w3.eth.contract(address=Web3.to_checksum_address(pool.pool_address), abi=_POOL_V3_ABI)
            slot0 = await asyncio.to_thread(contract.functions.slot0().call)
            liquidity_raw = await asyncio.to_thread(contract.functions.liquidity().call)
            fee = await asyncio.to_thread(contract.functions.fee().call)
            liquidity_snapshot = await self.get_liquidity_snapshot(pool_id)
            return {
                "pool_id": pool_id,
                "sqrt_price_x96": Decimal(slot0[0]),
                "fee_bps": Decimal(fee),
                "liquidity_raw": Decimal(liquidity_raw),
                "liquidity_usd": liquidity_snapshot.get("liquidity_usd", Decimal("0")),
                "healthy": liquidity_snapshot.get("liquidity_usd", Decimal("0")) > 0,
            }
        except Exception:
            return {"pool_id": pool_id, "healthy": False, "liquidity_usd": Decimal("0")}

    async def get_fee_bps(self, pool_id: str) -> int:
        pool = self.pools.get(pool_id)
        if pool is None:
            raise QuoteUnavailableError("quote_unavailable", f"unknown pool: {pool_id}")
        return pool.fee_bps

    async def get_liquidity_snapshot(self, pool_id: str) -> dict[str, Decimal]:
        pool = self.pools.get(pool_id)
        if pool is None:
            return {"liquidity_usd": Decimal("0")}

        if pool.pool_address:
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    response = await client.get(
                        f"https://api.dexscreener.com/latest/dex/pairs/{self.chain_slug}/{pool.pool_address}"
                    )
                    response.raise_for_status()
                    payload = response.json()
                pair = (payload.get("pairs") or [None])[0]
                if pair and pair.get("liquidity") and pair["liquidity"].get("usd") is not None:
                    return {"liquidity_usd": Decimal(str(pair["liquidity"]["usd"]))}
            except Exception:
                pass

        return {"liquidity_usd": pool.liquidity_usd}

    async def is_pool_healthy(self, pool_id: str) -> bool:
        if not self.supported:
            return False
        snap = await self.get_liquidity_snapshot(pool_id)
        return snap.get("liquidity_usd", Decimal("0")) > 0

    async def get_last_quote_timestamp(self) -> float | None:
        return self._last_quote_ts

    async def _quote_exact_input_wei(self, pool: PoolModel, amount_in_wei: int) -> int:
        if self.quoter is None:
            raise QuoteUnavailableError("quote_unavailable", "quoter missing")
        if self.quoter_mode == "v2":
            params = (
                Web3.to_checksum_address(pool.token_in_address),
                Web3.to_checksum_address(pool.token_out_address),
                amount_in_wei,
                pool.fee_bps,
                0,
            )
            result = await asyncio.to_thread(self.quoter.functions.quoteExactInputSingle(params).call)
            return int(result[0] if isinstance(result, (list, tuple)) else result)
        result = await asyncio.to_thread(
            self.quoter.functions.quoteExactInputSingle(
                Web3.to_checksum_address(pool.token_in_address),
                Web3.to_checksum_address(pool.token_out_address),
                pool.fee_bps,
                amount_in_wei,
                0,
            ).call
        )
        return int(result)

    async def _quote_exact_output_wei(self, pool: PoolModel, amount_out_wei: int) -> int:
        if self.quoter is None:
            raise QuoteUnavailableError("quote_unavailable", "quoter missing")
        if self.quoter_mode == "v2":
            params = (
                Web3.to_checksum_address(pool.token_in_address),
                Web3.to_checksum_address(pool.token_out_address),
                amount_out_wei,
                pool.fee_bps,
                0,
            )
            result = await asyncio.to_thread(self.quoter.functions.quoteExactOutputSingle(params).call)
            return int(result[0] if isinstance(result, (list, tuple)) else result)
        result = await asyncio.to_thread(
            self.quoter.functions.quoteExactOutputSingle(
                Web3.to_checksum_address(pool.token_in_address),
                Web3.to_checksum_address(pool.token_out_address),
                pool.fee_bps,
                amount_out_wei,
                0,
            ).call
        )
        return int(result)

    async def _token_decimals(self, token_address: str, fallback: int) -> int:
        normalized = token_address.lower().strip()
        if not normalized:
            return fallback
        if normalized in self._decimals_cache:
            return self._decimals_cache[normalized]
        if self.w3 is None:
            return fallback
        try:
            token = self.w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=_ERC20_DECIMALS_ABI)
            decimals = int(await asyncio.to_thread(token.functions.decimals().call))
            self._decimals_cache[normalized] = decimals
            return decimals
        except Exception:
            return fallback

    def _find_pool(self, token_in: str, token_out: str) -> PoolModel:
        normalized_in = token_in.upper().strip()
        normalized_out = token_out.upper().strip()
        for pool in self.pools.values():
            if pool.token_in_symbol.upper() == normalized_in and pool.token_out_symbol.upper() == normalized_out:
                return pool
        raise QuoteUnavailableError(
            "quote_unavailable",
            f"pool mapping not found for {self.venue}: {normalized_in}->{normalized_out}",
        )


class RamsesV3Adapter(MockV3Adapter):
    venue = "ramses_v3"


class HybraV3Adapter(MockV3Adapter):
    venue = "hybra_v3"


class HybraV4ObserverAdapter(MockV3Adapter):
    venue = "hybra_v4_observer"


class RealRamsesV3Adapter(RealV3LikeAdapter):
    venue = "ramses_v3"


class RealHybraV3Adapter(RealV3LikeAdapter):
    venue = "hybra_v3"


class RealHybraV4ObserverAdapter(RealV3LikeAdapter):
    venue = "hybra_v4_observer"
