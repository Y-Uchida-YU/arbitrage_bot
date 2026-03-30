# Testing

## Test Layers

## Unit

- modeled edge calculation
- stale/slippage/depeg/gas guards
- strict failure semantics and cooldown behavior
- quote_unavailable handling
- symbol normalization
- config defaults and allowlist parsing
- kill switch behavior
- route adapter selection
- health collector rolling metrics
- blocked reason summary aggregation
- fee unit separation (economic fee vs quoter/pool fee tier)
- persistent route runtime state hydration
- health unknown => blocked
- market snapshot serialization
- backtest result aggregation and parameter-set application

## Integration

- app bootstrap with DB writes
- dashboard rendering
- overview/opportunities/executions API
- control API actions
- live mode switch + dry-run flow
- `USE_MOCK_MARKET_DATA=false` startup behavior
- unsupported DEX path => blocked/quote_unavailable behavior
- schema guard behavior (`AUTO_CREATE_SCHEMA=false`)
- observation recording endpoints (`market-snapshots`, `route-health-snapshots`)
- backtest run/results endpoints and dashboard rendering
- restart path restores persisted route runtime pause/cooldown state

## Contract

- `ArbExecutor` happy path
- minProfit unmet revert
- unauthorized caller revert
- route validation mismatch revert
- selector not allowed revert
- pool/fee mismatch revert
- paused revert
- emergency withdraw

## Run Commands

```bash
pytest
```

or split by layer:

```bash
pytest tests/unit
pytest tests/integration
pytest tests/contract
```

## Notes

- Contract tests use `py-solc-x` and `eth_tester`.
- If Solidity compiler install is unavailable in the environment, contract tests may skip.
- Use mock market mode for deterministic local testing (`USE_MOCK_MARKET_DATA=true`).
