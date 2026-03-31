# Safe-First Arbitrage Bot (HyperEVM DEX-DEX + Base Shadow)

Safety-priority crypto arbitrage framework designed for **risk control before execution quality and profitability**.

## Scope Summary

- Live v1: **HyperEVM DEX-DEX only** (`USDC -> USDt0 -> USDC`) in a single atomic transaction path
- Shadow v1: Base `VIRTUAL/USDC` DEX observation vs Bybit/MEXC spot (paper only)
- Out of scope: CEX-CEX live, leverage, borrowing, flash-loan, bridge, cross-chain

## Commissioning Focus (Current)

- Real-data observation with conservative blocking semantics
- Observation persistence for post-analysis
- Replay/backtest on saved data for threshold validation (`opportunities` + `market_snapshots`)
- Live-readiness decision support while keeping real submit disabled

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

## Schema Policy (Important)

- Source of truth is Alembic migration.
- Default: `AUTO_CREATE_SCHEMA=false` (conservative)
- If schema is missing and `AUTO_CREATE_SCHEMA=false`, startup fails fast.
- Local-only fallback: set `AUTO_CREATE_SCHEMA=true` when commissioning quick sandbox runs.

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

## Mock / Real Data Switch

- `USE_MOCK_MARKET_DATA=true`
  - deterministic mock adapters for commissioning/UI/test
- `USE_MOCK_MARKET_DATA=false`
  - CEX adapters call real Bybit/MEXC APIs
  - DEX adapters use real quoter path if configured
  - unconfigured/unsupported DEX venue is handled as `quote_unavailable` (blocked), not crash

Required real config examples:

- `HYPEREVM_RAMSES_QUOTER`, `HYPEREVM_HYBRA_QUOTER`, pool/token/fee fields
- `BASE_UNISWAP_QUOTER`, `BASE_PANCAKE_QUOTER`, pool/token/fee fields

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
- `GET /api/routes`
- `GET /api/route-health`
- `GET /api/readiness/summary`
- `GET /api/readiness/routes`
- `GET /api/readiness/routes/{route_id}`
- `GET /api/commissioning/summary`
- `GET /api/commissioning/routes`
- `GET /api/commissioning/routes/{route_id}`
- `GET /api/commissioning/ranking`
- `GET /api/commissioning/daily-summary`
- `GET /api/blocked-reason-summary`
- `GET /api/cooldowns`
- `GET /api/market-snapshots`
- `GET /api/route-health-snapshots`
- `POST /api/backtest/run`
- `GET /api/backtest/runs`
- `GET /api/backtest/results`
- `GET /api/backtest/results/{run_id}`
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

## Backtest CLI

```bash
python -m app.main backtest \
  --strategy hyperevm_dex_dex \
  --route-id <route_id> \
  --pair USDC/USDt0 \
  --start-ts 2026-03-29T00:00:00+00:00 \
  --end-ts 2026-03-30T00:00:00+00:00 \
  --replay-mode market_snapshots
```

Replay modes:

- `opportunities` (default, strict): unknown `support_status` stays blocked (`health_unknown`)
- `opportunities_legacy` (opt-in only): legacy compatibility fallback for old datasets
- `market_snapshots`: snapshot-driven replay

## Commissioning CLI

Route detail report:

```bash
python -m app.main commissioning-report
python -m app.main commissioning-report --route-id <route_id>
python -m app.main commissioning-report --format json
python -m app.main commissioning-report --format markdown
```

Daily summary report:

```bash
python -m app.main daily-commissioning-summary
python -m app.main daily-commissioning-summary --format json
python -m app.main daily-commissioning-summary --format markdown
python -m app.main daily-commissioning-summary --send-discord
```

`--send-discord` sends only on explicit command invocation. No per-scan auto-notify is enabled.

## Canonical Status Vocabulary

- Support status (`support_status`) canonical values:
  - `supported` / `unsupported` / `unknown`
- Fee confidence (`fee_known_status`) canonical values:
  - `unknown` / `fallback_only` / `config_only` / `venue_declared` / `acct_verified` / `chain_verified`
- Balance confidence (`balance_match_status`) canonical values:
  - `unknown` / `mismatch` / `internal_ok` / `db_inventory_ok` / `wallet_verified` / `venue_verified`
- Quote match status (`quote_match_status`) canonical values:
  - `unknown` / `mismatch` / `matched`

- Legacy values (`good/bad/true/false/1/0/yes/no`) are normalized to canonical values at read/write paths.
- Unknown or unverified confidence is blocked for tradability and surfaced in readiness blockers.
- `green` readiness grade is still not permission to enable live submit; human review remains mandatory.

## Readiness Policy (Strategy-Aware)

- `readiness_summary.latest_backtest_mode` is sourced from the latest stored backtest result/run metadata, independent of observation timestamps.
- `hyperevm_dex_dex` (live-intent readiness):
  - strict fee/balance requirements (`venue_declared`+, `wallet_verified`+)
  - `quote_match_status=matched` required
  - fatal pause or missing backtest keeps route `red`
- `base_virtual_shadow` (observation readiness):
  - support must still be `supported`
  - fee/balance thresholds are observation-aware (`fallback_only`+, `internal_ok`+)
  - route is intentionally treated as observation-only (typically `yellow`, not auto-promoted to live-intent `green`)

## Commissioning Promotion Gates

Commissioning gates are route-type specific and fail-safe. Any critical fail blocks promotion.

- Promotion statuses:
  - `not_ready`
  - `observation_ready` (shadow observation route only)
  - `review_ready` (live-intent review stage)
  - `promotion_blocked` (one or more critical gate fails)
- Phase states:
  - `phase_0_mock_sanity`
  - `phase_1_real_observation`
  - `phase_2_replay_review`
  - `phase_3_commissioning_review`

HyperEVM live-intent (`hyperevm_dex_dex`) minimum gates:

- observation window >= 14 days
- market snapshots >= 5,000
- opportunities >= 300
- market-snapshot replay runs >= 3
- opportunities replay runs >= 3
- quote unavailable rate <= 5%
- fatal pause unresolved = false
- readiness grade != red

Base shadow (`base_virtual_shadow`) minimum gates:

- observation window >= 7 days
- market snapshots >= 3,000
- opportunities >= 200
- total backtest runs >= 2
- quote unavailable rate <= 10%
- fatal pause unresolved = false
- readiness grade != red

Important:

- Shadow `observation_ready` is not live promotion approval.
- `review_ready` or readiness `green` never enables live submit automatically.
- Human sign-off is mandatory and `LIVE_EXECUTION_ENABLED` remains `false` by default.

Ranking score intent:

- prioritize gate attainment and operational stability over raw profitability
- add points for promotion/readiness progress and minimum evidence coverage
- subtract points for fail/warn density, quote-unavailable burden, fatal/cooldown instability
- live-intent routes get a moderate visibility bonus without hard-locking shadow routes to bottom

## Environment Variables

See [.env.example](.env.example) for the full list.

High-impact variables:

- `MODE`
- `DATABASE_URL`
- `AUTO_CREATE_SCHEMA`
- `USE_MOCK_MARKET_DATA`
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
- `HEALTH_SNAPSHOT_STALE_SECONDS`
- `LIVE_MIN_FEE_CONFIDENCE_STATUS`
- `LIVE_MIN_BALANCE_CONFIDENCE_STATUS`
- `LIVE_MIN_QUOTE_MATCH_STATUS`
- `SHADOW_MIN_FEE_CONFIDENCE_FOR_READINESS`
- `SHADOW_MIN_BALANCE_CONFIDENCE_FOR_READINESS`
- `SHADOW_MIN_QUOTE_MATCH_FOR_READINESS`
- `BALANCE_VERIFY_TOLERANCE_ABS`
- `BALANCE_VERIFY_TOLERANCE_RATIO`
- `HYPEREVM_WALLET_ADDRESS`
- `HYPEREVM_RAMSES_QUOTER_FEE_TIER` / `HYPEREVM_RAMSES_POOL_FEE_TIER` / `HYPEREVM_RAMSES_ECONOMIC_FEE_BPS`
- `HYPEREVM_HYBRA_QUOTER_FEE_TIER` / `HYPEREVM_HYBRA_POOL_FEE_TIER` / `HYPEREVM_HYBRA_ECONOMIC_FEE_BPS`
- `COMMISSIONING_LIVE_MIN_OBSERVATION_DAYS`
- `COMMISSIONING_LIVE_MIN_MARKET_SNAPSHOTS`
- `COMMISSIONING_LIVE_MIN_OPPORTUNITIES`
- `COMMISSIONING_LIVE_MIN_BACKTEST_RUNS_MARKET_SNAPSHOTS`
- `COMMISSIONING_LIVE_MIN_BACKTEST_RUNS_OPPORTUNITIES`
- `COMMISSIONING_LIVE_MAX_QUOTE_UNAVAILABLE_RATE`
- `COMMISSIONING_SHADOW_MIN_OBSERVATION_DAYS`
- `COMMISSIONING_SHADOW_MIN_MARKET_SNAPSHOTS`
- `COMMISSIONING_SHADOW_MIN_OPPORTUNITIES`
- `COMMISSIONING_SHADOW_MIN_BACKTEST_RUNS_TOTAL`
- `COMMISSIONING_SHADOW_MAX_QUOTE_UNAVAILABLE_RATE`
- `COMMISSIONING_WARN_HEALTH_UNKNOWN_RATE` / `COMMISSIONING_FAIL_HEALTH_UNKNOWN_RATE`
- `COMMISSIONING_WARN_FEE_UNVERIFIED_RATE` / `COMMISSIONING_FAIL_FEE_UNVERIFIED_RATE`
- `COMMISSIONING_WARN_BALANCE_UNVERIFIED_RATE` / `COMMISSIONING_FAIL_BALANCE_UNVERIFIED_RATE`
- `COMMISSIONING_WARN_QUOTE_MISMATCH_RATE` / `COMMISSIONING_FAIL_QUOTE_MISMATCH_RATE`

## Major Risks

- On-chain router behavior mismatch with encoded calldata
- Chain/RPC instability causing stale or bad quotes
- Fee model mismatch across venues/accounts
- Unexpected stablecoin depeg behavior
- Operational mistakes in mode switching
- Misconfigured quoter/pool/token mapping can force `quote_unavailable` and halt tradability

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

## Unsupported / Not Ready Venues (Default Config)

With default `.env.example` real-market setup, the following are intentionally not tradable until quoter/pool config is provided:

- HyperEVM: `ramses_v3`, `hybra_v3`, `hybra_v4_observer`
- Base: `uniswap_v3_base`, `pancakeswap_v3_base`, `aerodrome_base`

Behavior is fail-safe:

- route quote becomes unavailable
- opportunity is persisted with `blocked_reason=quote_unavailable`
- no live submission is attempted

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
- `app/backtest` event-driven replay/backtest engine
- `app/api` REST API
- `contracts/` Solidity contract sources
- `tests/` unit/integration/contract tests

## Future Extensions

- Real live submit path wiring remains intentionally disabled (`LIVE_EXECUTION_ENABLED=false`)
- Signed transaction submission path (currently dry-run by default)
- Fine-grained auth/RBAC for control API
- Strategy-specific dynamic notional control
- Expanded telemetry and SLO-based guard automation

## Additional Docs

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [RISK_GUARDS.md](RISK_GUARDS.md)
- [RUNBOOK.md](RUNBOOK.md)
- [TESTING.md](TESTING.md)
- [COMMISSIONING_PLAN.md](COMMISSIONING_PLAN.md)
- [BACKTESTING.md](BACKTESTING.md)
- [LIVE_READINESS_CHECKLIST.md](LIVE_READINESS_CHECKLIST.md)
- [PROMOTION_GATES.md](PROMOTION_GATES.md)
