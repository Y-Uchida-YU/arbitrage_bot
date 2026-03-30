# COMMISSIONING PLAN

This repository is commissioning-oriented and keeps real live submit disabled by default.

- Default mode: `MODE=paper`
- Live submit gate: `LIVE_EXECUTION_ENABLED=false`
- Any unknown/unsupported route remains blocked and non-tradable.

## Step 1: Basic Mock Validation

- Start with `USE_MOCK_MARKET_DATA=true`.
- Verify API, dashboard, risk checks, and opportunity persistence.
- Confirm control APIs and kill switches work.

## Step 2: Real Data Observation Only

- Set `USE_MOCK_MARKET_DATA=false`.
- Keep mode in paper and live submit disabled.
- Confirm CEX and supported DEX adapters return real observations.

## Step 3: Resolve quote_unavailable / blocked reasons

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

- Review `LIVE_READINESS_CHECKLIST.md` item-by-item.
- Confirm explainability of blocked reasons over recent days.
- Confirm health unknown/stale behavior is fail-safe.

## Step 9: Explicit Review Before Any Live Submit

- Even after readiness review, keep `LIVE_EXECUTION_ENABLED=false` until an explicit human review is completed.
- No automatic live-submit enablement is permitted.
