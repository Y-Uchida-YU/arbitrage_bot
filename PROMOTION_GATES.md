# PROMOTION GATES

This document defines commissioning promotion gate logic.

## Safety Invariants

- `MODE=paper` default remains unchanged.
- `LIVE_EXECUTION_ENABLED=false` default remains unchanged.
- Promotion gate status never enables live submit by itself.
- Unsupported/unknown routes remain blocked and non-tradable.

## Route Types

- Live-intent route: `hyperevm_dex_dex`
- Shadow observation route: `base_virtual_shadow`

## Promotion Gate Status

- `not_ready`: no critical fail, but minimum gate still not satisfied.
- `observation_ready`: shadow route passed observation minimum gates.
- `review_ready`: live-intent route passed minimum gates and is ready for human review.
- `promotion_blocked`: at least one critical gate failed.

## KPI Set

Per route commissioning metrics:

- `observation_window_days`
- `market_snapshot_count`
- `opportunity_count`
- `backtest_run_count_total`
- `backtest_run_count_market_snapshots`
- `backtest_run_count_opportunities`
- `quote_unavailable_rate`
- `health_unknown_rate`
- `fee_unverified_rate`
- `balance_unverified_rate`
- `quote_mismatch_rate`
- `fatal_pause_count`
- `cooldown_event_count`
- `blocked_reason_top_n`
- `latest_backtest_pnl`
- `median_backtest_pnl`
- `worst_backtest_drawdown`
- `latest_readiness_grade`

Each KPI is evaluated as `pass`, `warn`, or `fail`.

## Thresholds

### Live-intent (`hyperevm_dex_dex`)

- observation window: `>= COMMISSIONING_LIVE_MIN_OBSERVATION_DAYS` (default 14)
- snapshots: `>= COMMISSIONING_LIVE_MIN_MARKET_SNAPSHOTS` (default 5000)
- opportunities: `>= COMMISSIONING_LIVE_MIN_OPPORTUNITIES` (default 300)
- market snapshot backtests: `>= COMMISSIONING_LIVE_MIN_BACKTEST_RUNS_MARKET_SNAPSHOTS` (default 3)
- opportunities backtests: `>= COMMISSIONING_LIVE_MIN_BACKTEST_RUNS_OPPORTUNITIES` (default 3)
- quote unavailable rate: `<= COMMISSIONING_LIVE_MAX_QUOTE_UNAVAILABLE_RATE` (default 0.05)

### Shadow (`base_virtual_shadow`)

- observation window: `>= COMMISSIONING_SHADOW_MIN_OBSERVATION_DAYS` (default 7)
- snapshots: `>= COMMISSIONING_SHADOW_MIN_MARKET_SNAPSHOTS` (default 3000)
- opportunities: `>= COMMISSIONING_SHADOW_MIN_OPPORTUNITIES` (default 200)
- backtests total: `>= COMMISSIONING_SHADOW_MIN_BACKTEST_RUNS_TOTAL` (default 2)
- quote unavailable rate: `<= COMMISSIONING_SHADOW_MAX_QUOTE_UNAVAILABLE_RATE` (default 0.10)

### Shared quality-rate warn/fail thresholds

- health unknown rate:
  - warn above `COMMISSIONING_WARN_HEALTH_UNKNOWN_RATE`
  - fail above `COMMISSIONING_FAIL_HEALTH_UNKNOWN_RATE`
- fee unverified rate:
  - warn above `COMMISSIONING_WARN_FEE_UNVERIFIED_RATE`
  - fail above `COMMISSIONING_FAIL_FEE_UNVERIFIED_RATE`
- balance unverified rate:
  - warn above `COMMISSIONING_WARN_BALANCE_UNVERIFIED_RATE`
  - fail above `COMMISSIONING_FAIL_BALANCE_UNVERIFIED_RATE`
- quote mismatch rate:
  - warn above `COMMISSIONING_WARN_QUOTE_MISMATCH_RATE`
  - fail above `COMMISSIONING_FAIL_QUOTE_MISMATCH_RATE`

## Required APIs

- `GET /api/commissioning/summary`
- `GET /api/commissioning/routes`
- `GET /api/commissioning/routes/{route_id}`

## Interpretation

- `promotion_blocked` means do not proceed; resolve blockers first.
- `observation_ready` means shadow observation quality is acceptable, not live approval.
- `review_ready` means route can be considered in a human review packet.
- Even after `review_ready`, live submit remains disabled unless explicitly approved.
