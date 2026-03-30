# Runbook

## Startup

1. Configure `.env` from `.env.example`.
2. Apply migrations: `alembic upgrade head`.
3. Start API/dashboard: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
4. Verify: `GET /api/health` and dashboard load.

If startup fails with schema error:

- confirm Alembic migration is applied
- or set `AUTO_CREATE_SCHEMA=true` only for local/dev sandbox

## Operational Checks

- `GET /api/status` confirms mode and pause flags
- `GET /api/overview` confirms PnL/trade/health summary
- Dashboard opportunities table shows block reasons
- `GET /api/cooldowns` confirms per-route cooldown/failure state
- `GET /api/blocked-reason-summary` confirms guard trend
- `GET /api/market-snapshots` confirms observation persistence
- `GET /api/route-health-snapshots` confirms route health persistence

## Manual Controls

All control endpoints require `CONTROL_API_TOKEN`.

- Pause globally: `POST /api/control/pause`
- Resume: `POST /api/control/resume`
- Stop all: `POST /api/control/stop-all`
- Disable route: `POST /api/control/disable-route`
- Enable route: `POST /api/control/enable-route`
- Switch mode: `POST /api/control/switch-mode`

## Live Enable Procedure (Conservative)

1. Confirm allowlists are correct.
2. Set `LIVE_ENABLE_FLAG=true`.
3. Keep `LIVE_EXECUTION_ENABLED=false` during commissioning.
4. Call `/api/control/switch-mode` with both control token and `live_confirmation_token`.
5. Validate dry-run behavior, guard statuses, and alerting.
6. Only after sign-off, enable real execution path (not enabled by default in this version).

## Real-Data Commissioning Notes

- `USE_MOCK_MARKET_DATA=false` enables real-data capable adapters.
- If quoter/pool/token config is missing for a venue, it is treated as `quote_unavailable` and blocked.
- This is expected fail-safe behavior, not a runtime crash.
- Route runtime state (`route_runtime_states`) is persisted and re-hydrated on restart.

## Replay / Backtest Operations

- API:
  - `POST /api/backtest/run`
  - `GET /api/backtest/runs`
  - `GET /api/backtest/results`
  - `GET /api/backtest/results/{run_id}`
- CLI:
  - `python -m app.main backtest --strategy ... --route-id ... --pair ... --start-ts ... --end-ts ...`
- Always treat backtest assumptions as conservative. Do not use optimistic fill assumptions for readiness decisions.

## Incident Response

1. Trigger `stop-all` immediately.
2. Review `blocked_reason`/`revert_reason`/alerts.
3. Verify RPC/DB/gas/quote health.
4. Re-enable routes one-by-one after root-cause confirmation.

## Alert Events

- startup
- shutdown
- strategy paused/resumed
- kill switch triggered
- trade executed/reverted
- abnormal health
- daily DD stop
- depeg stop
