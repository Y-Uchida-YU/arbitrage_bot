from __future__ import annotations

from decimal import Decimal

import pytest

from app.config.settings import Settings
from app.exchanges.cex.bybit import BybitSpotAdapter
from app.exchanges.cex.mexc import MEXCSpotAdapter


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, params: dict[str, str]):
        _ = url
        _ = params
        return _FakeResponse(self.payload)


@pytest.mark.asyncio
async def test_bybit_real_adapter_happy_path(monkeypatch) -> None:
    settings = Settings(use_mock_market_data=False)
    adapter = BybitSpotAdapter(settings)

    payload = {
        "retCode": 0,
        "result": {"list": [{"bid1Price": "1.01", "ask1Price": "1.02"}]},
    }

    monkeypatch.setattr(
        "app.exchanges.cex.bybit.httpx.AsyncClient",
        lambda timeout: _FakeClient(payload),
    )

    bid, ask = await adapter.get_best_bid_ask("VIRTUALUSDC")
    assert bid == Decimal("1.01")
    assert ask == Decimal("1.02")


@pytest.mark.asyncio
async def test_mexc_real_adapter_happy_path(monkeypatch) -> None:
    settings = Settings(use_mock_market_data=False)
    adapter = MEXCSpotAdapter(settings)

    payload = {"bidPrice": "0.98", "askPrice": "1.00"}

    monkeypatch.setattr(
        "app.exchanges.cex.mexc.httpx.AsyncClient",
        lambda timeout: _FakeClient(payload),
    )

    bid, ask = await adapter.get_best_bid_ask("VIRTUALUSDC")
    assert bid == Decimal("0.98")
    assert ask == Decimal("1.00")