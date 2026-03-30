# Risk Guards

## Priority

`Risk control > fill rate > profitability`

## Core Guards

- Global kill switch
- Strategy pause
- Route pause
- Pair pause
- Stale quote guard
- RPC reachability and error-rate guard
- DB reachability guard
- Alert subsystem failure guard
- Gas spike guard
- Liquidity deterioration guard
- Depeg guard
- Notional absolute and pool-share cap
- Balance sufficiency guard
- Route frequency limit
- Consecutive failure limit
- Consecutive loss limit
- Cooldown after failure
- Fatal failure categories (quote mismatch/revert/chain mismatch/router violation/stale critical data/quote unavailable)

## Live Threshold Defaults

- `LIVE_MIN_NET_EDGE_BPS=30`
- `LIVE_MIN_EDGE_PERSIST_SECONDS=8`
- `LIVE_MAX_SLIPPAGE_BPS=2`
- `LIVE_MIN_PROFIT_ABSOLUTE_USDC=0.50`
- `LIVE_MAX_NOTIONAL_USDC=100`
- `LIVE_MAX_NOTIONAL_PCT_OF_SMALLER_POOL=0.0002`
- `LIVE_MAX_TRADES_PER_ROUTE_PER_10M=3`
- `LIVE_MAX_CONSECUTIVE_FAILURES_PER_ROUTE=1`
- `LIVE_MAX_CONSECUTIVE_LOSSES_PER_ROUTE=2`
- `ROUTE_FAILURE_COOLDOWN_SECONDS=300`
- `ROUTE_FATAL_FAILURE_COOLDOWN_SECONDS=900`
- `GLOBAL_DAILY_DD_STOP_PCT=0.005`
- `GLOBAL_STALE_QUOTE_STOP_SECONDS=3`

## Depeg / Abnormal Stops

- `DEPEG_THRESHOLD_BPS=50`
- `RPC_ERROR_RATE_STOP_PCT_5M=0.05`
- `GAS_SPIKE_MULTIPLIER=1.5`
- `LIQUIDITY_DROP_STOP_PCT=0.30`

## Fail-Safe Behavior

If required data is stale/unknown or subsystems become unreliable, new entries are blocked and logged with explicit `blocked_reason`.

Strict semantics:

- when `LIVE_MAX_CONSECUTIVE_FAILURES_PER_ROUTE=1`, one failure blocks the next attempt
- fatal category can pause route immediately pending manual investigation
- route cooldown/pause/failure counters are persisted in DB and restored on restart
- unknown health states are blocked (`health_unknown`) rather than assumed healthy
