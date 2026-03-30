from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    BalanceOut,
    BacktestResultOut,
    BacktestRunOut,
    BacktestRunRequest,
    BacktestTradeOut,
    CooldownOut,
    ControlRequest,
    CooldownControlRequest,
    DisableRouteRequest,
    EnableRouteRequest,
    ExecutionOut,
    HealthResponse,
    InventoryOut,
    MarketSnapshotOut,
    MetricOut,
    ModeSwitchRequest,
    OpportunityOut,
    ReadinessSummaryOut,
    RouteReadinessOut,
    RouteOut,
    RouteHealthSnapshotOut,
    StrategyControlRequest,
    TradeOut,
    VenueControlRequest,
)
from app.app_state import AppState
from app.config.settings import RunMode
from app.db.repository import Repository
from app.db.session import get_async_session
from app.utils.metrics import metrics_store
from app.utils.replay import ReplayEngine

router = APIRouter(prefix="/api", tags=["api"])
replay_engine = ReplayEngine()


def get_state(request: Request) -> AppState:
    state = getattr(request.app.state, "services", None)
    if state is None:
        raise HTTPException(status_code=500, detail="app state not initialized")
    return state


def _check_control_token(state: AppState, token: str) -> None:
    expected = state.settings.control_api_token.get_secret_value()
    if token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid control token")


def _to_backtest_result_out(row: object) -> BacktestResultOut:
    replay_mode = "unknown"
    try:
        metadata_raw = getattr(row, "metadata_json", "{}")
        parsed = json.loads(metadata_raw)
        if isinstance(parsed, dict):
            replay_mode = str(parsed.get("replay_mode", "unknown"))
    except Exception:
        replay_mode = "unknown"
    return BacktestResultOut(
        id=getattr(row, "id"),
        backtest_run_id=getattr(row, "backtest_run_id"),
        signals=getattr(row, "signals"),
        eligible_count=getattr(row, "eligible_count"),
        blocked_count=getattr(row, "blocked_count"),
        simulated_pnl=getattr(row, "simulated_pnl"),
        hit_rate=getattr(row, "hit_rate"),
        avg_modeled_edge_bps=getattr(row, "avg_modeled_edge_bps"),
        avg_realized_like_pnl=getattr(row, "avg_realized_like_pnl"),
        max_drawdown=getattr(row, "max_drawdown"),
        worst_sequence=getattr(row, "worst_sequence"),
        missed_opportunities=getattr(row, "missed_opportunities"),
        replay_mode=replay_mode,
        blocked_reason_json=getattr(row, "blocked_reason_json"),
        metadata_json=getattr(row, "metadata_json"),
        created_at=getattr(row, "created_at"),
    )


async def _persist_route_state(repo: Repository, state: AppState, route_id: str) -> None:
    current = state.risk_manager.get_route_state(route_id)
    cooldown_until = None
    last_failure_at = None
    raw = str(current.get("cooldown_until", ""))
    if raw:
        try:
            cooldown_until = datetime.fromisoformat(raw)
        except ValueError:
            cooldown_until = None
    last_failure_raw = str(current.get("last_failure_at", ""))
    if last_failure_raw:
        try:
            last_failure_at = datetime.fromisoformat(last_failure_raw)
        except ValueError:
            last_failure_at = None
    await repo.upsert_route_runtime_state(
        route_id=route_id,
        paused=bool(current.get("route_paused", False)),
        cooldown_until=cooldown_until,
        last_failure_category=str(current.get("last_failure_category", "")),
        last_failure_reason=str(current.get("last_failure_reason", "")),
        last_failure_fatal=bool(current.get("last_failure_fatal", False)),
        last_failure_at=last_failure_at,
        consecutive_failures=int(current.get("consecutive_failures", 0)),
        consecutive_losses=int(current.get("consecutive_losses", 0)),
    )


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=datetime.now(timezone.utc))


@router.get("/status")
async def status_endpoint(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str | bool]:
    state = get_state(request)
    repo = Repository(session)
    ctrl = await repo.get_runtime_control()
    return {
        "mode": ctrl.mode,
        "global_pause": ctrl.global_pause,
        "strategy_pause": ctrl.strategy_pause,
        "pair_pause": ctrl.pair_pause,
        "route_pause": ctrl.route_pause,
        "live_guard_armed": state.live_engine.runtime_armed,
    }


@router.get("/overview")
async def overview(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    state = get_state(request)
    repo = Repository(session)
    data = await repo.overview()
    routes = await repo.list_routes()
    cooldowns = [state.risk_manager.get_route_state(route.id) for route in routes]
    snapshot = state.health_collector.build_snapshot("global")

    data["cooldown_routes_count"] = sum(1 for x in cooldowns if int(x["cooldown_remaining_seconds"]) > 0)
    data["unhealthy_venues_count"] = await repo.unhealthy_venues_count(since_minutes=60)
    data["quote_unavailable_count"] = await repo.quote_unavailable_count(since_minutes=60)
    data["degraded_health"] = (
        snapshot.rpc_error_rate_5m > state.settings.rpc_error_rate_stop_pct_5m
        or snapshot.market_data_staleness_seconds > Decimal(state.settings.market_data_staleness_stop_seconds)
        or len(snapshot.quote_unavailable_venues) > 0
    )
    data["live_arm_state"] = state.live_engine.runtime_armed
    data["quote_unavailable_venues"] = snapshot.quote_unavailable_venues
    data["venue_quote_health"] = [asdict(item) for item in state.health_collector.venue_quote_health()]
    readiness_summary = await state.readiness_service.readiness_summary(repo)
    data["readiness_summary"] = readiness_summary
    latest_health_rows = await repo.list_latest_route_health_snapshots()
    fee_distribution: dict[str, int] = {}
    balance_distribution: dict[str, int] = {}
    for row in latest_health_rows:
        fee_distribution[row.fee_known_status] = fee_distribution.get(row.fee_known_status, 0) + 1
        balance_distribution[row.balance_match_status] = balance_distribution.get(row.balance_match_status, 0) + 1
    data["fee_confidence_distribution"] = fee_distribution
    data["balance_confidence_distribution"] = balance_distribution
    return data


@router.get("/opportunities", response_model=list[OpportunityOut])
async def opportunities(
    strategy: str | None = Query(default=None),
    pair: str | None = Query(default=None),
    venue: str | None = Query(default=None),
    route_id: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    blocked_reason: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_async_session),
) -> list[OpportunityOut]:
    repo = Repository(session)
    rows = await repo.list_opportunities(
        strategy=strategy,
        pair=pair,
        venue=venue,
        route_id=route_id,
        source_type=source_type,
        blocked_reason=blocked_reason,
        limit=limit,
    )
    output: list[OpportunityOut] = []
    for row in rows:
        payload: dict[str, object] = {}
        try:
            parsed = json.loads(row.payload_json)
            if isinstance(parsed, dict):
                payload = parsed
        except Exception:
            payload = {}
        output.append(
            OpportunityOut(
                id=row.id,
                timestamp=row.timestamp,
                strategy=row.strategy,
                pair=row.pair,
                direction=row.direction,
                venues=row.venues,
                raw_edge_bps=row.raw_edge_bps,
                modeled_edge_bps=row.modeled_edge_bps,
                expected_pnl_abs=row.expected_pnl_abs,
                expected_slippage_bps=row.expected_slippage_bps,
                gas_estimate_usdc=row.gas_estimate_usdc,
                quote_age_seconds=row.quote_age_seconds,
                persisted_seconds=row.persisted_seconds,
                pool_health_ok=row.pool_health_ok,
                status=row.status,
                blocked_reason=row.blocked_reason,
                payload_json=row.payload_json,
                quote_source=str(payload.get("quote_source", "")),
                risk_checks=str(payload.get("risk_checks", "")),
                quote_unavailable_reason=str(payload.get("quote_unavailable_reason", "")),
            )
        )
    return output


@router.get("/trades", response_model=list[TradeOut])
async def trades(
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_async_session),
) -> list[TradeOut]:
    repo = Repository(session)
    rows = await repo.list_trades(limit=limit)
    return [TradeOut.model_validate(x, from_attributes=True) for x in rows]


@router.get("/executions", response_model=list[ExecutionOut])
async def executions(
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_async_session),
) -> list[ExecutionOut]:
    repo = Repository(session)
    rows = await repo.list_executions(limit=limit)
    return [ExecutionOut.model_validate(x, from_attributes=True) for x in rows]


@router.get("/balances", response_model=list[BalanceOut])
async def balances(session: AsyncSession = Depends(get_async_session)) -> list[BalanceOut]:
    repo = Repository(session)
    rows = await repo.list_balances()
    return [BalanceOut.model_validate(x, from_attributes=True) for x in rows]


@router.get("/inventory", response_model=list[InventoryOut])
async def inventory(
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_async_session),
) -> list[InventoryOut]:
    repo = Repository(session)
    rows = await repo.list_inventory(limit=limit)
    return [InventoryOut.model_validate(x, from_attributes=True) for x in rows]


@router.get("/metrics", response_model=list[MetricOut])
async def metrics(
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_async_session),
) -> list[MetricOut]:
    repo = Repository(session)
    rows = await repo.list_health_metrics(limit=limit)
    return [MetricOut.model_validate(x, from_attributes=True) for x in rows]


@router.get("/market-snapshots", response_model=list[MarketSnapshotOut])
async def market_snapshots(
    strategy: str | None = Query(default=None),
    route_id: str | None = Query(default=None),
    venue: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    session: AsyncSession = Depends(get_async_session),
) -> list[MarketSnapshotOut]:
    repo = Repository(session)
    rows = await repo.list_market_snapshots(strategy=strategy, route_id=route_id, venue=venue, limit=limit)
    return [MarketSnapshotOut.model_validate(x, from_attributes=True) for x in rows]


@router.get("/route-health-snapshots", response_model=list[RouteHealthSnapshotOut])
async def route_health_snapshots(
    route_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    session: AsyncSession = Depends(get_async_session),
) -> list[RouteHealthSnapshotOut]:
    repo = Repository(session)
    rows = await repo.list_route_health_snapshots(route_id=route_id, limit=limit)
    return [RouteHealthSnapshotOut.model_validate(x, from_attributes=True) for x in rows]


@router.get("/routes", response_model=list[RouteOut])
async def routes(session: AsyncSession = Depends(get_async_session)) -> list[RouteOut]:
    repo = Repository(session)
    rows = await repo.list_routes()
    return [RouteOut.model_validate(x, from_attributes=True) for x in rows]


@router.get("/route-health")
async def route_health(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> list[dict[str, object]]:
    state = get_state(request)
    repo = Repository(session)
    routes = await repo.list_routes()
    output: list[dict[str, object]] = []
    for route in routes:
        runtime_row = await repo.get_route_runtime_state(route.id)
        persisted_state = (
            {
                "paused": runtime_row.paused,
                "cooldown_until": runtime_row.cooldown_until.isoformat() if runtime_row.cooldown_until else "",
                "last_failure_category": runtime_row.last_failure_category,
                "last_failure_reason": runtime_row.last_failure_reason,
                "last_failure_fatal": runtime_row.last_failure_fatal,
                "last_failure_at": runtime_row.last_failure_at.isoformat() if runtime_row.last_failure_at else "",
                "consecutive_failures": runtime_row.consecutive_failures,
                "consecutive_losses": runtime_row.consecutive_losses,
            }
            if runtime_row is not None
            else None
        )
        latest_health = await repo.latest_route_health_snapshot(route.id)
        output.append(
            {
                "route_id": route.id,
                "route_name": route.name,
                "strategy": route.strategy,
                "pair": route.pair,
                "enabled": route.enabled,
                "kill_switch": route.kill_switch,
                "risk_state": state.risk_manager.get_route_state(route.id),
                "health_snapshot": asdict(state.health_collector.build_snapshot(route.id)),
                "persisted_runtime_state": persisted_state,
                "persisted_health": (
                    {
                        "fee_known_status": latest_health.fee_known_status,
                        "quote_match_status": latest_health.quote_match_status,
                        "balance_match_status": latest_health.balance_match_status,
                        "support_status": latest_health.support_status,
                        "cooldown_active": latest_health.cooldown_active,
                        "paused": latest_health.paused,
                    }
                    if latest_health
                    else None
                ),
            }
        )
    return output


@router.get("/readiness/routes", response_model=list[RouteReadinessOut])
async def readiness_routes(
    request: Request,
    route_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_async_session),
) -> list[RouteReadinessOut]:
    state = get_state(request)
    repo = Repository(session)
    rows = await state.readiness_service.route_readiness_rows(repo, route_id=route_id)
    return [RouteReadinessOut.model_validate(row) for row in rows]


@router.get("/readiness/routes/{route_id}", response_model=RouteReadinessOut)
async def readiness_route_detail(
    route_id: str,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> RouteReadinessOut:
    state = get_state(request)
    repo = Repository(session)
    rows = await state.readiness_service.route_readiness_rows(repo, route_id=route_id)
    if not rows:
        raise HTTPException(status_code=404, detail="route readiness not found")
    return RouteReadinessOut.model_validate(rows[0])


@router.get("/readiness/summary", response_model=ReadinessSummaryOut)
async def readiness_summary(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> ReadinessSummaryOut:
    state = get_state(request)
    repo = Repository(session)
    summary = await state.readiness_service.readiness_summary(repo)
    return ReadinessSummaryOut.model_validate(summary)


@router.get("/blocked-reason-summary")
async def blocked_reason_summary(
    minutes: int = Query(default=60, ge=1, le=1440),
    session: AsyncSession = Depends(get_async_session),
) -> list[dict[str, object]]:
    repo = Repository(session)
    return await repo.blocked_reason_summary(since_minutes=minutes)


@router.get("/cooldowns", response_model=list[CooldownOut])
async def cooldowns(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> list[CooldownOut]:
    state = get_state(request)
    repo = Repository(session)
    routes = await repo.list_routes()
    out: list[CooldownOut] = []
    for route in routes:
        out.append(CooldownOut.model_validate(state.risk_manager.get_route_state(route.id)))
    return out


@router.post("/control/pause")
async def pause(
    payload: ControlRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str | bool]:
    state = get_state(request)
    _check_control_token(state, payload.token)
    repo = Repository(session)
    await repo.set_global_pause(True)
    await repo.write_kill_switch_event("global", "global", "trigger", "manual_pause")
    state.risk_manager.set_global_kill(True)
    await state.alert_service.send(session, "WARN", "strategy_paused", "global pause activated")
    return {"ok": True, "global_pause": True}


@router.post("/control/resume")
async def resume(
    payload: ControlRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str | bool]:
    state = get_state(request)
    _check_control_token(state, payload.token)
    repo = Repository(session)
    await repo.set_global_pause(False)
    await repo.write_kill_switch_event("global", "global", "release", "manual_resume")
    state.risk_manager.set_global_kill(False)
    await state.alert_service.send(session, "INFO", "strategy_resumed", "global pause released")
    return {"ok": True, "global_pause": False}


@router.post("/control/stop-all")
async def stop_all(
    payload: ControlRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str | bool]:
    state = get_state(request)
    _check_control_token(state, payload.token)
    repo = Repository(session)
    await repo.set_global_pause(True)
    await repo.set_mode(RunMode.STOPPED)
    await repo.write_kill_switch_event("global", "global", "trigger", "stop_all")
    state.risk_manager.set_global_kill(True)
    state.live_engine.disarm_live()
    await state.alert_service.send(session, "WARN", "kill_switch_triggered", "stop-all invoked")
    return {"ok": True, "global_pause": True, "mode": RunMode.STOPPED.value}


@router.post("/control/disable-route")
async def disable_route(
    payload: DisableRouteRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str | bool]:
    state = get_state(request)
    _check_control_token(state, payload.token)
    repo = Repository(session)
    updated = await repo.set_route_enabled(payload.route_id, False)
    await repo.write_kill_switch_event("route", payload.route_id, "trigger", "manual_disable_route")
    state.risk_manager.pause_route(payload.route_id)
    await _persist_route_state(repo, state, payload.route_id)
    return {"ok": updated, "route_id": payload.route_id, "enabled": False}


@router.post("/control/enable-route")
async def enable_route(
    payload: EnableRouteRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str | bool]:
    state = get_state(request)
    _check_control_token(state, payload.token)
    repo = Repository(session)
    updated = await repo.set_route_enabled(payload.route_id, True)
    await repo.write_kill_switch_event("route", payload.route_id, "release", "manual_enable_route")
    state.risk_manager.resume_route(payload.route_id)
    await _persist_route_state(repo, state, payload.route_id)
    return {"ok": updated, "route_id": payload.route_id, "enabled": True}


@router.post("/control/switch-mode")
async def switch_mode(
    payload: ModeSwitchRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str | bool]:
    state = get_state(request)
    _check_control_token(state, payload.token)

    try:
        target = RunMode(payload.target_mode.lower())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid target_mode") from exc

    if target == RunMode.LIVE:
        if not state.settings.live_enable_flag:
            raise HTTPException(status_code=400, detail="live mode disabled by env")
        if not payload.live_confirmation_token:
            raise HTTPException(status_code=400, detail="live_confirmation_token required")
        armed = state.live_engine.arm_live(payload.live_confirmation_token)
        if not armed:
            raise HTTPException(status_code=401, detail="invalid live confirmation token")

    if target != RunMode.LIVE:
        state.live_engine.disarm_live()

    repo = Repository(session)
    ctrl = await repo.set_mode(target)
    if target == RunMode.STOPPED:
        await repo.set_global_pause(True)
        await state.alert_service.send(session, "WARN", "kill_switch_triggered", "mode switched to stopped")
    if target == RunMode.LIVE:
        await state.alert_service.send(session, "INFO", "mode_switch", "live mode armed")
    return {
        "ok": True,
        "mode": ctrl.mode,
        "live_guard_armed": state.live_engine.runtime_armed,
    }


@router.post("/control/disable-venue")
async def disable_venue(
    payload: VenueControlRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str | bool]:
    state = get_state(request)
    _check_control_token(state, payload.token)
    state.risk_manager.pause_venue(payload.venue)
    repo = Repository(session)
    await repo.write_config_audit(
        actor="api",
        action="disable_venue",
        target=f"venue.{payload.venue}",
        before_json="{}",
        after_json="{\"enabled\":false}",
        notes="manual venue disable",
    )
    return {"ok": True, "venue": payload.venue, "enabled": False}


@router.post("/control/enable-venue")
async def enable_venue(
    payload: VenueControlRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str | bool]:
    state = get_state(request)
    _check_control_token(state, payload.token)
    state.risk_manager.resume_venue(payload.venue)
    repo = Repository(session)
    await repo.write_config_audit(
        actor="api",
        action="enable_venue",
        target=f"venue.{payload.venue}",
        before_json="{}",
        after_json="{\"enabled\":true}",
        notes="manual venue enable",
    )
    return {"ok": True, "venue": payload.venue, "enabled": True}


@router.post("/control/pause-strategy")
async def pause_strategy(
    payload: StrategyControlRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str | bool]:
    state = get_state(request)
    _check_control_token(state, payload.token)
    state.risk_manager.pause_strategy(payload.strategy)
    repo = Repository(session)
    await repo.write_config_audit(
        actor="api",
        action="pause_strategy",
        target=f"strategy.{payload.strategy}",
        before_json="{}",
        after_json="{\"paused\":true}",
        notes="manual strategy pause",
    )
    await state.alert_service.send(session, "WARN", "strategy_paused", f"strategy paused: {payload.strategy}")
    return {"ok": True, "strategy": payload.strategy, "paused": True}


@router.post("/control/resume-strategy")
async def resume_strategy(
    payload: StrategyControlRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str | bool]:
    state = get_state(request)
    _check_control_token(state, payload.token)
    state.risk_manager.resume_strategy(payload.strategy)
    repo = Repository(session)
    await repo.write_config_audit(
        actor="api",
        action="resume_strategy",
        target=f"strategy.{payload.strategy}",
        before_json="{}",
        after_json="{\"paused\":false}",
        notes="manual strategy resume",
    )
    await state.alert_service.send(session, "INFO", "strategy_resumed", f"strategy resumed: {payload.strategy}")
    return {"ok": True, "strategy": payload.strategy, "paused": False}


@router.post("/control/clear-cooldown")
async def clear_cooldown(
    payload: CooldownControlRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str | bool]:
    state = get_state(request)
    _check_control_token(state, payload.token)
    state.risk_manager.clear_cooldown(payload.route_id)
    repo = Repository(session)
    await repo.write_config_audit(
        actor="api",
        action="clear_cooldown",
        target=payload.route_id or "all_routes",
        before_json="{}",
        after_json="{}",
        notes="manual cooldown clear",
    )
    if payload.route_id:
        await _persist_route_state(repo, state, payload.route_id)
    else:
        routes = await repo.list_routes()
        for route in routes:
            await _persist_route_state(repo, state, route.id)
    return {"ok": True, "route_id": payload.route_id or "all"}


@router.post("/backtest/run")
async def run_backtest(
    payload: BacktestRunRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, object]:
    state = get_state(request)
    _check_control_token(state, payload.token)
    repo = Repository(session)
    result = await state.backtest_engine.run(
        repo,
        strategy=payload.strategy,
        route_id=payload.route_id,
        pair=payload.pair,
        start_ts=payload.start_ts,
        end_ts=payload.end_ts,
        parameter_set_id=payload.parameter_set_id,
        notes=payload.notes,
        replay_mode=payload.replay_mode,
    )
    return result


@router.get("/backtest/runs", response_model=list[BacktestRunOut])
async def backtest_runs(
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_async_session),
) -> list[BacktestRunOut]:
    repo = Repository(session)
    rows = await repo.list_backtest_runs(limit=limit)
    return [BacktestRunOut.model_validate(x, from_attributes=True) for x in rows]


@router.get("/backtest/results", response_model=list[BacktestResultOut])
async def backtest_results(
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_async_session),
) -> list[BacktestResultOut]:
    repo = Repository(session)
    rows = await repo.list_backtest_results(limit=limit)
    return [_to_backtest_result_out(x) for x in rows]


@router.get("/backtest/results/{run_id}")
async def backtest_result_detail(
    run_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, object]:
    repo = Repository(session)
    result = await repo.get_backtest_result(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="backtest result not found")
    trades = await repo.list_backtest_trades(run_id, limit=5000)
    return {
        "result": _to_backtest_result_out(result),
        "trades": [BacktestTradeOut.model_validate(x, from_attributes=True) for x in trades],
    }


@router.get("/prometheus", response_class=PlainTextResponse)
async def prometheus_metrics() -> str:
    snapshot = metrics_store.snapshot()
    lines: list[str] = []
    for key, value in snapshot.items():
        metric_name = f"arb_{key}".replace("-", "_")
        val = "nan" if value is None else str(value)
        lines.append(f"# TYPE {metric_name} gauge")
        lines.append(f"{metric_name} {val}")
    return "\n".join(lines) + "\n"


@router.get("/simulation/replay")
async def replay_simulation(
    strategy: str | None = Query(default=None),
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    return await replay_engine.replay_expected_pnl(session=session, strategy=strategy)
