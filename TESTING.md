# Testing

## Test Layers

## Unit

- modeled edge calculation
- stale/slippage/depeg/gas guards
- symbol normalization
- config defaults and allowlist parsing
- kill switch behavior
- route adapter selection

## Integration

- app bootstrap with DB writes
- dashboard rendering
- overview/opportunities/executions API
- control API actions
- live mode switch + dry-run flow

## Contract

- `ArbExecutor` happy path
- minProfit unmet revert
- unauthorized caller revert
- non-allowlisted router revert
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