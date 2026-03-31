from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.app_state import AppState
from app.db.repository import Repository
from app.db.session import get_async_session
from app.models.core import Opportunity
from app.utils.confidence import (
    normalize_balance_confidence,
    normalize_fee_confidence,
    normalize_quote_match_status,
    normalize_support_status,
)
from app.utils.metrics import metrics_store

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/dashboard/templates")


def _enrich_opportunity_row(row: Opportunity) -> dict[str, object]:
    payload: dict[str, object] = {}
    try:
        parsed = json.loads(row.payload_json)
        if isinstance(parsed, dict):
            payload = parsed
    except Exception:
        payload = {}
    return {
        "id": row.id,
        "timestamp": row.timestamp,
        "strategy": row.strategy,
        "pair": row.pair,
        "direction": row.direction,
        "venues": row.venues,
        "raw_edge_bps": row.raw_edge_bps,
        "modeled_edge_bps": row.modeled_edge_bps,
        "expected_pnl_abs": row.expected_pnl_abs,
        "expected_slippage_bps": row.expected_slippage_bps,
        "gas_estimate_usdc": row.gas_estimate_usdc,
        "quote_age_seconds": row.quote_age_seconds,
        "persisted_seconds": row.persisted_seconds,
        "pool_health_ok": row.pool_health_ok,
        "status": row.status,
        "blocked_reason": row.blocked_reason,
        "payload_json": row.payload_json,
        "quote_source": str(payload.get("quote_source", "")),
        "risk_checks": str(payload.get("risk_checks", "")),
        "quote_unavailable_reason": str(payload.get("quote_unavailable_reason", "")),
    }


def _enrich_route_health_row(row: object) -> dict[str, object]:
    return {
        "id": getattr(row, "id"),
        "timestamp": getattr(row, "timestamp"),
        "strategy": getattr(row, "strategy"),
        "route_id": getattr(row, "route_id"),
        "pair": getattr(row, "pair"),
        "rpc_latency_ms": getattr(row, "rpc_latency_ms"),
        "rpc_error_rate_5m": getattr(row, "rpc_error_rate_5m"),
        "db_latency_ms": getattr(row, "db_latency_ms"),
        "quote_latency_ms": getattr(row, "quote_latency_ms"),
        "market_data_staleness_seconds": getattr(row, "market_data_staleness_seconds"),
        "contract_revert_rate": getattr(row, "contract_revert_rate"),
        "alert_send_success_rate": getattr(row, "alert_send_success_rate"),
        "fee_known_status": normalize_fee_confidence(getattr(row, "fee_known_status", "unknown")),
        "quote_match_status": normalize_quote_match_status(getattr(row, "quote_match_status", "unknown")),
        "balance_match_status": normalize_balance_confidence(getattr(row, "balance_match_status", "unknown")),
        "support_status": normalize_support_status(getattr(row, "support_status", "unknown")),
        "cooldown_active": getattr(row, "cooldown_active"),
        "paused": getattr(row, "paused"),
        "metadata_json": getattr(row, "metadata_json", "{}"),
    }


@router.get("/", response_class=HTMLResponse)
async def dashboard_index(request: Request, session: AsyncSession = Depends(get_async_session)) -> HTMLResponse:
    state: AppState = request.app.state.services
    repo = Repository(session)
    overview = await repo.overview()
    opportunities = await repo.list_opportunities(limit=50)
    opportunities_view = [_enrich_opportunity_row(row) for row in opportunities]
    trades = await repo.list_trades(limit=50)
    executions = await repo.list_executions(limit=50)
    balances = await repo.list_balances()
    metrics = await repo.list_health_metrics(limit=100)
    routes = await repo.list_routes()
    runtime_states = await repo.list_route_runtime_states()
    route_health_rows = await repo.list_latest_route_health_snapshots()
    route_health_view = [_enrich_route_health_row(row) for row in route_health_rows]
    readiness_rows = await state.readiness_service.route_readiness_rows(repo)
    readiness_summary = await state.readiness_service.readiness_summary(repo)
    blocked_summary = await repo.blocked_reason_summary(since_minutes=120)
    cooldown_states = [state.risk_manager.get_route_state(route.id) for route in routes]
    global_health = state.health_collector.build_snapshot("global")
    venue_quote_health = state.health_collector.venue_quote_health()
    backtest_runs = await repo.list_backtest_runs(limit=20)
    backtest_results = await repo.list_backtest_results(limit=20)
    run_by_id = {row.id: row for row in backtest_runs}
    backtest_result_rows: list[dict[str, object]] = []
    for row in backtest_results:
        run = run_by_id.get(row.backtest_run_id)
        result_meta: dict[str, object] = {}
        try:
            parsed_meta = json.loads(row.metadata_json)
            if isinstance(parsed_meta, dict):
                result_meta = parsed_meta
        except Exception:
            result_meta = {}
        backtest_result_rows.append(
            {
                "backtest_run_id": row.backtest_run_id,
                "route_id": run.route_id if run else "",
                "parameter_set_id": run.parameter_set_id if run else None,
                "simulated_pnl": row.simulated_pnl,
                "eligible_count": row.eligible_count,
                "blocked_count": row.blocked_count,
                "hit_rate": row.hit_rate,
                "created_at": row.created_at,
                "replay_mode": str(result_meta.get("replay_mode", "opportunities")),
            }
        )
    latest_backtest = backtest_results[0] if backtest_results else None
    latest_backtest_blocked: dict[str, int] = {}
    latest_backtest_trade_points: list[dict[str, object]] = []
    if latest_backtest is not None:
        latest_backtest_meta: dict[str, object] = {}
        try:
            parsed = json.loads(latest_backtest.blocked_reason_json)
            if isinstance(parsed, dict):
                latest_backtest_blocked = {str(k): int(v) for k, v in parsed.items()}
        except Exception:
            latest_backtest_blocked = {}
        try:
            parsed_meta = json.loads(latest_backtest.metadata_json)
            if isinstance(parsed_meta, dict):
                latest_backtest_meta = parsed_meta
        except Exception:
            latest_backtest_meta = {}
        trades_for_latest = await repo.list_backtest_trades(
            run_id=latest_backtest.backtest_run_id,
            limit=500,
        )
        latest_backtest_trade_points = [
            {
                "t": row.timestamp.isoformat(),
                "status": row.status,
                "pnl": float(row.simulated_pnl),
            }
            for row in trades_for_latest
        ]
    else:
        latest_backtest_meta = {}

    chart_points = [
        {"t": row.created_at.isoformat(), "v": float(row.realized_pnl)}
        for row in reversed(executions)
    ]
    opp_points = [
        {
            "t": row.timestamp.isoformat(),
            "status": row.status,
            "edge": float(row.modeled_edge_bps),
            "quote_age": float(row.quote_age_seconds),
        }
        for row in reversed(opportunities)
    ]
    gas_points = [
        {"t": row.timestamp.isoformat(), "v": float(row.value)}
        for row in reversed(metrics)
        if row.name == "gas_now"
    ]
    latency_points = [
        {"t": row.timestamp.isoformat(), "v": float(row.value)}
        for row in reversed(metrics)
        if row.name == "quote_latency_ms"
    ]
    backtest_pnl_points = [
        {"t": row.created_at.isoformat(), "v": float(row.simulated_pnl)}
        for row in reversed(backtest_results)
    ]
    eligible_count = sum(1 for row in opportunities if row.status == "eligible")
    blocked_count = sum(1 for row in opportunities if row.status == "blocked")
    fee_distribution: dict[str, int] = {}
    balance_distribution: dict[str, int] = {}
    for row in route_health_view:
        fee_status = str(row["fee_known_status"])
        balance_status = str(row["balance_match_status"])
        fee_distribution[fee_status] = fee_distribution.get(fee_status, 0) + 1
        balance_distribution[balance_status] = balance_distribution.get(balance_status, 0) + 1

    context = {
        "request": request,
        "overview": overview,
        "opportunities": opportunities_view,
        "trades": trades,
        "executions": executions,
        "balances": balances,
        "metrics": metrics,
        "chart_points": chart_points,
        "opp_points": opp_points,
        "gas_points": gas_points,
        "latency_points": latency_points,
        "eligible_count": eligible_count,
        "blocked_count": blocked_count,
        "blocked_summary": blocked_summary,
        "cooldown_states": cooldown_states,
        "global_health": global_health,
        "venue_quote_health": venue_quote_health,
        "runtime_states": runtime_states,
        "route_health_rows": route_health_view,
        "readiness_rows": readiness_rows,
        "readiness_summary": readiness_summary,
        "backtest_runs": backtest_runs,
        "backtest_results": backtest_results,
        "backtest_result_rows": backtest_result_rows,
        "latest_backtest": latest_backtest,
        "latest_backtest_meta": latest_backtest_meta,
        "latest_backtest_blocked": latest_backtest_blocked,
        "backtest_pnl_points": backtest_pnl_points,
        "latest_backtest_trade_points": latest_backtest_trade_points,
        "fee_confidence_distribution": fee_distribution,
        "balance_confidence_distribution": balance_distribution,
        "live_arm_state": state.live_engine.runtime_armed,
        "metric_snapshot": metrics_store.snapshot(),
    }
    return templates.TemplateResponse(request, "index.html", context)


@router.get("/dashboard/opportunities", response_class=HTMLResponse)
async def opportunities_fragment(
    request: Request,
    strategy: str | None = None,
    pair: str | None = None,
    venue: str | None = None,
    route_id: str | None = None,
    source_type: str | None = None,
    blocked_reason: str | None = None,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    repo = Repository(session)
    rows = await repo.list_opportunities(
        strategy=strategy,
        pair=pair,
        venue=venue,
        route_id=route_id,
        source_type=source_type,
        blocked_reason=blocked_reason,
        limit=100,
    )
    view_rows = [_enrich_opportunity_row(row) for row in rows]
    return templates.TemplateResponse(request, "partials/opportunities_table.html", {"request": request, "opportunities": view_rows})


@router.get("/dashboard/executions", response_class=HTMLResponse)
async def executions_fragment(request: Request, session: AsyncSession = Depends(get_async_session)) -> HTMLResponse:
    repo = Repository(session)
    rows = await repo.list_executions(limit=100)
    return templates.TemplateResponse(request, "partials/executions_table.html", {"request": request, "executions": rows})


@router.get("/export/opportunities.csv")
async def export_opportunities_csv(session: AsyncSession = Depends(get_async_session)) -> StreamingResponse:
    repo = Repository(session)
    rows = await repo.list_opportunities(limit=5000)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "timestamp",
            "strategy",
            "pair",
            "direction",
            "venues",
            "raw_edge_bps",
            "modeled_edge_bps",
            "expected_pnl_abs",
            "expected_slippage_bps",
            "gas_estimate_usdc",
            "quote_age_seconds",
            "status",
            "blocked_reason",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.timestamp.isoformat(),
                row.strategy,
                row.pair,
                row.direction,
                row.venues,
                row.raw_edge_bps,
                row.modeled_edge_bps,
                row.expected_pnl_abs,
                row.expected_slippage_bps,
                row.gas_estimate_usdc,
                row.quote_age_seconds,
                row.status,
                row.blocked_reason,
            ]
        )

    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=opportunities.csv"},
    )


@router.get("/export/opportunities.json")
async def export_opportunities_json(session: AsyncSession = Depends(get_async_session)) -> JSONResponse:
    repo = Repository(session)
    rows = await repo.list_opportunities(limit=5000)
    payload = [
        {
            "timestamp": row.timestamp.isoformat(),
            "strategy": row.strategy,
            "pair": row.pair,
            "direction": row.direction,
            "venues": row.venues,
            "raw_edge_bps": str(row.raw_edge_bps),
            "modeled_edge_bps": str(row.modeled_edge_bps),
            "expected_pnl_abs": str(row.expected_pnl_abs),
            "expected_slippage_bps": str(row.expected_slippage_bps),
            "gas_estimate_usdc": str(row.gas_estimate_usdc),
            "quote_age_seconds": str(row.quote_age_seconds),
            "status": row.status,
            "blocked_reason": row.blocked_reason,
        }
        for row in rows
    ]
    return JSONResponse(payload)


@router.get("/export/logs")
async def export_logs() -> PlainTextResponse:
    log_path = Path("logs/app.log")
    if not log_path.exists():
        return PlainTextResponse("log file not found", status_code=404)
    content = log_path.read_text(encoding="utf-8")
    return PlainTextResponse(content, headers={"Content-Disposition": "attachment; filename=app.log"})
