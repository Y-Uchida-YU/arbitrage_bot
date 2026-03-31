from __future__ import annotations

from decimal import Decimal

import pytest

from app.commissioning.service import CommissioningService
from app.config.settings import Settings
from app.models.core import Route
from app.readiness.service import ReadinessService


def _route(strategy: str, route_id: str) -> Route:
    return Route(
        id=route_id,
        strategy=strategy,
        name=f"{strategy}-{route_id}",
        pair="USDC/USDt0" if strategy == "hyperevm_dex_dex" else "VIRTUAL/USDC",
        direction="forward",
        venue_a="venue_a",
        venue_b="venue_b",
        pool_a="pool_a",
        pool_b="pool_b",
        router_a="router_a",
        router_b="router_b",
    )


def _stats(**overrides: object) -> dict[str, object]:
    baseline: dict[str, object] = {
        "observation_window_days": Decimal("20"),
        "market_snapshot_count": 6000,
        "opportunity_count": 400,
        "backtest_run_count_total": 8,
        "backtest_run_count_market_snapshots": 4,
        "backtest_run_count_opportunities": 4,
        "quote_unavailable_rate": Decimal("0.01"),
        "health_unknown_rate": Decimal("0.01"),
        "fee_unverified_rate": Decimal("0.01"),
        "balance_unverified_rate": Decimal("0.01"),
        "quote_mismatch_rate": Decimal("0.01"),
        "fatal_pause_count": 0,
        "cooldown_event_count": 0,
        "blocked_reason_top_n": [],
        "latest_backtest_pnl": Decimal("1.25"),
        "median_backtest_pnl": Decimal("0.95"),
        "worst_backtest_drawdown": Decimal("0.20"),
    }
    baseline.update(overrides)
    return baseline


def _readiness(**overrides: object) -> dict[str, object]:
    baseline: dict[str, object] = {
        "support_status": "supported",
        "readiness_grade": "green",
        "fatal_paused": False,
        "readiness_blockers": [],
        "human_action_items": [],
    }
    baseline.update(overrides)
    return baseline


def _kpi_status(row: dict[str, object], name: str) -> str:
    evaluations = row["kpi_evaluations"]
    assert isinstance(evaluations, list)
    for item in evaluations:
        if isinstance(item, dict) and item.get("name") == name:
            return str(item.get("status", ""))
    raise AssertionError(f"kpi not found: {name}")


def test_promotion_gate_for_hyperevm_route() -> None:
    service = CommissioningService(Settings(), ReadinessService(Settings()))
    row = service._build_route_row(  # noqa: SLF001 - unit coverage for gate logic
        _route("hyperevm_dex_dex", "r-live"),
        stats=_stats(),
        readiness=_readiness(),
    )

    assert row["route_type"] == "live_intent"
    assert row["promotion_gate_status"] == "review_ready"
    assert row["phase"] == "phase_3_commissioning_review"


def test_promotion_gate_for_shadow_route() -> None:
    service = CommissioningService(Settings(), ReadinessService(Settings()))
    row = service._build_route_row(  # noqa: SLF001 - unit coverage for gate logic
        _route("base_virtual_shadow", "r-shadow"),
        stats=_stats(
            observation_window_days=Decimal("8"),
            market_snapshot_count=3200,
            opportunity_count=220,
            backtest_run_count_total=2,
            backtest_run_count_market_snapshots=0,
            backtest_run_count_opportunities=2,
        ),
        readiness=_readiness(readiness_grade="yellow"),
    )

    assert row["route_type"] == "shadow"
    assert row["promotion_gate_status"] == "observation_ready"
    assert row["readiness_grade"] == "yellow"


def test_insufficient_observation_days_is_fail() -> None:
    service = CommissioningService(Settings(), ReadinessService(Settings()))
    row = service._build_route_row(  # noqa: SLF001 - unit coverage for gate logic
        _route("hyperevm_dex_dex", "r-obs-fail"),
        stats=_stats(observation_window_days=Decimal("2")),
        readiness=_readiness(),
    )

    assert _kpi_status(row, "observation_window_days") == "fail"
    assert row["promotion_gate_status"] == "promotion_blocked"


def test_quote_unavailable_warn_zone_is_not_ready() -> None:
    service = CommissioningService(Settings(), ReadinessService(Settings()))
    row = service._build_route_row(  # noqa: SLF001 - unit coverage for gate logic
        _route("hyperevm_dex_dex", "r-quote-warn"),
        stats=_stats(quote_unavailable_rate=Decimal("0.06")),
        readiness=_readiness(),
    )

    assert _kpi_status(row, "quote_unavailable_rate") == "warn"
    assert row["promotion_gate_status"] == "not_ready"


def test_backtest_count_shortfall_is_fail() -> None:
    service = CommissioningService(Settings(), ReadinessService(Settings()))
    row = service._build_route_row(  # noqa: SLF001 - unit coverage for gate logic
        _route("hyperevm_dex_dex", "r-backtest-fail"),
        stats=_stats(backtest_run_count_market_snapshots=2, backtest_run_count_opportunities=3),
        readiness=_readiness(),
    )

    assert _kpi_status(row, "backtest_run_count_market_snapshots") == "fail"
    assert row["promotion_gate_status"] == "promotion_blocked"


def test_readiness_red_forces_promotion_blocked() -> None:
    service = CommissioningService(Settings(), ReadinessService(Settings()))
    row = service._build_route_row(  # noqa: SLF001 - unit coverage for gate logic
        _route("base_virtual_shadow", "r-readiness-red"),
        stats=_stats(
            observation_window_days=Decimal("8"),
            market_snapshot_count=3200,
            opportunity_count=220,
            backtest_run_count_total=2,
            backtest_run_count_market_snapshots=0,
            backtest_run_count_opportunities=2,
        ),
        readiness=_readiness(readiness_grade="red"),
    )

    assert _kpi_status(row, "readiness_grade") == "fail"
    assert row["promotion_gate_status"] == "promotion_blocked"


def test_commissioning_ranking_score_prioritizes_live_intent_without_shadow_lockout() -> None:
    service = CommissioningService(Settings(), ReadinessService(Settings()))
    live_row = service._build_route_row(  # noqa: SLF001 - unit coverage for ranking logic
        _route("hyperevm_dex_dex", "rank-live"),
        stats=_stats(),
        readiness=_readiness(),
    )
    shadow_row = service._build_route_row(  # noqa: SLF001 - unit coverage for ranking logic
        _route("base_virtual_shadow", "rank-shadow"),
        stats=_stats(
            observation_window_days=Decimal("8"),
            market_snapshot_count=3200,
            opportunity_count=220,
            backtest_run_count_total=2,
            backtest_run_count_market_snapshots=0,
            backtest_run_count_opportunities=2,
        ),
        readiness=_readiness(readiness_grade="yellow"),
    )
    ranked = service._rank_rows([shadow_row, live_row])  # noqa: SLF001 - unit coverage

    assert ranked[0]["route_id"] == "rank-live"
    assert Decimal(str(ranked[0]["score"])) > Decimal(str(ranked[1]["score"]))
    assert Decimal(str(ranked[1]["score"])) > Decimal("0")


@pytest.mark.asyncio
async def test_daily_summary_aggregation_includes_top_blockers_and_best_candidates() -> None:
    service = CommissioningService(Settings(), ReadinessService(Settings()))
    rows = [
        service._build_route_row(  # noqa: SLF001 - unit coverage
            _route("hyperevm_dex_dex", "daily-live"),
            stats=_stats(),
            readiness=_readiness(),
        ),
        service._build_route_row(  # noqa: SLF001 - unit coverage
            _route("base_virtual_shadow", "daily-shadow"),
            stats=_stats(
                observation_window_days=Decimal("2"),
                market_snapshot_count=10,
                opportunity_count=5,
                backtest_run_count_total=0,
                backtest_run_count_market_snapshots=0,
                backtest_run_count_opportunities=0,
                quote_unavailable_rate=Decimal("0.45"),
            ),
            readiness=_readiness(readiness_grade="red"),
        ),
    ]
    summary = {
        "total_routes": 2,
        "routes_review_ready": 1,
        "routes_observation_ready": 0,
        "routes_promotion_blocked": 1,
        "gate_fail_route_count": 1,
        "gate_warn_route_count": 1,
        "latest_backtest_mode": "market_snapshots",
    }

    async def _fake_rows(_: object) -> list[dict[str, object]]:
        return rows

    async def _fake_summary(_: object) -> dict[str, object]:
        return summary

    service.commissioning_route_rows = _fake_rows  # type: ignore[assignment]
    service.commissioning_summary = _fake_summary  # type: ignore[assignment]

    result = await service.daily_summary(repo=object(), top_n=2)

    assert result["total_routes"] == 2
    assert result["top_blockers"]
    assert result["best_candidate_routes"]
    assert result["quote_unavailable_worst_routes"][0]["route_id"] == "daily-shadow"
