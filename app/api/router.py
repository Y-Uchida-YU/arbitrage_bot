from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    BalanceOut,
    CooldownOut,
    ControlRequest,
    CooldownControlRequest,
    DisableRouteRequest,
    EnableRouteRequest,
    ExecutionOut,
    HealthResponse,
    InventoryOut,
    MetricOut,
    ModeSwitchRequest,
    OpportunityOut,
    RouteOut,
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
    return data


@router.get("/opportunities", response_model=list[OpportunityOut])
async def opportunities(
    strategy: str | None = Query(default=None),
    pair: str | None = Query(default=None),
    venue: str | None = Query(default=None),
    route_id: str | None = Query(default=None),
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
        blocked_reason=blocked_reason,
        limit=limit,
    )
    return [OpportunityOut.model_validate(x, from_attributes=True) for x in rows]


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
            }
        )
    return output


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
    return {"ok": True, "route_id": payload.route_id or "all"}


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
