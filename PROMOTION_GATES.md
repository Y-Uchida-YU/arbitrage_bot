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
- `GET /api/commissioning/ranking`
- `GET /api/commissioning/daily-summary`

## Required CLI

- `python -m app.main commissioning-report`
- `python -m app.main commissioning-report --route-id <route_id>`
- `python -m app.main commissioning-report --format json|markdown`
- `python -m app.main daily-commissioning-summary`
- `python -m app.main daily-commissioning-summary --format json|markdown`
- `python -m app.main daily-commissioning-summary --send-discord`

`--send-discord` is explicit-only. There is no automatic per-scan broadcast.

## Ranking Score Intent

Ranking score is explainable and gate-oriented, not profit-maximizing.

Score adds:

- gate progress (`review_ready`, `observation_ready`)
- readiness quality (`yellow`, `green`)
- evidence coverage (observation/snapshot/opportunity/backtest completion)
- moderate visibility bonus for live-intent routes

Score subtracts:

- KPI fail count and warn count
- high quote-unavailable burden
- instability signals reflected in blockers and cooldown/fatal metrics

## Interpretation

- `promotion_blocked` means do not proceed; resolve blockers first.
- `observation_ready` means shadow observation quality is acceptable, not live approval.
- `review_ready` means route can be considered in a human review packet.
- best candidate routes are ranking outputs for human review triage, not auto-promotion.
- worst quote-unavailable routes are remediation priorities for support/health/adapter work.
- Even after `review_ready`, live submit remains disabled unless explicitly approved.
