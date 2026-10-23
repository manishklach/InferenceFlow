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
- Pre-v0.3 baseline native suite: **56 passed, 1 skipped** (GPU opt-in).
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
Single model enabled; the optional second model and learned/heterogeneous throughput prediction are not implemented. The opt-in v0.3 estimator and adaptive dispatcher are described below. Scheduler uses slot caps and pauses new dispatch at 90% reported vLLM KV-cache pressure. Worker heartbeats also report engine queue/running counts and NVIDIA utilization when nvidia-smi is available. One owner membership per self-service account is supported; organization/team management is outside this MVP UI. Request reservations, idempotency and leases are stored directly on durable job/request rows rather than separate bookkeeping tables; encryption uses PostgreSQL columns rather than an object store. Rate limiting uses shared PostgreSQL counters across API replicas. Provider accounting uses conservative quoted uptime estimates rather than invoice ingestion; compare against actual provider bills before unattended operation. Prometheus covers queue/slot/financial/heartbeat state, including reported GPU/KV-cache gauges; optional OTLP FastAPI instrumentation is implemented and requires the observability extra plus a collector. Real GPU telemetry remains unvalidated. Provider watchdog assumes a dedicated account and persistent independent execution; a control-plane budget check is not a provider-side billing guarantee.

See README.md for boot/test commands and docs/gpu-deploy.md for pinned rented-GPU attachment steps. Keep PROVISIONING_ENABLED=false and STRIPE_ENABLED=false until the relevant integration is intentionally configured and approved.

## v0.3 scheduling review candidate

- Additive migration 0006: persisted admission snapshots, first dispatch, telemetry/adaptive state, per-attempt execution records, sampled GPU activity and internal cost profiles.
- DeadlineEstimator, bounded urgency/aging DispatchPolicy, independent adaptive slots and pure CapacityPlanner. Both scheduling flags default false; provisioning and Stripe stay disabled.
- Strict admission rejects uncertain/unachievable targets before reservation; default best effort is explicit, and legacy idempotency fingerprints remain compatible.
- GPU quote/invoice accounting and operator-only import/attachment/shutdown-record commands never alter customer prices or wallets and never create/stop provider capacity.
- Tenant performance API/SDK/dashboard plus separately authenticated operator capacity/economics, latency percentiles, actual-versus-predicted outcomes and measurement provenance.
- Six scenarios × three policy variants produce deterministic, checked-in simulation results. Real GPU calibration is deliberately false. The baseline is reproduced within the simulator, not measured on a GPU.
- Architecture/diagram, economics, benchmark/attachment plan, product positioning, blog and review release notes are included. See docs/architecture/scheduler-v2.md for gap analysis and rollback.

### Verification

Baseline before v0.3: 56 passed / one real-GPU test skipped; Ruff and mypy passed. An intermediate complete suite passed 74 tests / one GPU skip; subsequent fairness/concurrency/telemetry coverage is included in the final verification below. Dashboard production build passed with the new operator report route. No paid capacity or external payment/provider/OIDC accounts were contacted.

Final verification: 78 Python regression tests (including 22 new scheduling/economics cases) and one opt-in real-GPU test; the exact completed run is confirmed in the implementation report. The 31 existing platform tests also pass with SCHEDULER_V2_ENABLED=true. Ruff/mypy pass across 32 source modules; normal and isolated QA Next.js production builds pass; Docker Compose configuration validates. Two complete 18-run seed-42 simulations reproduce byte-for-byte. Browser QA confirmed tenant performance, authenticated operator reporting, zero registered real GPUs in mock mode, missing-cost labels and cleared operator input, with no browser errors. Unmodified captures are in docs/media/v03/.

This is a review candidate: do not infer a formal SLA, production readiness or verified economics. Prepare v0.3 release notes only; merge and release publication await review.
