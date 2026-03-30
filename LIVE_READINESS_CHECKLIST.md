# LIVE READINESS CHECKLIST

Use this checklist before any decision to enable real submit path.

## Safety-Critical Engineering

- [ ] Fee-unit responsibility separation is complete (`economic_fee_bps` vs `quoter/pool fee tier`).
- [ ] `fee_known_status` uses explicit provenance levels (not a bool-only approximation).
- [ ] `balance_match_status` uses explicit confidence levels (not a bool-only approximation).
- [ ] Live defaults remain conservative (`MODE=paper`, `LIVE_EXECUTION_ENABLED=false`).
- [ ] Unsupported routes/venues are blocked (`quote_unavailable`) and never forced tradable.
- [ ] Allowlist/route validation guards remain strict.

## Health Truthfulness

- [ ] Critical health fields are observation-based, not fixed true.
- [ ] Unknown health states are fail-safe blocked.
- [ ] Stale health snapshots trigger blocking.
- [ ] quote_unavailable venues are visible and tracked.
- [ ] Fee confidence below live threshold blocks (`fee_unverified`).
- [ ] Balance confidence below live threshold blocks (`balance_unverified`).

## Runtime State Persistence

- [ ] Route cooldown/fatal pause state is persisted in DB.
- [ ] Restart hydrates route runtime state correctly.
- [ ] Manual clear/release operations are audit-logged.

## Observability and Explainability

- [ ] Market observations are persisted (`market_snapshots`).
- [ ] Route health observations are persisted (`route_health_snapshots`).
- [ ] Blocked reason summary is explainable for recent N days.
- [ ] Dashboard/API expose cooldown and fatal-paused routes.

## Replay / Backtest Evidence

- [ ] Backtest runs/results/trades are persisted.
- [ ] Parameter set rationale is documented.
- [ ] Replay/backtest covers enough historical windows.
- [ ] Both replay modes are reviewed (`opportunities` and `market_snapshots`).
- [ ] Drawdown/worst-sequence metrics are reviewed.

## Route/Venue Readiness

- [ ] Route-by-route supported/unsupported status is documented.
- [ ] Fee-known / quote-match / balance-match status is visible per route.
- [ ] Depeg, gas spike, RPC failure, liquidity deterioration guards are validated.
- [ ] Readiness API and dashboard blockers are explainable for each non-green route.

## Final Gate

- [ ] Dry-run remains stable with no unexplained fatal pauses.
- [ ] Human review sign-off is completed.
- [ ] Even with `green`, live submit remains disabled until explicit human approval.
- [ ] Real submit path is still disabled by default and requires explicit approval to change.
