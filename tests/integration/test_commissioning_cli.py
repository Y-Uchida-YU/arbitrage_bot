from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _cli_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    db_path = tmp_path / "commissioning_cli.db"
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["AUTO_CREATE_SCHEMA"] = "true"
    env["MODE"] = "paper"
    env["LIVE_EXECUTION_ENABLED"] = "false"
    env["LIVE_ENABLE_FLAG"] = "false"
    env["USE_MOCK_MARKET_DATA"] = "true"
    env["CONTROL_API_TOKEN"] = "test-control-token"
    env["LOG_LEVEL"] = "INFO"
    return env


def _run_cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "app.main", *args],
        cwd=_repo_root(),
        env=_cli_env(tmp_path),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )


def _parse_last_json(stdout: str) -> dict[str, object]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    assert lines
    payload = json.loads(lines[-1])
    assert isinstance(payload, dict)
    return payload


def test_commissioning_report_cli_json_and_route_filter(tmp_path: Path) -> None:
    result = _run_cli(tmp_path, "commissioning-report", "--format", "json")
    assert result.returncode == 0, result.stderr
    payload = _parse_last_json(result.stdout)
    assert "summary" in payload
    assert "routes" in payload
    routes = payload["routes"]
    assert isinstance(routes, list)
    assert routes
    route_id = routes[0]["route_id"]

    filtered = _run_cli(
        tmp_path,
        "commissioning-report",
        "--format",
        "json",
        "--route-id",
        str(route_id),
    )
    assert filtered.returncode == 0, filtered.stderr
    filtered_payload = _parse_last_json(filtered.stdout)
    filtered_routes = filtered_payload["routes"]
    assert isinstance(filtered_routes, list)
    assert len(filtered_routes) == 1
    assert filtered_routes[0]["route_id"] == route_id


def test_daily_commissioning_summary_cli_json_and_markdown(tmp_path: Path) -> None:
    json_result = _run_cli(
        tmp_path,
        "daily-commissioning-summary",
        "--format",
        "json",
        "--send-discord",
    )
    assert json_result.returncode == 0, json_result.stderr
    payload = _parse_last_json(json_result.stdout)
    assert "daily_summary" in payload
    summary = payload["daily_summary"]
    assert isinstance(summary, dict)
    assert "best_candidate_routes" in summary
    assert "top_blockers" in summary

    markdown_result = _run_cli(tmp_path, "daily-commissioning-summary", "--format", "markdown")
    assert markdown_result.returncode == 0, markdown_result.stderr
    assert "# Daily Commissioning Summary" in markdown_result.stdout
