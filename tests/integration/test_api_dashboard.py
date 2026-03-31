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

        readiness_summary = client.get("/api/readiness/summary")
        assert readiness_summary.status_code == 200
        summary = readiness_summary.json()
        assert "red_count" in summary

        readiness_routes = client.get("/api/readiness/routes")
        assert readiness_routes.status_code == 200
        assert isinstance(readiness_routes.json(), list)


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
        if not snapshot_rows:
            for _ in range(15):
                time.sleep(0.2)
                snapshots = client.get("/api/market-snapshots")
                assert snapshots.status_code == 200
                snapshot_rows = snapshots.json()
                if snapshot_rows:
                    break
        assert len(snapshot_rows) >= 1

        route_health = client.get("/api/route-health-snapshots")
        assert route_health.status_code == 200
        route_health_rows = route_health.json()
        assert isinstance(route_health_rows, list)
        if not route_health_rows:
            for _ in range(10):
                time.sleep(0.2)
                route_health = client.get("/api/route-health-snapshots")
                assert route_health.status_code == 200
                route_health_rows = route_health.json()
                if route_health_rows:
                    break
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

        snapshot_payload = dict(payload)
        snapshot_payload["replay_mode"] = "market_snapshots"
        snapshot_run = client.post("/api/backtest/run", json=snapshot_payload)
        assert snapshot_run.status_code == 200
        snapshot_body = snapshot_run.json()
        assert snapshot_body["status"] == "completed"
        assert snapshot_body["replay_mode"] == "market_snapshots"

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

        readiness = client.get("/api/readiness/routes")
        assert readiness.status_code == 200
        rows = readiness.json()
        assert isinstance(rows, list)
        assert len(rows) >= 1
        assert "readiness_grade" in rows[0]

        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "Backtest Runs" in dashboard.text
        assert "Backtest Signal Timeline" in dashboard.text
        assert "Route Readiness" in dashboard.text


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


def test_unsupported_route_stays_red_in_readiness(tmp_path: Path) -> None:
    with _boot_client(tmp_path, live_enabled=False, use_mock_market_data=False) as client:
        time.sleep(1.2)
        readiness = client.get("/api/readiness/routes")
        assert readiness.status_code == 200
        rows = readiness.json()
        assert isinstance(rows, list)
        assert len(rows) >= 1
        assert any(
            row["readiness_grade"] == "red" and row["support_status"] != "supported"
            for row in rows
        )


def test_fallback_fee_route_is_not_green(tmp_path: Path) -> None:
    with _boot_client(tmp_path, live_enabled=False, use_mock_market_data=True) as client:
        time.sleep(1.2)
        readiness = client.get("/api/readiness/routes")
        assert readiness.status_code == 200
        rows = readiness.json()
        target = [row for row in rows if row["strategy"] == "base_virtual_shadow"]
        assert target
        assert all(row["readiness_grade"] != "green" for row in target)


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


def test_route_health_and_readiness_return_canonical_statuses(tmp_path: Path) -> None:
    support_allowed = {"supported", "unsupported", "unknown"}
    fee_allowed = {"unknown", "fallback_only", "config_only", "venue_declared", "acct_verified", "chain_verified"}
    balance_allowed = {"unknown", "mismatch", "internal_ok", "db_inventory_ok", "wallet_verified", "venue_verified"}
    quote_allowed = {"unknown", "mismatch", "matched"}

    with _boot_client(tmp_path, live_enabled=False, use_mock_market_data=True) as client:
        time.sleep(1.2)

        health = client.get("/api/route-health-snapshots")
        assert health.status_code == 200
        rows = health.json()
        assert isinstance(rows, list)
        if not rows:
            for _ in range(12):
                time.sleep(0.2)
                health = client.get("/api/route-health-snapshots")
                assert health.status_code == 200
                rows = health.json()
                if rows:
                    break
        assert len(rows) >= 1
        for row in rows:
            assert row["support_status"] in support_allowed
            assert row["fee_known_status"] in fee_allowed
            assert row["balance_match_status"] in balance_allowed
            assert row["quote_match_status"] in quote_allowed

        readiness = client.get("/api/readiness/routes")
        assert readiness.status_code == 200
        readiness_rows = readiness.json()
        assert isinstance(readiness_rows, list)
        assert len(readiness_rows) >= 1
        for row in readiness_rows:
            assert row["support_status"] in support_allowed
            assert row["fee_known_status"] in fee_allowed
            assert row["balance_match_status"] in balance_allowed
            assert row["quote_match_status"] in quote_allowed


def test_readiness_summary_uses_latest_backtest_mode(tmp_path: Path) -> None:
    with _boot_client(tmp_path, live_enabled=False, use_mock_market_data=True) as client:
        time.sleep(1.5)
        routes = client.get("/api/routes")
        assert routes.status_code == 200
        route_rows = routes.json()
        assert len(route_rows) >= 2

        now = datetime.now(timezone.utc)
        payload_a = {
            "token": "test-control-token",
            "strategy": route_rows[0]["strategy"],
            "route_id": route_rows[0]["id"],
            "pair": route_rows[0]["pair"],
            "start_ts": (now - timedelta(hours=1)).isoformat(),
            "end_ts": (now + timedelta(minutes=1)).isoformat(),
            "notes": "summary mode test a",
            "replay_mode": "opportunities",
        }
        run_a = client.post("/api/backtest/run", json=payload_a)
        assert run_a.status_code == 200
        assert run_a.json()["status"] == "completed"

        payload_b = {
            "token": "test-control-token",
            "strategy": route_rows[1]["strategy"],
            "route_id": route_rows[1]["id"],
            "pair": route_rows[1]["pair"],
            "start_ts": (now - timedelta(hours=1)).isoformat(),
            "end_ts": (now + timedelta(minutes=1)).isoformat(),
            "notes": "summary mode test b",
            "replay_mode": "market_snapshots",
        }
        run_b = client.post("/api/backtest/run", json=payload_b)
        assert run_b.status_code == 200
        assert run_b.json()["status"] == "completed"

        summary = client.get("/api/readiness/summary")
        assert summary.status_code == 200
        assert summary.json()["latest_backtest_mode"] == "market_snapshots"


def test_backtest_api_supports_legacy_replay_mode_opt_in(tmp_path: Path) -> None:
    with _boot_client(tmp_path, live_enabled=False, use_mock_market_data=True) as client:
        time.sleep(1.5)
        routes = client.get("/api/routes")
        assert routes.status_code == 200
        route = routes.json()[0]
        now = datetime.now(timezone.utc)
        payload = {
            "token": "test-control-token",
            "strategy": route["strategy"],
            "route_id": route["id"],
            "pair": route["pair"],
            "start_ts": (now - timedelta(hours=1)).isoformat(),
            "end_ts": (now + timedelta(minutes=1)).isoformat(),
            "notes": "legacy replay mode api test",
            "replay_mode": "opportunities_legacy",
        }
        run = client.post("/api/backtest/run", json=payload)
        assert run.status_code == 200
        body = run.json()
        assert body["status"] == "completed"
        assert body["replay_mode"] == "opportunities_legacy"


def test_shadow_route_can_be_yellow_not_forced_red(tmp_path: Path) -> None:
    with _boot_client(tmp_path, live_enabled=False, use_mock_market_data=True) as client:
        time.sleep(2.0)
        routes = client.get("/api/routes")
        assert routes.status_code == 200
        route_rows = routes.json()
        shadow_routes = [row for row in route_rows if row["strategy"] == "base_virtual_shadow"]
        assert shadow_routes
        target = shadow_routes[0]

        now = datetime.now(timezone.utc)
        run = client.post(
            "/api/backtest/run",
            json={
                "token": "test-control-token",
                "strategy": target["strategy"],
                "route_id": target["id"],
                "pair": target["pair"],
                "start_ts": (now - timedelta(hours=1)).isoformat(),
                "end_ts": (now + timedelta(minutes=1)).isoformat(),
                "notes": "shadow readiness test",
                "replay_mode": "opportunities",
            },
        )
        assert run.status_code == 200
        assert run.json()["status"] == "completed"

        found_yellow = False
        for _ in range(80):
            readiness = client.get("/api/readiness/routes")
            assert readiness.status_code == 200
            rows = readiness.json()
            candidate = next((row for row in rows if row["route_id"] == target["id"]), None)
            if candidate and int(candidate["observation_count"]) >= 20 and candidate["readiness_grade"] == "yellow":
                found_yellow = True
                break
            time.sleep(0.25)

        assert found_yellow
