from __future__ import annotations

from app.config.settings import Settings
from app.contracts.client import ArbExecutorClient
from app.execution.interface import ExecutionEngine
from app.quote_engine.types import RouteQuote


class LiveDryRunExecutionEngine(ExecutionEngine):
    def __init__(self, settings: Settings, arb_client: ArbExecutorClient | None = None) -> None:
        self.settings = settings
        self.arb_client = arb_client
        self.runtime_armed = False

    def arm_live(self, confirmation_token: str) -> bool:
        if self.settings.allow_live_without_token:
            self.runtime_armed = True
            return True
        if confirmation_token == self.settings.live_confirmation_token.get_secret_value():
            self.runtime_armed = True
            return True
        return False

    def disarm_live(self) -> None:
        self.runtime_armed = False

    async def simulate(self, opportunity: RouteQuote) -> dict[str, str | bool]:
        return {
            "ok": True,
            "mode": "live",
            "action": "simulate",
            "expected_pnl": str(opportunity.modeled_net_edge_amount),
        }

    async def execute(self, opportunity: RouteQuote) -> dict[str, str | bool]:
        if not self.settings.live_enable_flag:
            return {
                "ok": False,
                "mode": "live",
                "action": "execute",
                "blocked_reason": "live_flag_off",
            }
        if not self.runtime_armed:
            return {
                "ok": False,
                "mode": "live",
                "action": "execute",
                "blocked_reason": "live_not_armed",
            }
        if not self.settings.live_execution_enabled:
            return {
                "ok": False,
                "mode": "live",
                "action": "execute",
                "blocked_reason": "live_execution_disabled",
            }
        # Production transaction submission is intentionally disabled by default.
        return {
            "ok": False,
            "mode": "live",
            "action": "execute",
            "blocked_reason": "live_submit_not_implemented",
        }

    async def dry_run(self, opportunity: RouteQuote) -> dict[str, str | bool]:
        if self.arb_client is not None and not self.arb_client.validate_chain():
            return {
                "ok": False,
                "mode": "live",
                "action": "dry_run",
                "blocked_reason": "chain_id_mismatch",
                "atomic_required": True,
            }
        return {
            "ok": True,
            "mode": "live",
            "action": "dry_run",
            "expected_final": str(opportunity.final_amount),
            "atomic_required": True,
        }

    async def cancel_all(self) -> dict[str, str | bool]:
        return {"ok": True, "mode": "live", "action": "cancel_all", "message": "no open orders"}
