# BACKTESTING

Backtesting is event-driven replay over persisted observations.

## Purpose

- Validate threshold and risk-check behavior before any production submit path.
- Measure blocked reason quality, signal quality, and conservative simulated PnL.
- Support route-level go/no-go decisions for commissioning continuation.

## Data Sources

- `opportunities` (derived replay stream)
- `market_snapshots` (observation audit)
- `route_health_snapshots` (health context)
- `parameter_sets` (backtest parameterization)

## Replay Modes

- `opportunities`
  - Re-evaluates persisted opportunity rows.
  - Fast sanity/repro mode for threshold changes.
- `market_snapshots`
  - Reconstructs route events from raw-ish observation rows (`leg_b` snapshots + latest route health state).
  - Better for commissioning truthfulness checks and readiness scoring.

## Conservative Fill Model

Replay uses conservative assumptions and does not model optimistic fills.

Included penalties/guards:

- slippage constraints
- quote-age reject
- quote drift buffer
- gas penalty
- latency penalty
- liquidity cap / pool share cap
- quote unavailable / fee unknown / quote mismatch blocking
- fallback-fee penalty
- unverified fee penalty
- unverified balance penalty

## Running Backtest (CLI)

```bash
python -m app.main backtest \
  --strategy hyperevm_dex_dex \
  --route-id <route_id> \
  --pair USDC/USDt0 \
  --start-ts 2026-03-29T00:00:00+00:00 \
  --end-ts 2026-03-30T00:00:00+00:00 \
  --parameter-set-id <optional_parameter_set_id> \
  --replay-mode market_snapshots
```

## Running Backtest (API)

- `POST /api/backtest/run`
- `GET /api/backtest/runs`
- `GET /api/backtest/results`
- `GET /api/backtest/results/{run_id}`

Request example:

```json
{
  "token": "<CONTROL_API_TOKEN>",
  "strategy": "hyperevm_dex_dex",
  "route_id": "<route_id>",
  "pair": "USDC/USDt0",
  "start_ts": "2026-03-29T00:00:00+00:00",
  "end_ts": "2026-03-30T00:00:00+00:00",
  "parameter_set_id": null,
  "notes": "commissioning replay",
  "replay_mode": "market_snapshots"
}
```

## Stored Results

- run metadata: `backtest_runs`
- aggregate metrics: `backtest_results`
- per-signal/per-trade replay rows: `backtest_trades`

Key outputs include:

- signals / eligible / blocked
- blocked reason breakdown
- simulated pnl
- hit rate
- avg modeled edge
- avg realized-like pnl
- max drawdown
- worst losing sequence
- missed opportunities
- stale/unknown health event count
- fee confidence distribution
- balance confidence distribution
- penalty totals

## Interpretation Guidelines

- Prefer stability and explainability over peak simulated PnL.
- High `quote_unavailable` or `health_unknown` rates indicate readiness gaps.
- `fallback_only`/`config_only` fee dominance is a readiness blocker.
- `internal_ok` only (without wallet/venue verification) is not sufficient for live readiness.
- If blocked reasons are not explainable, do not advance commissioning stage.
- Keep real submit disabled until checklist completion.
