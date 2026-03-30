from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.config.settings import RunMode, Settings
from app.exchanges.cex.base import CEXAdapter
from app.exchanges.dex.base import DEXAdapter
from app.exchanges.errors import QuoteUnavailableError
from app.models.core import Route
from app.quote_engine.edge import ModeledEdgeCalculator
from app.quote_engine.types import RouteQuote
from app.utils.confidence import min_fee_confidence
from app.utils.decimal_math import to_bps


def _cex_fee_status_from_provenance(provenance: str) -> str:
    normalized = provenance.strip().lower()
    if normalized == "fallback_only":
        return "fallback_only"
    if normalized in {"config_only"}:
        return "config_only"
    if normalized in {"venue_declared", "symbol_override", "venue_default"}:
        return "venue_declared"
    if normalized in {"acct_verified", "account_verified"}:
        return "acct_verified"
    return "unknown"


def _dex_fee_status(
    *,
    pool_state: dict[str, Decimal | str | bool],
    configured_pool_fee_tier: int,
    source_type: str,
) -> tuple[str, str]:
    if source_type == "mock":
        return "config_only", "mock_config"

    pool_fee_raw = pool_state.get("pool_fee_tier")
    try:
        pool_fee = int(Decimal(str(pool_fee_raw)))
    except Exception:
        pool_fee = 0
    if pool_fee <= 0:
        return "config_only", "config_only"
    if configured_pool_fee_tier > 0 and pool_fee != configured_pool_fee_tier:
        return "unknown", "pool_fee_mismatch"
    return "chain_verified", "chain_pool_fee"


class HyperDexDexQuoteEngine:
    def __init__(
        self,
        settings: Settings,
        edge_calculator: ModeledEdgeCalculator,
        dex_adapters: dict[str, DEXAdapter],
    ) -> None:
        self.settings = settings
        self.edge_calculator = edge_calculator
        self.dex_adapters = dex_adapters
        self._edge_started_at: dict[str, datetime] = {}

    async def quote_route(self, route: Route, amount_in: Decimal, mode_profile: RunMode) -> RouteQuote:
        start = datetime.now(timezone.utc)

        adapter_a = self.dex_adapters[route.venue_a]
        adapter_b = self.dex_adapters[route.venue_b]

        if not adapter_a.supported or not adapter_b.supported:
            raise QuoteUnavailableError(
                "quote_unavailable",
                f"unsupported adapter route={route.name} a={adapter_a.support_reason} b={adapter_b.support_reason}",
            )

        out_leg1 = await adapter_a.quote_exact_input(
            "USDC",
            "USDT0",
            amount_in,
            fee_tier=route.quoter_fee_tier_a,
            pool_id=route.pool_a,
        )
        out_leg2 = await adapter_b.quote_exact_input(
            "USDT0",
            "USDC",
            out_leg1,
            fee_tier=route.quoter_fee_tier_b,
            pool_id=route.pool_b,
        )

        gas_units_a = await adapter_a.estimate_gas({"route": route.name})
        gas_units_b = await adapter_b.estimate_gas({"route": route.name})
        total_gas_units = gas_units_a + gas_units_b

        gas_cost_usdc = self._estimate_gas_usdc(total_gas_units)
        raw_spread = out_leg2 - amount_in
        raw_edge_bps = to_bps(raw_spread, amount_in)

        dex_fee_cost = self._estimate_dex_fee_cost(
            amount_in,
            route.economic_fee_bps_a,
            route.economic_fee_bps_b,
        )

        edge = self.edge_calculator.calculate(
            initial_amount=amount_in,
            expected_final_amount=out_leg2,
            dex_fee_cost=dex_fee_cost,
            gas_cost=gas_cost_usdc,
        )

        end = datetime.now(timezone.utc)
        quote_age_seconds = Decimal((end - start).total_seconds())
        slippage_bps = Decimal("1")
        persisted_seconds = self._update_persistence(
            route.id,
            edge.modeled_net_edge_bps,
            use_live_profile=(mode_profile == RunMode.LIVE),
        )

        pool_health_a = await adapter_a.is_pool_healthy(route.pool_a)
        pool_health_b = await adapter_b.is_pool_healthy(route.pool_b)
        pool_state_a = await adapter_a.get_pool_state(route.pool_a)
        pool_state_b = await adapter_b.get_pool_state(route.pool_b)
        liq_a = await adapter_a.get_liquidity_snapshot(route.pool_a)
        liq_b = await adapter_b.get_liquidity_snapshot(route.pool_b)
        quote_match_ok = await self._quote_match_hyper(route, amount_in, out_leg1, adapter_a)
        quote_match_status = "matched" if quote_match_ok else "mismatch"

        fee_status_a, fee_provenance_a = _dex_fee_status(
            pool_state=pool_state_a,
            configured_pool_fee_tier=route.pool_fee_tier_a,
            source_type="mock" if self.settings.use_mock_market_data else "real",
        )
        fee_status_b, fee_provenance_b = _dex_fee_status(
            pool_state=pool_state_b,
            configured_pool_fee_tier=route.pool_fee_tier_b,
            source_type="mock" if self.settings.use_mock_market_data else "real",
        )
        fee_known_status = min_fee_confidence([fee_status_a, fee_status_b])
        smaller_pool_liquidity_usdc = min(
            liq_a.get("liquidity_usd", Decimal("0")),
            liq_b.get("liquidity_usd", Decimal("0")),
        )

        return RouteQuote(
            route_id=route.id,
            strategy=route.strategy,
            pair=route.pair,
            direction=route.direction,
            initial_amount=amount_in,
            final_amount=out_leg2,
            raw_spread_amount=raw_spread,
            raw_edge_bps=raw_edge_bps,
            modeled_net_edge_amount=edge.modeled_net_edge_amount,
            modeled_net_edge_bps=edge.modeled_net_edge_bps,
            expected_slippage_bps=slippage_bps,
            gas_cost_usdc=gas_cost_usdc,
            quote_age_seconds=quote_age_seconds,
            all_costs=edge.cost_breakdown.total,
            persisted_seconds=persisted_seconds,
            metadata={
                "pool_health": str(pool_health_a and pool_health_b).lower(),
                "venues": f"{route.venue_a}->{route.venue_b}",
                "smaller_pool_liquidity_usdc": str(smaller_pool_liquidity_usdc),
                "pool_a_liquidity_usdc": str(liq_a.get("liquidity_usd", Decimal("0"))),
                "pool_b_liquidity_usdc": str(liq_b.get("liquidity_usd", Decimal("0"))),
                "pool_fee_tier_a": str(route.pool_fee_tier_a),
                "pool_fee_tier_b": str(route.pool_fee_tier_b),
                "quoter_fee_tier_a": str(route.quoter_fee_tier_a),
                "quoter_fee_tier_b": str(route.quoter_fee_tier_b),
                "economic_fee_bps_a": str(route.economic_fee_bps_a),
                "economic_fee_bps_b": str(route.economic_fee_bps_b),
                "fee_known": str(fee_known_status != "unknown").lower(),
                "fee_known_status": fee_known_status,
                "fee_source": fee_provenance_a,
                "fee_provenance": f"{fee_provenance_a}|{fee_provenance_b}",
                "quote_match": str(quote_match_ok).lower(),
                "quote_match_status": quote_match_status,
                "quote_source": "mock" if self.settings.use_mock_market_data else "real",
                "leg1_amount_out": str(out_leg1),
                "leg2_amount_out": str(out_leg2),
                "initial_amount": str(amount_in),
                "final_amount": str(out_leg2),
            },
        )

    def _estimate_dex_fee_cost(self, amount_in: Decimal, fee_a_bps: int, fee_b_bps: int) -> Decimal:
        total_bps = Decimal(fee_a_bps + fee_b_bps)
        return (amount_in * total_bps / Decimal(10000)).quantize(Decimal("0.00000001"))

    def _estimate_gas_usdc(self, gas_units: int) -> Decimal:
        gas_native = Decimal(gas_units) * self.settings.gas_price_gwei_default * Decimal("0.000000001")
        return (gas_native * self.settings.gas_token_price_usdc).quantize(Decimal("0.00000001"))

    def _update_persistence(self, route_id: str, modeled_edge_bps: Decimal, use_live_profile: bool) -> Decimal:
        threshold = Decimal(self.settings.live_min_net_edge_bps if use_live_profile else self.settings.shadow_min_net_edge_bps)
        now = datetime.now(timezone.utc)
        if modeled_edge_bps >= threshold:
            first_seen = self._edge_started_at.setdefault(route_id, now)
            return Decimal((now - first_seen).total_seconds())
        self._edge_started_at.pop(route_id, None)
        return Decimal("0")

    async def _quote_match_hyper(
        self,
        route: Route,
        amount_in: Decimal,
        out_leg1: Decimal,
        adapter_a: DEXAdapter,
    ) -> bool:
        try:
            leg1_back_in = await adapter_a.quote_exact_output(
                "USDC",
                "USDT0",
                out_leg1,
                fee_tier=route.quoter_fee_tier_a,
                pool_id=route.pool_a,
            )
            if amount_in <= 0:
                return False
            deviation = abs((leg1_back_in - amount_in) / amount_in)
            return deviation <= Decimal("0.01")
        except Exception:
            return False


class ShadowCexDexQuoteEngine:
    def __init__(
        self,
        settings: Settings,
        edge_calculator: ModeledEdgeCalculator,
        cex_adapters: dict[str, CEXAdapter],
        dex_adapters: dict[str, DEXAdapter],
    ) -> None:
        self.settings = settings
        self.edge_calculator = edge_calculator
        self.cex_adapters = cex_adapters
        self.dex_adapters = dex_adapters
        self._edge_started_at: dict[str, datetime] = {}

    async def quote_route(self, route: Route, amount_in_usdc: Decimal) -> RouteQuote:
        start = datetime.now(timezone.utc)

        cex = self.cex_adapters[route.venue_a]
        dex = self.dex_adapters[route.venue_b]

        if not dex.supported:
            raise QuoteUnavailableError("quote_unavailable", f"dex unsupported {route.venue_b}: {dex.support_reason}")

        status = await cex.get_market_status("VIRTUALUSDC")
        if status != "trading":
            raise QuoteUnavailableError("quote_unavailable", f"cex market not trading: {route.venue_a} status={status}")

        virtual_amount = await dex.quote_exact_input("USDC", "VIRTUAL", amount_in_usdc)
        cex_bid, _cex_ask = await cex.get_best_bid_ask("VIRTUALUSDC")

        expected_usdc = virtual_amount * cex_bid
        cex_fee_bps, cex_fee_provenance = await cex.get_trading_fee_details(
            "VIRTUALUSDC",
            side="sell",
            maker_or_taker="taker",
        )
        cex_fee_cost = expected_usdc * Decimal(cex_fee_bps) / Decimal(10000)
        dex_fee_cost = amount_in_usdc * Decimal(route.economic_fee_bps_b) / Decimal(10000)

        gas_units = await dex.estimate_gas({"route": route.name})
        gas_cost_usdc = self._estimate_gas_usdc(gas_units)

        raw_spread = expected_usdc - amount_in_usdc
        raw_edge_bps = to_bps(raw_spread, amount_in_usdc)

        edge = self.edge_calculator.calculate(
            initial_amount=amount_in_usdc,
            expected_final_amount=expected_usdc,
            dex_fee_cost=cex_fee_cost + dex_fee_cost,
            gas_cost=gas_cost_usdc,
        )

        end = datetime.now(timezone.utc)
        quote_age_seconds = Decimal((end - start).total_seconds())
        persisted_seconds = self._update_persistence(route.id, edge.modeled_net_edge_bps)
        pool_health = await dex.is_pool_healthy(route.pool_b)
        pool_liq = await dex.get_liquidity_snapshot(route.pool_b)
        pool_state = await dex.get_pool_state(route.pool_b)
        quote_match_ok = await self._quote_match_shadow(dex, amount_in_usdc, virtual_amount, route)
        quote_match_status = "matched" if quote_match_ok else "mismatch"
        dex_fee_status, dex_fee_provenance = _dex_fee_status(
            pool_state=pool_state,
            configured_pool_fee_tier=route.pool_fee_tier_b,
            source_type="mock" if self.settings.use_mock_market_data else "real",
        )
        cex_fee_status = _cex_fee_status_from_provenance(cex_fee_provenance)
        fee_known_status = min_fee_confidence([cex_fee_status, dex_fee_status])

        return RouteQuote(
            route_id=route.id,
            strategy=route.strategy,
            pair=route.pair,
            direction=route.direction,
            initial_amount=amount_in_usdc,
            final_amount=expected_usdc,
            raw_spread_amount=raw_spread,
            raw_edge_bps=raw_edge_bps,
            modeled_net_edge_amount=edge.modeled_net_edge_amount,
            modeled_net_edge_bps=edge.modeled_net_edge_bps,
            expected_slippage_bps=Decimal("5"),
            gas_cost_usdc=gas_cost_usdc,
            quote_age_seconds=quote_age_seconds,
            all_costs=edge.cost_breakdown.total,
            persisted_seconds=persisted_seconds,
            metadata={
                "pool_health": str(pool_health).lower(),
                "venues": f"{route.venue_a}->{route.venue_b}",
                "smaller_pool_liquidity_usdc": str(pool_liq.get("liquidity_usd", Decimal("0"))),
                "pool_fee_tier_b": str(route.pool_fee_tier_b),
                "quoter_fee_tier_b": str(route.quoter_fee_tier_b),
                "economic_fee_bps_b": str(route.economic_fee_bps_b),
                "fee_known": str(fee_known_status != "unknown").lower(),
                "fee_known_status": fee_known_status,
                "fee_source": cex_fee_provenance,
                "fee_provenance": f"cex:{cex_fee_provenance}|dex:{dex_fee_provenance}",
                "quote_match": str(quote_match_ok).lower(),
                "quote_match_status": quote_match_status,
                "quote_source": "mock" if self.settings.use_mock_market_data else "real",
                "cex_bid": str(cex_bid),
                "cex_fee_bps": str(cex_fee_bps),
                "dex_fee_cost_usdc": str(dex_fee_cost),
                "dex_virtual_amount": str(virtual_amount),
                "initial_amount": str(amount_in_usdc),
                "final_amount": str(expected_usdc),
            },
        )

    def _estimate_gas_usdc(self, gas_units: int) -> Decimal:
        gas_native = Decimal(gas_units) * self.settings.gas_price_gwei_default * Decimal("0.000000001")
        return (gas_native * self.settings.gas_token_price_usdc).quantize(Decimal("0.00000001"))

    def _update_persistence(self, route_id: str, modeled_edge_bps: Decimal) -> Decimal:
        threshold = Decimal(self.settings.shadow_min_net_edge_bps)
        now = datetime.now(timezone.utc)
        if modeled_edge_bps >= threshold:
            first_seen = self._edge_started_at.setdefault(route_id, now)
            return Decimal((now - first_seen).total_seconds())
        self._edge_started_at.pop(route_id, None)
        return Decimal("0")

    async def _quote_match_shadow(
        self,
        dex: DEXAdapter,
        amount_in_usdc: Decimal,
        virtual_amount: Decimal,
        route: Route,
    ) -> bool:
        try:
            usdc_back = await dex.quote_exact_output(
                "USDC",
                "VIRTUAL",
                virtual_amount,
                fee_tier=route.quoter_fee_tier_b,
                pool_id=route.pool_b,
            )
            if amount_in_usdc <= 0:
                return False
            deviation = abs((usdc_back - amount_in_usdc) / amount_in_usdc)
            return deviation <= Decimal("0.02")
        except Exception:
            return False
