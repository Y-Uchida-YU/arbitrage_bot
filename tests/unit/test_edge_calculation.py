from decimal import Decimal

from app.config.settings import Settings
from app.quote_engine.edge import ModeledEdgeCalculator


def test_modeled_edge_calculation_includes_costs() -> None:
    settings = Settings()
    calc = ModeledEdgeCalculator(settings)

    result = calc.calculate(
        initial_amount=Decimal("100"),
        expected_final_amount=Decimal("100.8"),
        dex_fee_cost=Decimal("0.1"),
        gas_cost=Decimal("0.05"),
    )

    assert result.cost_breakdown.total > Decimal("0.15")
    assert result.modeled_net_edge_amount < Decimal("0.65")
    assert isinstance(result.modeled_net_edge_bps, Decimal)