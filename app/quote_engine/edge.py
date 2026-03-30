from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.config.settings import Settings
from app.utils.decimal_math import apply_bps, to_bps


@dataclass(slots=True)
class CostBreakdown:
    dex_fee_cost: Decimal
    gas_cost: Decimal
    quote_drift_buffer: Decimal
    slippage_buffer: Decimal
    router_overhead: Decimal
    failed_tx_allowance: Decimal
    safety_margin: Decimal

    @property
    def total(self) -> Decimal:
        return (
            self.dex_fee_cost
            + self.gas_cost
            + self.quote_drift_buffer
            + self.slippage_buffer
            + self.router_overhead
            + self.failed_tx_allowance
            + self.safety_margin
        )


@dataclass(slots=True)
class EdgeResult:
    expected_final_amount: Decimal
    modeled_net_edge_amount: Decimal
    modeled_net_edge_bps: Decimal
    cost_breakdown: CostBreakdown


class ModeledEdgeCalculator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def calculate(
        self,
        initial_amount: Decimal,
        expected_final_amount: Decimal,
        dex_fee_cost: Decimal,
        gas_cost: Decimal,
    ) -> EdgeResult:
        quote_drift_buffer = apply_bps(initial_amount, Decimal(self.settings.cost_quote_drift_buffer_bps))
        slippage_buffer = apply_bps(initial_amount, Decimal(self.settings.cost_slippage_buffer_bps))
        router_overhead = apply_bps(initial_amount, Decimal(self.settings.cost_router_overhead_bps))
        failed_tx_allowance = apply_bps(initial_amount, Decimal(self.settings.cost_failed_tx_allowance_bps))
        safety_margin = apply_bps(initial_amount, Decimal(self.settings.cost_safety_margin_bps))

        costs = CostBreakdown(
            dex_fee_cost=dex_fee_cost,
            gas_cost=gas_cost,
            quote_drift_buffer=quote_drift_buffer,
            slippage_buffer=slippage_buffer,
            router_overhead=router_overhead,
            failed_tx_allowance=failed_tx_allowance,
            safety_margin=safety_margin,
        )
        modeled_net_edge_amount = expected_final_amount - initial_amount - costs.total
        modeled_net_edge_bps = to_bps(modeled_net_edge_amount, initial_amount)
        return EdgeResult(
            expected_final_amount=expected_final_amount,
            modeled_net_edge_amount=modeled_net_edge_amount,
            modeled_net_edge_bps=modeled_net_edge_bps,
            cost_breakdown=costs,
        )