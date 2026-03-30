from __future__ import annotations

from abc import ABC, abstractmethod

from app.quote_engine.types import RouteQuote


class ExecutionEngine(ABC):
    @abstractmethod
    async def simulate(self, opportunity: RouteQuote) -> dict[str, str | bool]:
        raise NotImplementedError

    @abstractmethod
    async def execute(self, opportunity: RouteQuote) -> dict[str, str | bool]:
        raise NotImplementedError

    @abstractmethod
    async def dry_run(self, opportunity: RouteQuote) -> dict[str, str | bool]:
        raise NotImplementedError

    @abstractmethod
    async def cancel_all(self) -> dict[str, str | bool]:
        raise NotImplementedError