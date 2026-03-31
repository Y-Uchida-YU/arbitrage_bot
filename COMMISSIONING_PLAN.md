# COMMISSIONING PLAN

This repository is commissioning-oriented and keeps real live submit disabled by default.

- Default mode: `MODE=paper`
- Live submit gate: `LIVE_EXECUTION_ENABLED=false`
- Any unknown/unsupported route remains blocked and non-tradable.

## Phase Model

Route-level phase is tracked by API/dashboard as one of:

- `phase_0_mock_sanity`
- `phase_1_real_observation`
- `phase_2_replay_review`
- `phase_3_commissioning_review`

Promotion gate status is tracked separately:

- `not_ready`
- `observation_ready` (shadow route only)
- `review_ready` (live-intent review stage)
- `promotion_blocked`

## Route-Type Minimum Gates

### HyperEVM Live-Intent (`hyperevm_dex_dex`)

- Observation window: `>= 14` days
- Market snapshots: `>= 5000`
- Opportunities: `>= 300`
- Market-snapshots replay runs: `>= 3`
- Opportunities replay runs: `>= 3`
- Quote unavailable rate: `<= 0.05`
- Fatal pause unresolved: must be false
- Latest readiness grade: must not be `red`

### Base Shadow (`base_virtual_shadow`)

- Observation window: `>= 7` days
- Market snapshots: `>= 3000`
- Opportunities: `>= 200`
- Total replay/backtest runs: `>= 2`
- Quote unavailable rate: `<= 0.10`
- Fatal pause unresolved: must be false
- Latest readiness grade: must not be `red`

Shadow route gates are observation-readiness only and are not live-promotion approval.

## KPI Set Used For Gate Evaluation

Per route, commissioning API tracks at least:

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

## Step 1: Basic Mock Validation

- Start with `USE_MOCK_MARKET_DATA=true`.
- Verify API, dashboard, risk checks, and opportunity persistence.
- Confirm control APIs and kill switches work.

## Step 2: Real Data Observation Only

- Set `USE_MOCK_MARKET_DATA=false`.
- Keep mode in paper and live submit disabled.
- Confirm CEX and supported DEX adapters return real observations.

## Step 3: Resolve `quote_unavailable` / blocked reasons

- Review blocked reasons (`/api/blocked-reason-summary`, dashboard table).
- For each unsupported route, either configure safely or keep blocked.
- Never bypass support checks to force tradability.

## Step 4: Accumulate Observation History (days to weeks)

- Keep recording market snapshots and route-health snapshots.
- Monitor stability for quote freshness, liquidity, gas, and RPC health.
- Persist all opportunities and blocked reasons for replay.

## Step 5: Replay / Backtest

- Run replay/backtest over recorded windows by route and pair.
- Store backtest runs/results/trades for auditability.
- Compare blocked reason breakdown against expected behavior.

## Step 6: Threshold Re-evaluation

- Reassess net-edge threshold, slippage caps, quote-age limits, and liquidity caps.
- Keep assumptions conservative; do not optimize for aggressive fills.

## Step 7: Dry-Run Stabilization

- Continue dry-run (`mode=live` allowed only with multi-guard arming) without real submit.
- Ensure failure/cooldown persistence survives restarts.
- Verify fatal categories trigger pause/cooldown as expected.

## Step 8: Live Readiness Review

- Review `LIVE_READINESS_CHECKLIST.md` and `PROMOTION_GATES.md` item-by-item.
- Confirm explainability of blocked reasons over recent days.
- Confirm unknown/stale behavior remains fail-safe.

## Step 9: Explicit Review Before Any Live Submit

- Even after readiness review, keep `LIVE_EXECUTION_ENABLED=false` until explicit human sign-off.
- No automatic live-submit enablement is permitted.

## Daily / Weekly Operations

Daily routine:

- Run `python -m app.main daily-commissioning-summary --format markdown`.
- Check `review_ready`, `observation_ready`, and `promotion_blocked` counts.
- Review top blockers and worst quote-unavailable routes.
- Review best candidate routes and their action items.

Route detail drill-down:

- Run `python -m app.main commissioning-report --route-id <route_id> --format markdown`.
- Confirm blocker reasons are concrete and actionable.

Weekly routine:

- Compare ranking movement route-by-route.
- Validate replay/backtest evidence accumulation and KPI trend direction.
- Reassess threshold assumptions conservatively and document rationale.
