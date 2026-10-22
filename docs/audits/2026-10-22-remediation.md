# Audit remediation and upgrade guide

The ten source-level findings in the [original audit](2026-10-22-readiness.md) have been addressed. The original report describes commit `1204670`; it remains historical evidence rather than a description of the updated code.

## Changes

| Finding | Implemented remediation | Regression evidence |
|---|---|---|
| IF-01: default worker credential | Production startup rejects default/short bootstrap credentials; dashboard proxy exposes only customer/auth routes | Production configuration rejection |
| IF-02: abandoned leases | Enrollment rotates worker generation; heartbeat renews only active request epochs; old generations recover; finalization retries continue with bounded backoff; poll respects remaining physical slots and attempts are tracked by ID/epoch | Same-ID restart, old credential/finalization rejection, selective renewal, five finalization attempts, slot-aware polling |
| IF-03: model identity | Worker identity persists repository, model/tokenizer revisions and execution mode; dispatch matches all fields; work carries identity; engine checks identity-derived served alias and fails a failed canary | Four identity mismatch cases, revision upgrade, wrong engine identity, failed canary |
| IF-04: reversed funding | Refund/dispute freezes and cancels outstanding work under wallet lock; epochs fence late results; debt is journaled; later credits repay debt; reconciliation checks debt/reservations/captured usage | Queued/running reversal, completed-usage liability, concurrent refund/finalization, legacy debt migration |
| IF-05: create/watchdog race | Watchdog reconciles deterministic creation names with intents; creation accepts an already reconciled ID; absent instances are marked terminated; historical terminated spend contributes to budget estimates | Watchdog during create, missing inventory, historical spend |
| IF-06: callback stalls | Separate callback process; expiring delivery claims; no database transaction held during network I/O | Blocked delivery while scheduler continues and delivery row remains lockable |
| IF-07: global wallet contention | Scheduler selects up to 64 active tenant wallets using SKIP LOCKED and rotates checked order; expensive token counting precedes wallet lock | Held wallet for tenant A does not prevent tenant B dispatch |
| IF-08: rate-limit bypass | API keys and sessions share persisted PostgreSQL fixed-window counters across replicas; database time defines windows; failed requests cannot roll back their allowance | Mixed session/key traffic shares the same 120-request allowance |
| IF-09: public metrics | Separate bearer credential required; unset token disables access; management endpoints excluded from dashboard proxy | Unauthenticated/customer-key rejection and authorized scrape |
| IF-10: rotation coupling | Independent credential-HMAC key with previous-key migration; versioned encryption key ring; explicit legacy decrypt key; maintenance re-encryption CLI | Session-key change preserves encrypted data; historical credentials authenticate and are upgraded |

Further hardening: platform image runs as a non-root user, and the Compose GPU/mock worker receives an explicit environment without database, payment, provider, signing, or encryption secrets.

## Existing deployment upgrade

1. Stop intake and stop existing API, scheduler, callback and worker processes. Back up PostgreSQL and retain the current deployment's encryption/credential secrets in a secret manager. Do not log them or commit `.env`.
2. Configure the environment fields below. For local mock development the existing `.env` continues to work; metrics remain inaccessible until a token is set. Production requires the new independent keys.
3. With the new code, apply `alembic upgrade head`. Migration `0005` adds worker identity/generation, wallet debt and debt journal deltas, scheduling fairness timestamps, shared rate counters, and callback claims. Existing reversal-debt audit records become debt journal entries. Review legacy liabilities before resuming paid traffic; pre-upgrade inconsistencies in reservations/usage must be reconciled rather than silently rewritten.
4. If migrating encrypted data, run the re-encryption maintenance command below while processes remain stopped. Validate a restored backup as well as the active database.
5. Rebuild/restart API, scheduler, callbacks and workers together. Old worker binaries are incompatible with the new active-lease protocol. Workers re-enroll with a fresh generation; old in-flight work is fenced and recovered according to retry limits. Requests that lack a model-price identity are not dispatched; review such legacy requests explicitly.
6. For vLLM, launch the model with the identity-derived served alias described in `docs/gpu-deploy.md`. Keep API/worker repository and revisions aligned. Retain old matching capacity until admitted work under the previous revision is drained, or explicitly cancel it.
7. Run `python -m packages.common.cli reconcile`, exercise a synthetic tenant/job, inspect wallet/debt/reservations, and verify scheduler and callback health before reopening intake.

Compose local deployment:

```bash
docker compose build
docker compose run --rm migrate
docker compose up -d
docker compose logs --tail=100 api scheduler callbacks worker
```

For native deployment, run `python -m apps.callbacks.main` in its own supervised process alongside the existing API, scheduler and worker. The callback process receives control-plane database and encryption access; GPU workers do not.

## Key configuration and rotation

Use independent randomly generated values, stored outside the repository:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Dashboard JWT and OIDC flow signing; rotation invalidates current browser sessions |
| `WORKER_BOOTSTRAP_TOKEN` | Protected enrollment secret, at least 32 characters outside development; do not expose through dashboard ingress |
| `METRICS_TOKEN` | Separate private scrape credential, at least 32 characters outside development |
| `CREDENTIAL_HASH_KEY` | API/worker credential HMAC key, at least 32 characters and independent of session signing |
| `CREDENTIAL_HASH_PREVIOUS_KEYS` | JSON array of old HMAC keys accepted temporarily for lazy migration |
| `ENCRYPTION_KEYS` | JSON object mapping nonempty colon-free key IDs to Fernet keys |
| `ENCRYPTION_ACTIVE_KEY` | ID used for new ciphertext; ciphertext records the version/key ID |
| `ENCRYPTION_LEGACY_SECRET` | Original application secret, retained temporarily to decrypt pre-versioned ciphertext |

Generate random secrets locally, for example using Python's `secrets.token_urlsafe(48)`. Generate encryption keys with `Fernet.generate_key()` from `cryptography.fernet`. Do not paste generated values into logs or release notes.

For legacy migration, put the old `SECRET_KEY` in `CREDENTIAL_HASH_PREVIOUS_KEYS` and `ENCRYPTION_LEGACY_SECRET`, then configure new independent signing/HMAC/encryption keys. Do not remove the old decryption material until all retained ciphertext and required backups have a documented migration/recovery path.

For a subsequent encryption rotation, add the new key to `ENCRYPTION_KEYS`, make its ID active, and retain old IDs for reads. During a maintenance window:

```bash
python -m packages.common.cli rotate-encryption
python -m packages.common.cli reconcile
```

This command re-encrypts retained request payloads, results and webhook secrets in one transaction. It is intended for a maintenance window with intake and workers stopped; large datasets require a planned maintenance duration. A missing historical key fails and rolls back rather than discarding content. Verify retrieval before removing old keys. Historical API/worker HMACs upgrade when those credentials are used; dormant keys must be reissued or revoked before dropping the previous HMAC key. Worker re-enrollment issues a new token.

## Financial and operational behavior

- A refund or dispute immediately freezes the account and cancels all outstanding work, including running and quarantined requests. Later completions are rejected without a further customer charge. Already committed usage remains recorded; reversed funding that has already been consumed becomes debt. Subsequent credits repay debt first. Unfreezing requires explicit operator review; it is not triggered by a top-up.
- Reconciliation now checks journal balances/debt, remaining request reservations, and captured usage totals. It is still not a provider invoice reconciliation system.
- The scheduler skips wallets locked by another transaction rather than blocking every tenant. Such tenants are reconsidered on subsequent ticks; fairness timestamps rotate active batches. Throughput at large tenant/queue counts still needs workload measurement.
- Callbacks remain at least once. Consumers must deduplicate `event_id`. A claim expires after two minutes if its process fails; delivery is isolated from inference scheduling even when a destination or DNS stalls.
- Rate limits are fixed UTC minute windows, with the standard possible boundary burst; they are not a rolling-window limit. Both authentication methods share the same PostgreSQL counter. Additional edge limits for unauthenticated login and worker enrollment remain advisable.
- GPU cost limits are estimates from operator quotes and observed lifetimes, including terminated sessions. They do not replace provider-side spending controls or invoice checks. Ambiguous pending creation intents require inventory reconciliation before retry.
- Version-derived engine aliases check configured deployment identity, not hardware attestation. GPU hosts, deployment image and vLLM launch configuration remain trusted.

## Validation and remaining gates

Validation: **56 tests passed; one real-GPU test skipped**. Ruff and mypy passed (29 source modules), the Next.js production build succeeded, and `docker compose config --quiet` passed. A temporary production Next.js server returned 404 for `/api/metrics` and `/api/internal/workers/register`, confirming the proxy exclusions. New regression coverage is in `tests/test_audit_fixes.py` and `tests/test_migrations.py`. The suite retains one upstream Starlette/AnyIO deprecation warning.

No paid resources were provisioned and no real payment credentials were used. Real NVIDIA/vLLM execution, provider contract behavior and invoices, Stripe test-mode financial lifecycle, external OIDC, production callback TLS/egress, least-privilege database roles, backup restoration and alert delivery still require deployment validation. The Windows Docker daemon was unavailable during remediation; Compose configuration validation passed, but the updated full container stack was not rerun here. The historical v0.1.0 Docker test result is not evidence for this updated image.

These source fixes do not by themselves establish readiness for paid production traffic.
