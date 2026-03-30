from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.app_state import AppState
from app.db.repository import Repository
from app.db.session import get_async_session
from app.utils.metrics import metrics_store

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/dashboard/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard_index(request: Request, session: AsyncSession = Depends(get_async_session)) -> HTMLResponse:
    state: AppState = request.app.state.services
    repo = Repository(session)
    overview = await repo.overview()
    opportunities = await repo.list_opportunities(limit=50)
    trades = await repo.list_trades(limit=50)
    executions = await repo.list_executions(limit=50)
    balances = await repo.list_balances()
    metrics = await repo.list_health_metrics(limit=100)
    routes = await repo.list_routes()
    blocked_summary = await repo.blocked_reason_summary(since_minutes=120)
    cooldown_states = [state.risk_manager.get_route_state(route.id) for route in routes]
    global_health = state.health_collector.build_snapshot("global")
    venue_quote_health = state.health_collector.venue_quote_health()

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
    eligible_count = sum(1 for row in opportunities if row.status == "eligible")
    blocked_count = sum(1 for row in opportunities if row.status == "blocked")

    context = {
        "request": request,
        "overview": overview,
        "opportunities": opportunities,
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
        "live_arm_state": state.live_engine.runtime_armed,
        "metric_snapshot": metrics_store.snapshot(),
    }
    return templates.TemplateResponse("index.html", context)


@router.get("/dashboard/opportunities", response_class=HTMLResponse)
async def opportunities_fragment(
    request: Request,
    strategy: str | None = None,
    pair: str | None = None,
    venue: str | None = None,
    route_id: str | None = None,
    blocked_reason: str | None = None,
    session: AsyncSession = Depends(get_async_session),
) -> HTMLResponse:
    repo = Repository(session)
    rows = await repo.list_opportunities(
        strategy=strategy,
        pair=pair,
        venue=venue,
        route_id=route_id,
        blocked_reason=blocked_reason,
        limit=100,
    )
    return templates.TemplateResponse("partials/opportunities_table.html", {"request": request, "opportunities": rows})


@router.get("/dashboard/executions", response_class=HTMLResponse)
async def executions_fragment(request: Request, session: AsyncSession = Depends(get_async_session)) -> HTMLResponse:
    repo = Repository(session)
    rows = await repo.list_executions(limit=100)
    return templates.TemplateResponse("partials/executions_table.html", {"request": request, "executions": rows})


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
