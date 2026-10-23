# Changelog

## v0.2.0 — 2026-10-23 — Hardened MVP prerelease

Audit fixes for stale workers, artifact identity, refunds/debt, provider recovery, callback transactions, scheduler locking, shared rate limits, metrics/proxy access, production secrets, and key rotation. Adds the recorded integration walkthrough, seven browser captures, SDK evidence, and the complete deployed Sites showcase source.

Validation: 56 passed / one real-GPU test skipped; lint, type checks, and dashboard build passed. Real GPU/provider, Stripe account, and OIDC validation remain pending. The hosted showcase retains owner-private access independently of GitHub visibility.

See [detailed release notes](docs/releases/v0.2.0.md).

## v0.1.0 — 2026-10-22 — MVP prerelease

Initial executable release: asynchronous inference API, durable PostgreSQL queue/scheduler, mock/vLLM workers, tenant identity/keys, prepaid accounting, Stripe test integration, signed callbacks, dashboard, SDK, provider guardrails, Compose, monitoring and runbooks.

Validation: 32 passed / 1 GPU test skipped in native and Python 3.12 Docker suites. Both 100-request HTTP smoke tests completed with zero ledger drift. Lint/type checks and dashboard build passed. External GPU/payment/provider/OIDC integration and beta review remain pending.

See [detailed release notes](docs/releases/v0.1.0.md).
