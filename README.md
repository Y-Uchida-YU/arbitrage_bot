# Safe-First Arbitrage Bot (HyperEVM DEX-DEX + Base Shadow)

Safety-priority crypto arbitrage framework designed for **risk control before execution quality and profitability**.

## Scope Summary

- Live v1: **HyperEVM DEX-DEX only** (`USDC -> USDt0 -> USDC`) in a single atomic transaction path
- Shadow v1: Base `VIRTUAL/USDC` DEX observation vs Bybit/MEXC spot (paper only)
- Out of scope: CEX-CEX live, leverage, borrowing, flash-loan, bridge, cross-chain

## Safety Principles

- Default mode is `paper`
- Live execution does not run unless all guards are explicitly enabled
- Route/token/router allowlist is enforced
- Atomic single-transaction path is required for live strategy intent
- Unknown fee / stale quote / uncertain health => not tradable

## Setup

1. Copy environment file.

```bash
cp .env.example .env
```

2. Install dependencies.

```bash
pip install -e .[dev]
```

3. Run DB migration.

```bash
alembic upgrade head
```

4. Start app.

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Local Run (Docker)

```bash
docker compose up --build
```

## Paper Mode Startup

- Ensure `.env` contains:

```env
MODE=paper
LIVE_ENABLE_FLAG=false
LIVE_EXECUTION_ENABLED=false
```

- Start service. Bot runner begins opportunity scanning in paper mode.

## Live Mode Enable Conditions

Live mode can only be activated when all are true:

1. `LIVE_ENABLE_FLAG=true`
2. API control token is valid (`CONTROL_API_TOKEN`)
3. Live confirmation token is provided and matches (`LIVE_CONFIRMATION_TOKEN`)
4. `POST /api/control/switch-mode` called with `target_mode=live`

Even after switching to live mode, initial implementation keeps real submission disabled by default:

- `LIVE_EXECUTION_ENABLED=false` => live strategy only performs dry-run integration path.

## Dashboard URL

- [http://localhost:8000/](http://localhost:8000/)

## API Quick List

- `GET /api/health`
- `GET /api/status`
- `GET /api/overview`
- `GET /api/opportunities`
- `GET /api/trades`
- `GET /api/executions`
- `GET /api/balances`
- `GET /api/inventory`
- `GET /api/metrics`
- `POST /api/control/pause`
- `POST /api/control/resume`
- `POST /api/control/stop-all`
- `POST /api/control/disable-route`
- `POST /api/control/enable-route`
- `POST /api/control/switch-mode`
- `POST /api/control/pause-strategy`
- `POST /api/control/resume-strategy`
- `POST /api/control/disable-venue`
- `POST /api/control/enable-venue`
- `POST /api/control/clear-cooldown`

## Environment Variables

See [.env.example](/C:/MyProjects/arbitrageBot/.env.example) for the full list.

High-impact variables:

- `MODE`
- `DATABASE_URL`
- `CONTROL_API_TOKEN`
- `LIVE_ENABLE_FLAG`
- `LIVE_CONFIRMATION_TOKEN`
- `LIVE_EXECUTION_ENABLED`
- `ALLOWLISTED_TOKENS`
- `ALLOWLISTED_ROUTERS`
- `DISCORD_WEBHOOK_URL`
- `LIVE_MIN_NET_EDGE_BPS`
- `SHADOW_MIN_NET_EDGE_BPS`
- `GLOBAL_STALE_QUOTE_STOP_SECONDS`

## Major Risks

- On-chain router behavior mismatch with encoded calldata
- Chain/RPC instability causing stale or bad quotes
- Fee model mismatch across venues/accounts
- Unexpected stablecoin depeg behavior
- Operational mistakes in mode switching

## Kill Switches

- Global pause (`POST /api/control/pause`)
- Stop all (`POST /api/control/stop-all`)
- Per-route disable/enable
- Risk manager automatic blocks (stale quote, gas spike, depeg, liquidity deterioration, consecutive failures/losses)

## Explicitly Out of Scope (This Version)

- CEX-CEX live
- Cross-chain or bridge arbitrage
- Flash loans
- Leverage / borrowing
- Auto-compounding and portfolio optimization
- AI-based threshold auto-tuning
- Multi-hop complex routing optimization

## Project Layout

- `app/config` settings and runtime guards
- `app/db` SQLAlchemy sessions/repository
- `app/models` DB models
- `app/exchanges` CEX/DEX adapters
- `app/quote_engine` modeled edge calculation
- `app/risk` global risk manager and guard functions
- `app/execution` paper/live dry-run execution engines
- `app/contracts` chain interaction helpers
- `app/dashboard` server-rendered UI
- `app/alerts` Discord/webhook alert service
- `app/jobs` bot runner loops
- `app/api` REST API
- `contracts/` Solidity contract sources
- `tests/` unit/integration/contract tests

## Future Extensions

- Real on-chain quoter integration for each DEX adapter
- Signed transaction submission path (currently dry-run by default)
- Fine-grained auth/RBAC for control API
- Strategy-specific dynamic notional control
- Expanded telemetry and SLO-based guard automation
