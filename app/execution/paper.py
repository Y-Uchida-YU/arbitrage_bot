from __future__ import annotations

from decimal import Decimal

from app.execution.interface import ExecutionEngine
from app.quote_engine.types import RouteQuote


class PaperExecutionEngine(ExecutionEngine):
    async def simulate(self, opportunity: RouteQuote) -> dict[str, str | bool]:
        return {
            "ok": True,
            "mode": "paper",
            "action": "simulate",
            "expected_pnl": str(opportunity.modeled_net_edge_amount),
        }

    async def execute(self, opportunity: RouteQuote) -> dict[str, str | bool]:
        realized = opportunity.modeled_net_edge_amount - Decimal("0.02")
        return {
            "ok": True,
            "mode": "paper",
            "action": "execute",
            "tx_hash": "paper-simulated",
            "realized_pnl": str(realized),
        }

    async def dry_run(self, opportunity: RouteQuote) -> dict[str, str | bool]:
        return {
            "ok": True,
            "mode": "paper",
            "action": "dry_run",
            "expected_final": str(opportunity.final_amount),
        }

    async def cancel_all(self) -> dict[str, str | bool]:
        return {"ok": True, "mode": "paper", "action": "cancel_all", "message": "no-op"}