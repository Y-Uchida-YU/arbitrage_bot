from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal


def commissioning_report_payload(
    *,
    summary: dict[str, object],
    routes: list[dict[str, object]],
    generated_at: datetime | None = None,
) -> dict[str, object]:
    ts = generated_at or datetime.now(timezone.utc)
    return {
        "generated_at": ts.isoformat(),
        "summary": summary,
        "routes": routes,
    }


def daily_summary_payload(
    *,
    summary: dict[str, object],
    generated_at: datetime | None = None,
) -> dict[str, object]:
    ts = generated_at or datetime.now(timezone.utc)
    return {
        "generated_at": ts.isoformat(),
        "daily_summary": summary,
    }


def render_commissioning_report_markdown(
    *,
    summary: dict[str, object],
    routes: list[dict[str, object]],
    generated_at: datetime | None = None,
) -> str:
    ts = (generated_at or datetime.now(timezone.utc)).isoformat()
    lines = [
        "# Commissioning Report",
        "",
        f"- generated_at: `{ts}`",
        f"- total_routes: `{summary.get('total_routes', 0)}`",
        f"- review_ready: `{summary.get('routes_review_ready', 0)}`",
        f"- observation_ready: `{summary.get('routes_observation_ready', 0)}`",
        f"- promotion_blocked: `{summary.get('routes_promotion_blocked', 0)}`",
        f"- gate_fail_routes: `{summary.get('gate_fail_route_count', 0)}`",
        f"- gate_warn_routes: `{summary.get('gate_warn_route_count', 0)}`",
        f"- latest_backtest_mode: `{summary.get('latest_backtest_mode', 'none')}`",
        "",
    ]
    for row in routes:
        lines.append(f"## Route `{row.get('route_id', '')}`")
        lines.append(f"- strategy: `{row.get('strategy', '')}`")
        lines.append(f"- route_type: `{row.get('route_type', '')}`")
        lines.append(f"- phase: `{row.get('phase', '')}`")
        lines.append(f"- readiness_grade: `{row.get('readiness_grade', '')}`")
        lines.append(f"- promotion_gate_status: `{row.get('promotion_gate_status', '')}`")
        lines.append(f"- observation_window_days: `{row.get('observation_window_days', 0)}`")
        lines.append(f"- market_snapshot_count: `{row.get('market_snapshot_count', 0)}`")
        lines.append(f"- opportunity_count: `{row.get('opportunity_count', 0)}`")
        lines.append(
            "- backtest_counts: "
            f"`total={row.get('backtest_run_count_total', 0)}, "
            f"snap={row.get('backtest_run_count_market_snapshots', 0)}, "
            f"opp={row.get('backtest_run_count_opportunities', 0)}`"
        )
        lines.append(f"- quote_unavailable_rate: `{row.get('quote_unavailable_rate', 0)}`")
        lines.append(f"- health_unknown_rate: `{row.get('health_unknown_rate', 0)}`")
        lines.append(f"- fee_unverified_rate: `{row.get('fee_unverified_rate', 0)}`")
        lines.append(f"- balance_unverified_rate: `{row.get('balance_unverified_rate', 0)}`")
        lines.append(f"- quote_mismatch_rate: `{row.get('quote_mismatch_rate', 0)}`")
        raw_blockers = row.get("gate_blockers", [])
        blockers = [str(item) for item in raw_blockers] if isinstance(raw_blockers, list) else []
        raw_actions = row.get("human_action_items", [])
        actions = [str(item) for item in raw_actions] if isinstance(raw_actions, list) else []
        lines.append("- major_blockers:")
        if blockers:
            for blocker in blockers:
                lines.append(f"  - `{blocker}`")
        else:
            lines.append("  - none")
        lines.append("- action_items:")
        if actions:
            for action in actions:
                lines.append(f"  - {action}")
        else:
            lines.append("  - none")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_daily_summary_markdown(
    *,
    summary: dict[str, object],
    generated_at: datetime | None = None,
) -> str:
    ts = (generated_at or datetime.now(timezone.utc)).isoformat()
    lines = [
        "# Daily Commissioning Summary",
        "",
        f"- generated_at: `{ts}`",
        f"- total_routes: `{summary.get('total_routes', 0)}`",
        f"- review_ready_count: `{summary.get('review_ready_count', 0)}`",
        f"- observation_ready_count: `{summary.get('observation_ready_count', 0)}`",
        f"- promotion_blocked_count: `{summary.get('promotion_blocked_count', 0)}`",
        f"- gate_fail_route_count: `{summary.get('gate_fail_route_count', 0)}`",
        f"- gate_warn_route_count: `{summary.get('gate_warn_route_count', 0)}`",
        f"- latest_backtest_mode: `{summary.get('latest_backtest_mode', 'none')}`",
        "",
        "## Top Blockers",
    ]
    blockers = summary.get("top_blockers", [])
    if isinstance(blockers, list) and blockers:
        for item in blockers:
            name = item.get("blocker", "") if isinstance(item, dict) else ""
            count = item.get("count", 0) if isinstance(item, dict) else 0
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Worst Quote Unavailable Routes")
    worst_routes = summary.get("quote_unavailable_worst_routes", [])
    if isinstance(worst_routes, list) and worst_routes:
        for item in worst_routes:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- `{item.get('route_id', '')}` ({item.get('strategy', '')}) "
                f"rate=`{item.get('quote_unavailable_rate', 0)}` "
                f"gate=`{item.get('promotion_gate_status', '')}`"
            )
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Best Candidate Routes")
    best_routes = summary.get("best_candidate_routes", [])
    if isinstance(best_routes, list) and best_routes:
        for item in best_routes:
            if not isinstance(item, dict):
                continue
            score = _as_decimal(item.get("score", 0))
            lines.append(
                f"- `#{item.get('rank', '-')}` `{item.get('route_id', '')}` "
                f"({item.get('strategy', '')}) score=`{score}` "
                f"gate=`{item.get('promotion_gate_status', '')}`"
            )
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def _as_decimal(raw: object) -> Decimal:
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, int):
        return Decimal(raw)
    if isinstance(raw, float):
        return Decimal(str(raw))
    return Decimal(str(raw or "0"))
