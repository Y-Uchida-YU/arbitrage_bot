from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi.testclient import TestClient


def _boot_client(tmp_path: Path, live_enabled: bool = False) -> TestClient:
    db_path = tmp_path / "test_app.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["CONTROL_API_TOKEN"] = "test-control-token"
    os.environ["LIVE_ENABLE_FLAG"] = "true" if live_enabled else "false"
    os.environ["LIVE_EXECUTION_ENABLED"] = "false"
    os.environ["LIVE_CONFIRMATION_TOKEN"] = "test-live-token"
    os.environ["USE_MOCK_MARKET_DATA"] = "true"
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
    with _boot_client(tmp_path, live_enabled=False) as client:
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


def test_control_and_live_dry_run_flow(tmp_path: Path) -> None:
    with _boot_client(tmp_path, live_enabled=True) as client:
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

        executions = client.get("/api/executions")
        assert executions.status_code == 200
        rows = executions.json()
        assert isinstance(rows, list)
        assert len(rows) >= 1
        assert any(row["tx_status"] == "dry_run" for row in rows)
