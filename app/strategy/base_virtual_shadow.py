from __future__ import annotations

from decimal import Decimal

from app.strategy.base import Strategy


class BaseVirtualShadowStrategy(Strategy):
    name = "base_virtual_shadow"

    async def run_once(self, notional: Decimal) -> dict[str, str]:
        _ = notional
        return {"strategy": self.name, "status": "delegated_to_runner"}