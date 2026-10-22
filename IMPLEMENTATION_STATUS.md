# Implementation status

This is a working local inference execution MVP with real integration code. It is not a live GPU service or a public beta deployment. No billable GPU was created and no real payment credentials were used.

## Implemented
- FastAPI public API, OpenAPI export, request IDs, standard error envelopes and limits.
- Managed OIDC authorization code + PKCE/state/nonce/JWKS verification; development-only local sign-in; secure cookie/CSRF sessions; users, owner memberships, one-time API keys, HMAC hashes and revocation.
- PostgreSQL durable per-request queue, separate scheduler, warm-model affinity, weighted tenant fairness/aging, best-effort deadlines, worker/tenant concurrency caps, lease renewal, retry backoff and fencing.
- Atomic batch admission, canonical idempotency, encrypted prompts/results, ordered partial results, pagination/JSONL, queued cancellation and best-effort running cancellation.
- Integer micro-USD prepaid accounting, locked reserves, immutable ledger trigger, immutable rate snapshots, unique usage, capture/release, usage-mismatch quarantine and audited operator reconciliation/release.
- Separate outbound async worker, deterministic mock engine, real private vLLM HTTP adapter, readiness canary, exact pinned Qwen chat-template tokenizer, explicit no-thinking generation, revision checks and worker credential renewal/rotation on re-registration.
- Stripe test Checkout and raw-body signature webhook, paid-session/PaymentIntent dedupe, cumulative refunds/dispute freeze and debt audit. Public payments remain gated.
- Registered signed customer webhooks, public-IP validation, pinned connect IP/TLS SNI, redirect rejection, durable 24-hour retries and delivery audit.
- Modular Fake, manual attach and current Runpod REST v2 adapters; default provisioning kill switch, durable ambiguous-create intents, one-GPU admission cap, quoted daily/session cost ceiling, independent orphan/idle/session watchdog.
- Next.js/TypeScript dashboard: sign-in, credits/reservations, key creation/revocation, sample submission, polling, results/JSONL, token usage, charges, ledger and test top-up.
- Python SDK, Docker Compose, pinned Python dependency list, CI, Prometheus gauges/alerts, health/readiness, redacted logs, 7-day content purge and deployment/security/billing runbooks.

## Evidence executed locally
- Docker Compose images built; PostgreSQL/API/scheduler/worker/dashboard booted. Container HTTP smoke completed 100 requests with the same usage/charge and zero ledger drift. The Python 3.12 container suite also passed **32 tests**, with only the real-GPU test skipped.
- PostgreSQL 16 installed and running in WSL; tests use a separate `_test` database. No SQLite substitutions.
- Latest native suite: **32 passed, 1 skipped** (GPU opt-in).
- Test suite covers 100-request ordering, 100 concurrent submissions, overspend contention, concurrent exactly-once finalization, stale epochs, crash-before-commit recovery, retries, cancellation, deadlines (including leased work), isolation, payments, OIDC, SSRF/rebinding/redirects, webhook retries, redaction, retention and migration rollback/rebuild.
- Ruff and mypy pass. Dashboard production build and TypeScript checks pass; npm production audit reports zero vulnerabilities.
- Native multi-process HTTP smoke: API -> queue -> separate scheduler -> separate mock worker -> results -> meter -> wallet. 100 succeeded; input tokens 3,690; output tokens 6,900; charge 2,500 micro-USD at synthetic test rates; zero ledger drift. Artifact: `.runtime/smoke-result.json`.
- Browser sign-in, sample submission and observed succeeded status/charge verified against live local API. Screenshot: `.runtime/dashboard.png`.
- Real Qwen tokenizer downloaded without model weights at SHA `1cfa9a7208912126459214e8b04321603b3df60c`; the checked sample counts 18 prompt tokens. Run `python scripts/check_tokenizer.py`. Model/image source pins are in `infra/model-lock.json`; GPU validation is explicitly false.

## External validation still required
- Approved rented NVIDIA GPU and the opt-in GPU smoke/restart/load test. No throughput, GPU fit, latency, margin or savings claim is established.
- External managed OIDC tenant credentials/redirect settings and actual provider sign-in. Local tests validate code exchange with mocked provider HTTP and real RSA signatures.
- Stripe test account/CLI delivery and real Checkout browser loop. Automated tests validate signed events, dedupe and reversals without contacting Stripe.
- Runpod account credentials, current confirmed availability/price and an explicitly approved paid smoke test. Contract tests mock official v2 HTTP shapes; they do not prove live provisioning.
- Real HTTPS customer-webhook TLS/egress validation, production TLS/reverse proxy, encrypted infrastructure/backups, restore drill and provider-side budget alerts.
- 48-hour measured rate selection, model/license review, prepaid/refund/tax/legal review and limited-beta security review.

## Explicit engineering boundaries
Single model enabled; the optional second model and advanced KV-cache/throughput prediction are not implemented. Scheduler uses slot caps and pauses new dispatch at 90% reported vLLM KV-cache pressure. Worker heartbeats also report engine queue/running counts and NVIDIA utilization when nvidia-smi is available. One owner membership per self-service account is supported; organization/team management is outside this MVP UI. Request reservations, idempotency and leases are stored directly on durable job/request rows rather than separate bookkeeping tables; encryption uses PostgreSQL columns rather than an object store. Rate limiting is per API process; distributed enforcement is needed before horizontal API scaling. Provider accounting uses conservative quoted uptime estimates rather than invoice ingestion; compare against actual provider bills before unattended operation. Prometheus covers queue/slot/financial/heartbeat state, including reported GPU/KV-cache gauges; optional OTLP FastAPI instrumentation is implemented and requires the observability extra plus a collector. Real GPU telemetry remains unvalidated. Provider watchdog assumes a dedicated account and persistent independent execution; a control-plane budget check is not a provider-side billing guarantee.

See README.md for boot/test commands and docs/gpu-deploy.md for pinned rented-GPU attachment steps. Keep PROVISIONING_ENABLED=false and STRIPE_ENABLED=false until the relevant integration is intentionally configured and approved.
