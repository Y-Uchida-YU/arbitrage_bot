# LIVE READINESS CHECKLIST

Use this checklist before any decision to enable real submit path.

## Safety-Critical Engineering

- [ ] Fee-unit responsibility separation is complete (`economic_fee_bps` vs `quoter/pool fee tier`).
- [ ] `fee_known_status` uses explicit provenance levels (not a bool-only approximation).
- [ ] `balance_match_status` uses explicit confidence levels (not a bool-only approximation).
- [ ] `support_status` and `quote_match_status` are canonicalized (`supported/unsupported/unknown`, `matched/mismatch/unknown`).
- [ ] Live defaults remain conservative (`MODE=paper`, `LIVE_EXECUTION_ENABLED=false`).
- [ ] Unsupported routes/venues are blocked (`quote_unavailable`) and never forced tradable.
- [ ] Allowlist/route validation guards remain strict.

## Health Truthfulness

- [ ] Critical health fields are observation-based, not fixed true.
- [ ] Unknown health states are fail-safe blocked.
- [ ] Stale health snapshots trigger blocking.
- [ ] `quote_unavailable` venues are visible and tracked.
- [ ] Fee confidence below live threshold blocks (`fee_unverified`).
- [ ] Balance confidence below live threshold blocks (`balance_unverified`).
- [ ] Quote match status below live threshold blocks (`quote_mismatch`).

## Runtime State Persistence

- [ ] Route cooldown/fatal pause state is persisted in DB.
- [ ] Restart hydrates route runtime state correctly.
- [ ] Manual clear/release operations are audit-logged.

## Observability and Explainability

- [ ] Market observations are persisted (`market_snapshots`).
- [ ] Route health observations are persisted (`route_health_snapshots`).
- [ ] Blocked reason summary is explainable for recent N days.
- [ ] Dashboard/API expose cooldown and fatal-paused routes.
- [ ] `readiness_summary.latest_backtest_mode` is derived from latest backtest run/result (not latest observation route).

## Replay / Backtest Evidence

- [ ] Backtest runs/results/trades are persisted.
- [ ] Parameter set rationale is documented.
- [ ] Replay/backtest covers enough historical windows.
- [ ] Both replay modes are reviewed (`opportunities`, `market_snapshots`).
- [ ] Drawdown/worst-sequence metrics are reviewed.

## Promotion Gate Evidence

- [ ] Route-level commissioning endpoints are populated:
  - `/api/commissioning/summary`
  - `/api/commissioning/routes`
  - `/api/commissioning/routes/{route_id}`
- [ ] Route type thresholds are met:
  - live-intent (`hyperevm_dex_dex`)
  - shadow observation (`base_virtual_shadow`)
- [ ] KPI evaluations (`pass/warn/fail`) are explainable for every non-ready route.
- [ ] `promotion_gate_status` is not `promotion_blocked` for promotion candidates.
- [ ] Shadow route `observation_ready` is treated as observation-only, not live approval.

## Final Gate

- [ ] Dry-run remains stable with no unexplained fatal pauses.
- [ ] Human review sign-off is completed.
- [ ] Even with readiness `green` or gate `review_ready`, live submit remains disabled until explicit approval.
- [ ] Real submit path is still disabled by default and requires explicit manual change.
