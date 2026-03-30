# Assumptions / TODO

## Assumptions

- Default runtime uses mock market data for deterministic local validation (`USE_MOCK_MARKET_DATA=true`).
- HyperEVM/Base RPC URLs and token/router addresses in `.env.example` are placeholders and must be replaced before production.
- Live transaction submission remains disabled by default to preserve safety-first rollout.

## TODO Before Production

- Replace mock DEX quotes with verified on-chain quoter integrations per venue.
- Wire real signer + transaction manager with nonce/replacement policies.
- Add strict auth (JWT/session/RBAC) for dashboard and control APIs.
- Add robust per-venue market status probes and quote drift detectors.
- Harden contract calldata builders for each allowlisted router ABI.
- Add CI pipelines for lint/type/test/contract checks.