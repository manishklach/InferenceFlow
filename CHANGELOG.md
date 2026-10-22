# Changelog

## v0.1.0 — 2026-10-22 — MVP prerelease

Initial executable release: asynchronous inference API, durable PostgreSQL queue/scheduler, mock/vLLM workers, tenant identity/keys, prepaid accounting, Stripe test integration, signed callbacks, dashboard, SDK, provider guardrails, Compose, monitoring and runbooks.

Validation: 32 passed / 1 GPU test skipped in native and Python 3.12 Docker suites. Both 100-request HTTP smoke tests completed with zero ledger drift. Lint/type checks and dashboard build passed. External GPU/payment/provider/OIDC integration and beta review remain pending.

See [detailed release notes](docs/releases/v0.1.0.md).
