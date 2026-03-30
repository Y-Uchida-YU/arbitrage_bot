from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient


def _boot_client(
    tmp_path: Path,
    live_enabled: bool = False,
    use_mock_market_data: bool = True,
    auto_create_schema: bool = True,
) -> TestClient:
    db_path = tmp_path / "test_app.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["AUTO_CREATE_SCHEMA"] = "true" if auto_create_schema else "false"
    os.environ["CONTROL_API_TOKEN"] = "test-control-token"
    os.environ["LIVE_ENABLE_FLAG"] = "true" if live_enabled else "false"
    os.environ["LIVE_EXECUTION_ENABLED"] = "false"
    os.environ["LIVE_CONFIRMATION_TOKEN"] = "test-live-token"
    os.environ["USE_MOCK_MARKET_DATA"] = "true" if use_mock_market_data else "false"
    os.environ["QUOTE_POLL_INTERVAL_SECONDS"] = "0.2"
    os.environ["HEALTH_POLL_INTERVAL_SECONDS"] = "0.5"
    os.environ["LIVE_MIN_EDGE_PERSIST_SECONDS"] = "0"
    os.environ["SHADOW_MIN_EDGE_PERSIST_SECONDS"] = "0"

    from app.config.settings import get_settings

    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()
    return TestClient(app)


def test_dashboard_and_api_bootstrap(tmp_path: Path) -> None:
    with _boot_client(tmp_path, live_enabled=False, use_mock_market_data=True) as client:
        time.sleep(1.5)

        health = client.get("/api/health")
        assert health.status_code == 200

        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "Safety-First Arbitrage Control Room" in dashboard.text

        opportunities = client.get("/api/opportunities")
        assert opportunities.status_code == 200
        rows = opportunities.json()
        assert isinstance(rows, list)
        assert len(rows) >= 1

        overview = client.get("/api/overview")
        assert overview.status_code == 200
        assert "current_mode" in overview.json()
        assert "cooldown_routes_count" in overview.json()

        routes = client.get("/api/routes")
        assert routes.status_code == 200
        assert isinstance(routes.json(), list)

        route_health = client.get("/api/route-health")
        assert route_health.status_code == 200
        assert isinstance(route_health.json(), list)


def test_control_and_live_dry_run_flow(tmp_path: Path) -> None:
    with _boot_client(tmp_path, live_enabled=True, use_mock_market_data=True) as client:
        time.sleep(1.0)

        pause = client.post("/api/control/pause", json={"token": "test-control-token"})
        assert pause.status_code == 200
        assert pause.json()["global_pause"] is True

        resume = client.post("/api/control/resume", json={"token": "test-control-token"})
        assert resume.status_code == 200
        assert resume.json()["global_pause"] is False

        switch = client.post(
            "/api/control/switch-mode",
            json={
                "token": "test-control-token",
                "target_mode": "live",
                "live_confirmation_token": "test-live-token",
            },
        )
        assert switch.status_code == 200
        assert switch.json()["mode"] == "live"

        time.sleep(1.2)

        status = client.get("/api/status")
        assert status.status_code == 200
        assert status.json()["mode"] == "live"

        executions = client.get("/api/executions")
        assert executions.status_code == 200
        rows = executions.json()
        assert isinstance(rows, list)

        trades = client.get("/api/trades")
        assert trades.status_code == 200
        trade_rows = trades.json()
        assert isinstance(trade_rows, list)
        if trade_rows:
            assert any(row["status"] != "submitted" for row in trade_rows)
        elif rows:
            assert any((row.get("tx_status") or "") != "pending" for row in rows)
        else:
            opportunities = client.get("/api/opportunities")
            assert opportunities.status_code == 200
            opportunity_rows = opportunities.json()
            assert isinstance(opportunity_rows, list)
            assert len(opportunity_rows) >= 1
            assert any((row.get("blocked_reason") or "") != "" for row in opportunity_rows)

        cooldowns = client.get("/api/cooldowns")
        assert cooldowns.status_code == 200
        assert isinstance(cooldowns.json(), list)


def test_real_mode_starts_and_unsupported_dex_blocks(tmp_path: Path) -> None:
    with _boot_client(tmp_path, live_enabled=False, use_mock_market_data=False) as client:
        time.sleep(0.8)

        rows = []
        for _ in range(10):
            opportunities = client.get("/api/opportunities")
            assert opportunities.status_code == 200
            rows = opportunities.json()
            assert isinstance(rows, list)
            if rows:
                break
            time.sleep(0.2)

        if rows:
            assert any(
                row["blocked_reason"] in {"quote_unavailable", "liquidity_unavailable", "route_disabled"}
                for row in rows
            )
        else:
            route_health = client.get("/api/route-health")
            assert route_health.status_code == 200
            route_health_rows = route_health.json()
            assert isinstance(route_health_rows, list)
            assert len(route_health_rows) >= 1

        summary = client.get("/api/blocked-reason-summary")
        assert summary.status_code == 200
        assert isinstance(summary.json(), list)


def test_observation_recording_and_backtest_flow(tmp_path: Path) -> None:
    with _boot_client(tmp_path, live_enabled=False, use_mock_market_data=True) as client:
        time.sleep(1.8)

        snapshots = client.get("/api/market-snapshots")
        assert snapshots.status_code == 200
        snapshot_rows = snapshots.json()
        assert isinstance(snapshot_rows, list)
        assert len(snapshot_rows) >= 1

        route_health = client.get("/api/route-health-snapshots")
        assert route_health.status_code == 200
        route_health_rows = route_health.json()
        assert isinstance(route_health_rows, list)
        assert len(route_health_rows) >= 1

        routes = client.get("/api/routes")
        assert routes.status_code == 200
        route_rows = routes.json()
        assert route_rows
        route = route_rows[0]

        now = datetime.now(timezone.utc)
        payload = {
            "token": "test-control-token",
            "strategy": route["strategy"],
            "route_id": route["id"],
            "pair": route["pair"],
            "start_ts": (now - timedelta(hours=1)).isoformat(),
            "end_ts": (now + timedelta(minutes=1)).isoformat(),
            "notes": "integration backtest",
        }
        run = client.post("/api/backtest/run", json=payload)
        assert run.status_code == 200
        run_body = run.json()
        assert run_body["status"] == "completed"
        run_id = run_body["run_id"]

        runs = client.get("/api/backtest/runs")
        assert runs.status_code == 200
        assert isinstance(runs.json(), list)
        assert len(runs.json()) >= 1

        results = client.get("/api/backtest/results")
        assert results.status_code == 200
        assert isinstance(results.json(), list)
        assert len(results.json()) >= 1

        detail = client.get(f"/api/backtest/results/{run_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert "result" in body
        assert "trades" in body
        assert isinstance(body["trades"], list)

        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "Backtest Runs" in dashboard.text
        assert "Backtest Signal Timeline" in dashboard.text


def test_restart_restores_route_runtime_state(tmp_path: Path) -> None:
    route_id = ""
    with _boot_client(tmp_path, live_enabled=False, use_mock_market_data=True) as client:
        time.sleep(1.0)
        routes = client.get("/api/routes")
        assert routes.status_code == 200
        route_rows = routes.json()
        assert route_rows
        route_id = route_rows[0]["id"]

        disable = client.post(
            "/api/control/disable-route",
            json={"token": "test-control-token", "route_id": route_id},
        )
        assert disable.status_code == 200
        assert disable.json()["enabled"] is False

    with _boot_client(tmp_path, live_enabled=False, use_mock_market_data=True) as client:
        time.sleep(1.0)
        cooldowns = client.get("/api/cooldowns")
        assert cooldowns.status_code == 200
        rows = cooldowns.json()
        target = next((x for x in rows if x["route_id"] == route_id), None)
        assert target is not None
        assert target["route_paused"] is True


def test_schema_guard_requires_flag_when_missing_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "guard.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["AUTO_CREATE_SCHEMA"] = "false"
    os.environ["USE_MOCK_MARKET_DATA"] = "true"

    from app.config.settings import get_settings

    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()

    try:
        with TestClient(app):
            assert False, "startup should fail when schema is missing and AUTO_CREATE_SCHEMA=false"
    except RuntimeError:
        assert True
