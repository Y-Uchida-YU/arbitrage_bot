# Architecture

## Runtime Components

1. FastAPI application
2. Async SQLAlchemy repository layer
3. Background `BotRunner`
4. Strategy quote engines
5. Risk manager (hard fail-safe)
6. Execution engines (paper + live dry-run)
7. Discord alert service
8. Server-rendered dashboard (Jinja2 + HTMX + Chart.js)

## Data Flow

1. Runner polls enabled routes from DB.
2. Adapters fetch/mock quotes.
3. Quote engine computes raw spread and modeled net edge.
4. Risk manager evaluates strict entry conditions.
5. Opportunity is always persisted with status and blocked reason.
6. If eligible:
   - paper mode: simulated execution + PnL write
   - live mode: dry-run integration path (unless explicitly enabled)
7. Health metrics and alerts are recorded continuously.
8. Dashboard/API read same DB records.

## Safety Gates

- Global + route + pair + strategy pause controls
- Mode guard (`paper` default)
- Live arm guard via confirmation token
- Allowlists for routers/tokens/pools
- Depeg, stale, gas, liquidity, error-rate checks
- Consecutive failure/loss and trade frequency controls

## Persistence

Core tables:

- `strategies`
- `routes`
- `venue_configs`
- `fee_profiles`
- `opportunities`
- `trade_attempts`
- `executions`
- `balances`
- `inventory_snapshots`
- `health_metrics`
- `alerts`
- `kill_switch_events`
- `config_audit_logs`
- `runtime_controls`

All timestamps are stored in UTC. Monetary/ratio fields use decimal numeric columns.

## Live Path Boundary

- Intended live strategy: HyperEVM same-chain DEX-DEX atomic path.
- This implementation intentionally keeps submission disabled by default (`LIVE_EXECUTION_ENABLED=false`) and performs dry-run integration for safe commissioning.
- Solidity `ArbExecutor` contract enforces owner-only, allowlists, deadlines, min-out/min-profit checks, pause, and emergency withdraw.