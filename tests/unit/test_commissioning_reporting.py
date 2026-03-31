from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.commissioning.reporting import (
    commissioning_report_payload,
    daily_summary_payload,
    render_commissioning_report_markdown,
    render_daily_summary_markdown,
)


def test_commissioning_report_payload_schema_is_stable() -> None:
    generated = datetime(2026, 3, 31, 0, 0, tzinfo=timezone.utc)
    payload = commissioning_report_payload(
        summary={"total_routes": 1},
        routes=[{"route_id": "r1", "strategy": "hyperevm_dex_dex"}],
        generated_at=generated,
    )
    assert payload["generated_at"] == generated.isoformat()
    assert "summary" in payload
    assert "routes" in payload


def test_render_commissioning_report_markdown_contains_route_sections() -> None:
    md = render_commissioning_report_markdown(
        summary={"total_routes": 1, "latest_backtest_mode": "market_snapshots"},
        routes=[
            {
                "route_id": "route-1",
                "strategy": "hyperevm_dex_dex",
                "phase": "phase_3_commissioning_review",
                "route_type": "live_intent",
                "readiness_grade": "yellow",
                "promotion_gate_status": "review_ready",
                "observation_window_days": Decimal("15"),
                "market_snapshot_count": 6000,
                "opportunity_count": 450,
                "backtest_run_count_total": 6,
                "backtest_run_count_market_snapshots": 3,
                "backtest_run_count_opportunities": 3,
                "quote_unavailable_rate": Decimal("0.01"),
                "health_unknown_rate": Decimal("0.02"),
                "fee_unverified_rate": Decimal("0.02"),
                "balance_unverified_rate": Decimal("0.01"),
                "quote_mismatch_rate": Decimal("0.01"),
                "gate_blockers": ["readiness_grade"],
                "human_action_items": ["Collect one more backtest window."],
            }
        ],
    )
    assert "# Commissioning Report" in md
    assert "## Route `route-1`" in md
    assert "major_blockers" in md
    assert "action_items" in md


def test_render_daily_summary_markdown_includes_expected_sections() -> None:
    md = render_daily_summary_markdown(
        summary={
            "total_routes": 2,
            "review_ready_count": 1,
            "observation_ready_count": 1,
            "promotion_blocked_count": 0,
            "gate_fail_route_count": 0,
            "gate_warn_route_count": 1,
            "latest_backtest_mode": "opportunities",
            "top_blockers": [{"blocker": "quote_unavailable_rate", "count": 3}],
            "quote_unavailable_worst_routes": [
                {
                    "route_id": "route-bad",
                    "strategy": "base_virtual_shadow",
                    "quote_unavailable_rate": "0.22",
                    "promotion_gate_status": "not_ready",
                }
            ],
            "best_candidate_routes": [
                {
                    "rank": 1,
                    "route_id": "route-good",
                    "strategy": "hyperevm_dex_dex",
                    "score": "81.2",
                    "promotion_gate_status": "review_ready",
                }
            ],
        }
    )
    assert "# Daily Commissioning Summary" in md
    assert "Top Blockers" in md
    assert "Worst Quote Unavailable Routes" in md
    assert "Best Candidate Routes" in md


def test_daily_summary_payload_schema_is_stable() -> None:
    generated = datetime(2026, 3, 31, 12, 0, tzinfo=timezone.utc)
    payload = daily_summary_payload(summary={"total_routes": 4}, generated_at=generated)
    assert payload["generated_at"] == generated.isoformat()
    assert "daily_summary" in payload
