# Copy/Paste Prompt for Codex — Build InferenceFlow MVP
**Version:** 1.0 — 22 October 2026  
**Use:** Paste the complete text below into Codex in a new repository. Place `inferenceflow_mvp_spec.md` in the repository root as the authoritative companion specification.

---

You are the founding CTO, principal backend engineer, and security reviewer for **InferenceFlow**. Implement a real, testable MVP of a **self-service, prepaid, pay-as-you-go, asynchronous GPU text-inference API**. Read `inferenceflow_mvp_spec.md` first and treat it as the source of truth; if absent, implement according to this prompt. **The core deliverable is actual inference execution and correct billing, not a benchmarking dashboard.**

## Product in one paragraph
A customer registers, creates an API key, prepays credits, submits a job containing 1–100 text-generation requests, receives a job ID immediately, waits while a GPU worker processes requests using a pinned open-weight model through vLLM, and fetches results or receives a signed webhook. The platform validates, queues, schedules, retries, meters, charges credits, and protects tenants. It runs locally with a deterministic mock worker and can run **real inference** by connecting a rented NVIDIA GPU with a pinned vLLM model. Start with `Qwen/Qwen3-4B` (`qwen3-4b` public ID), optional `Qwen/Qwen3-8B` behind a feature flag. Both require an exact model revision and license review before public launch.

## Operating rules
1. Implement code, migrations, Docker configs, tests, SDK, docs and runbooks—not just architecture prose. Do not claim mock output is GPU inference.
2. Do not invent cloud provider API endpoints, benchmark results, model license terms, token prices or working credentials. Check official documentation when available. If offline, implement provider adapter boundaries with explicit `NotConfigured` errors and leave a clear integration checklist; **never fake a live provisioning success**.
3. No secret values in source control. Use `.env.example`, environment variables and a documented secret manager strategy. `PROVISIONING_ENABLED=false` and `STRIPE_LIVE_MODE=false` by default.
4. Favor reliable boring components over infrastructure complexity: Postgres row leases instead of Kafka/Redis, Docker Compose instead of Kubernetes, one model/one GPU instead of multi-provider routing.
5. Do not ask for credentials to implement local mode. If live credentials are missing, finish everything possible and provide exact safe steps for later integration.
6. After each phase run tests, fix errors, commit logically if git access is available, and update `IMPLEMENTATION_STATUS.md` with tested behavior, commands and known gaps.
7. If work exceeds the context window, prioritize a **working vertical slice** (`authenticate -> validate -> reserve -> enqueue -> execute -> meter -> capture/release -> results`) and produce an exact continuation prompt; never silently omit unfinished work.

## Required technology
- Python 3.12; FastAPI; Pydantic 2; SQLAlchemy 2 async or sync consistently; Alembic; PostgreSQL 16; `httpx`; `pytest`; `pytest-asyncio` if async; Ruff; mypy/pyright; structured JSON logs.
- Scheduler and GPU worker agent as separate Python services. Use Postgres `SELECT ... FOR UPDATE SKIP LOCKED` and lease epochs/fencing tokens for durable dispatch. Do not hold a transaction open during inference.
- NVIDIA GPU serving: **vLLM OpenAI-compatible server**, pinned image/version/model revision, `stream=false`, chat completions. The GPU worker agent calls vLLM over localhost/private Docker network, not over the public internet.
- Dashboard: minimal Next.js + TypeScript UI with accessible forms and account/session auth; prefer managed OIDC with local-dev mock sign-in rather than inventing an insecure production password system.
- Payments: Stripe Checkout **test mode** only until explicitly enabled; webhook signature verification and idempotent credit posting. No direct card handling.
- Docker Compose for local CPU/mock stack. Separate documented GPU deployment (Docker Compose GPU profile or equivalent). GitHub Actions lint, typecheck and tests.
- OpenAPI, Python SDK (`InferenceFlowClient`), `.env.example`, `Makefile`, `README.md`, `/healthz`, `/readyz`, `/metrics`, and an ops runbook.

## Repo structure (adjust only if justified)
```text
inferenceflow/
  apps/api/              # FastAPI public + internal routes
  apps/scheduler/        # admission to worker capacity, fairness, lease assignment
  apps/worker/           # outbound polling agent, vLLM adapter, mock adapter
  apps/dashboard/        # Next.js minimal self-service UI
  packages/common/       # schemas, db, ledger, auth, model registry, logging
  packages/python_sdk/   # typed customer SDK
  infra/                 # Dockerfiles, compose, provider config, observability
  migrations/            # Alembic
  tests/unit/
  tests/integration/
  tests/security/
  tests/e2e/
  docs/                  # API, deployment, runbooks, pricing, privacy, ADRs
  .env.example
  docker-compose.yml
  Makefile
  README.md
  IMPLEMENTATION_STATUS.md
  inferenceflow_mvp_spec.md
```

## P0 implementation sequence
### Phase A — bootable foundation
Create project, lock dependencies, formatting/type checks, `.env.example`, migrations, Postgres connection pooling, OIDC abstraction/local dev login, tenant-aware auth, API key creation with secure random key (shown once), keyed hash stored at rest, prefix lookup, rotation/revocation, scopes, and model catalog. Create health/ready/metrics endpoints. Add migrations and a local test seed command. `docker compose up --build` must start Postgres, API, scheduler, mock worker and dashboard without GPU, cloud credentials or Stripe.

### Phase B — exact API contracts
Implement:
- `GET /v1/models` — versioned model, max context, supported tiers, immutable input/output rates per million tokens.
- `POST /v1/jobs` — JSON payload with `model`, `tier`, optional `deadline_seconds`, `requests[]`, optional pre-registered `webhook_url`. Requires `Idempotency-Key`; returns `202` with opaque job ID and reserved amount.
- `GET /v1/jobs/{id}` — status, progress, timestamps, usage, reservations/captures, errors.
- `GET /v1/jobs/{id}/results?cursor=&limit=` — ordered per-request outputs/errors, partial results and `complete` flag; support JSONL download.
- `POST /v1/jobs/{id}/cancel` — best-effort cancel and correct billing/refund semantics.
- `GET /v1/wallet`, `GET /v1/wallet/transactions`.
- Dashboard-authenticated `POST /v1/keys`, `GET /v1/keys`, `DELETE /v1/keys/{id}`.
- `POST /v1/billing/checkout-session` in Stripe test mode; `POST /internal/stripe/webhook` verified and idempotent.
- Internal worker register/heartbeat/poll/finalize endpoints with **separate scoped worker credentials**; do not expose these as customer APIs.

Use Pydantic request/response schemas, OpenAPI examples, standard error envelope, request IDs, pagination, typed HTTP status codes and 429 rate limits. Define body size <=5 MiB, requests/job <=100, prompt <=8192 tokens, max output <=2048 tokens, per-tenant queued <=2000, per-tenant running <=16; config-driven. Only accept string-based system/user/assistant chat messages. Reject arbitrary tools, external URL fetching and customer code.

Example submit payload:
```json
{
  "model": "qwen3-4b",
  "tier": "economy",
  "deadline_seconds": 86400,
  "requests": [
    {"custom_id": "doc-001", "messages": [
      {"role": "system", "content": "Summarize the following text."},
      {"role": "user", "content": "Example document text."}
    ], "max_output_tokens": 256, "temperature": 0.2, "top_p": 1.0}
  ]
}
```

### Phase C — database, state machine and idempotency
Migrate tables: `tenants`, `users`, `tenant_memberships`, `api_keys`, `model_versions`, `model_prices`, `jobs`, `job_requests`, `worker_nodes`, `worker_leases`, `provider_instances`, `provider_cost_samples`, `wallets`, `wallet_ledger`, `credit_reservations`, `usage_records`, `payment_events`, `webhook_deliveries`, `audit_events`, `idempotency_records`.

Add foreign keys, unique indexes, tenant predicates, timestamps and immutable versioned price snapshots. `job_requests` has `ordinal`, `custom_id`, `lease_epoch`, `attempts`, `status`, `worker_id`, encrypted payload or object-store pointer, result pointer, usage, failure reason, timestamps. Unique `(job_id,custom_id)` and `(job_id,ordinal)`. Unique `(tenant_id,route,idempotency_key)` with canonical body hash; same key+same body returns same job; same key+different body returns 409. Request states `queued,leased,running,succeeded,failed,canceled,expired`; job status derived from request states, with cancel flag.

**Correctness:** execution is at-least-once; billing must be exactly-once. Use monotonic lease epochs/fencing tokens. Atomic finalization checks current lease epoch and request state, persists usage/result reference, writes one capture entry, releases remainder, and updates status. Late/stale worker completion must not overwrite or bill. Terminal state immutable except audited reconciliation. Recover abandoned leases and retry transient errors with max attempts=3 and exponential backoff. No DB lock held during GPU call.

### Phase D — wallet and metering
Represent money as integer **micro-USD**, never floats. Build append-only ledger and materialized balances with transactional locks. On job acceptance, use **the exact pinned model tokenizer and chat template** to calculate a conservative prompt token upper bound; reject overflow. Reserve maximum estimated input+output cost from rate snapshot; do not accept if available credit insufficient. On each successfully completed request, capture actual engine-reported prompt/completion tokens, release unused reservation. Failed/unstarted requests release reservation. Cancellation charges only completed available output, refunds unstarted work; running work may finish under documented best-effort policy. Missing engine usage goes into `billing_pending`/manual reconciliation; do not invent a charge.

Formula, rates in micro-USD per million tokens:
```python
reserve = ceil(prompt_upper_bound * input_rate / 1_000_000) \
        + ceil(max_output_tokens * output_rate / 1_000_000)
charge  = ceil(actual_input_tokens * input_rate / 1_000_000) \
        + ceil(actual_output_tokens * output_rate / 1_000_000)
release = reserve - charge
```
If actual charge > reservation, flag discrepancy, cap customer charge at reservation until reconciled, and alert. Write unit tests for rounding, concurrency, failed attempts, double completion, retries, negative balances, duplicate payment events and reconciliation. Do not set public token rates without measured cost data; seed clearly labeled **test-only** rates.

### Phase E — durable scheduler and GPU worker
Implement scheduler using transactional Postgres leases. Choose requests by model affinity, tier, queue age and weighted tenant fairness. Standard requests have higher weight but economy cannot starve. Respect `max_inflight`, ready-worker capacity and target completion preferences. If an unstarted request passes its target, expire/release it; running requests may finish late. `deadline_seconds` is best-effort, never a guarantee.

Worker registers and heartbeats, polls outbound over HTTPS with scoped credentials, acquires lease with fencing epoch, and invokes local vLLM `/v1/chat/completions` using `httpx.AsyncClient`. Allow configurable concurrency (start <=16), so **vLLM continuous batching** combines concurrent model requests; do not write custom CUDA kernels. Persist `prompt_tokens`, `completion_tokens`, output text, finish reason, duration and error class. Run one pinned model per worker and keep it warm. Build `MockInferenceEngine` with deterministic output and realistic usage for CPU tests; label mock mode visibly in dashboard and docs. Implement cancellation signal checks before execution and best-effort interruption during running.

Implement `VllmInferenceEngine` with retries/timeouts and health probes. The vLLM API key is **not sufficient** to secure all server endpoints according to vLLM docs; bind it to loopback/private network, block public ingress, and restrict worker-to-control-plane traffic. Model and tokenizer revisions must match. For Qwen3 reasoning/chat-template behavior, check pinned model docs and set explicit, reproducible serving parameters rather than relying on defaults.

### Phase F — rented GPU provider adapter and guardrails
Define provider interface: `create_instance(spec,idempotency_key)`, `get_instance(id)`, `list_instances(tags)`, `terminate_instance(id)`, `get_price_quote(gpu_type,region)`. Implement:
1. `FakeProvider` for tests;
2. `AttachedWorkerProvider` for a GPU rented manually (real inference without automated provisioning);
3. `RunpodProvider` using current official Runpod docs/API, guarded behind `PROVISIONING_ENABLED=true`. If no credentials, it should be importable and testable with mocked HTTP responses but **must not** claim a live instance was created.

Defaults: `PROVISIONING_ENABLED=false`, `MAX_ACTIVE_GPUS=1`, `MAX_DAILY_GPU_SPEND_USD=25`, `MAX_GPU_SESSION_MINUTES=120`, `IDLE_SHUTDOWN_SECONDS=900`. Implement instance tagging, provider inventory reconciliation and orphan-instance alerts. A separate watchdog should try to terminate an instance on expired session or spend cap. No CI/test should ever launch billable GPUs. Do not rely on hard spend cap alone—provider may continue billing during control-plane failure. Store price quotes with timestamps and distinguish quotes from invoices.

### Phase G — dashboard, payments, webhook, SDK
Dashboard screens: sign in, create/revoke key, show available/reserved credits, Stripe test top-up, submit a sample job, job history/status, results/JSONL download, token usage and charges. Prioritize usability over visual polish.

Stripe: hosted Checkout, verified raw-body webhook signature, `payment_status=paid` before posting credits, unique Checkout Session/PaymentIntent ID, duplicate event tolerance, refund/chargeback reversal and account freeze. Never store card details or credit on return URL. Provide `STRIPE_ENABLED=false` local mode with an explicit admin-only seed-credit CLI.

Customer webhooks: require registered HTTPS endpoint, HMAC SHA256 over timestamp+raw payload, unique event IDs, 5-minute replay window, retries with backoff, delivery audit. Implement SSRF protection including internal IPs, DNS rebinding and redirect denial. SDK: `create_job`, `get_job`, `wait_for_job`, `get_results`, `cancel_job`, `get_models`, `get_wallet`, and automatic idempotency key generation/retry.

### Phase H — observability, security, deployment
Metrics: queue wait, jobs by status, requests/tenant, successful tokens, vLLM utilization/KV cache, retries, late targets, worker heartbeat, paid GPU seconds, provider spend, wallet reconciliation drift, contribution margin and webhook failures. `/healthz`, `/readyz`, `/metrics`, JSON logs with prompts/keys redacted, OpenTelemetry-ready traces. Add daily TTL purge of prompts/results (7 days by default), retain minimal billing records. Implement tenant-scoped queries and optionally Postgres RLS; tests must prove cross-tenant denial. Add rate limits, API request size limits, worker token rotation, CSRF on dashboard, secure cookies and strict CORS.

Provide two deployment paths:
- Local: `docker compose up --build` with mock worker and seed credits.
- Real GPU: CPU control plane on a small VM/managed service plus PostgreSQL; rented NVIDIA GPU running vLLM and worker agent; worker connects **outbound** to control plane. Include exact env vars, model download/pinning, Docker command/config, private networking and a real smoke test. No live payment or GPU creation by default.

## Tests that MUST exist
Use pytest and integration tests against real Postgres, not SQLite pretending to provide Postgres locking. Include:
1. Migration up/down and boot from clean checkout.
2. API key creation, hashing, revocation and tenant-scoped auth.
3. Duplicate idempotency key same payload -> same job, different payload -> 409.
4. 100-request job ordering, partial success, pagination and JSONL.
5. Concurrent wallet reserves never overspend; insufficient funds returns 402 with no queued rows.
6. Exact token-based reserve, capture, release, rounding and immutable ledger reconciliation.
7. Duplicate worker completion and stale fencing token -> **no duplicate charge**.
8. Worker killed after model output but before DB commit -> retry/recovery and one final charge.
9. Worker lease expiry and bounded retries; permanent failure releases unused credit.
10. Cancel queued/running work with correct charges/refunds.
11. Deadline expires before start; late-running request is flagged.
12. Tenant A cannot access tenant B jobs, keys, wallet, results, objects or worker internals.
13. Reject malicious webhook URLs (`localhost`, `127.0.0.1`, private ranges, cloud metadata IP, DNS rebinding and redirects).
14. Payment webhook signature invalid -> no credit; duplicate paid event -> one credit; refund -> reversal/freeze.
15. Provider creation disabled by default; max 1 GPU; orphan detection; no billable provisioning in CI.
16. Structured logs redact prompts, completions, bearer keys and Stripe secrets.
17. Result TTL purge removes raw content but leaves minimal ledger entries.
18. At least 100 concurrent mock requests with no stuck rows or ledger drift.
19. Real vLLM smoke test behind `RUN_GPU_E2E=1` (skip in CI unless GPU configured); verify nonempty real output, engine usage, successful capture and results.

## Definition of done / demonstration
From a fresh checkout with Docker installed, documented commands must:
1. Boot Postgres/API/scheduler/mock worker/dashboard.
2. Seed a test tenant and $10 credits via explicit dev-only command.
3. Create an API key and call `GET /v1/models`.
4. Submit a job of 100 requests and receive HTTP 202 immediately.
5. Poll until terminal and download ordered results.
6. Show exact ledger reserve/capture/release with no duplicate charge.
7. Cancel a queued job and verify released funds.
8. Run `make test`, `make lint`, `make typecheck` successfully.
9. When a real GPU is attached, execute a **real** `Qwen3-4B` inference end-to-end and show token usage and charge.
10. Demonstrate `PROVISIONING_ENABLED=false` prevents any paid instance launch.

Produce final artifacts: source code, migrations, tests, docs, `.env.example`, API examples, SDK, `IMPLEMENTATION_STATUS.md`, security and operations checklist, and a final report stating exactly what was executed, what remains untested, and how to launch a **limited** prepaid beta safely.

## Documentation required
- `README.md`: copy-paste local quickstart and expected JSON outputs.
- `docs/architecture.md`: architecture diagram, state machine, failure/recovery semantics, database invariants.
- `docs/api.md`: all public endpoints, errors, idempotency, cancellation, pricing and webhook contract.
- `docs/gpu-deploy.md`: verified rented NVIDIA GPU setup, pinned model/vLLM, worker connection, network isolation and shutdown.
- `docs/billing.md`: ledger accounting, payment event dedupe, refunds, sample calculation, reconciliation SQL.
- `docs/security.md`: tenant isolation, API key design, threat model, SSRF, logging, retention, abuse limits.
- `docs/ops.md`: cost leak watchdog, stuck leases, failed webhooks, provider billing, outage and rollback runbooks.
- `docs/pricing-experiment.md`: **internal only** model-matched workload methodology; not a benchmarking product or public promise.

## Start now
First output a concise architecture and file tree, identify the hardest correctness risks, and list the first five executable tasks. Then create the project files and implement Phase A through the end-to-end vertical slice. Run commands and tests, report real results, fix failures, and proceed through the remaining phases. Do not stop at planning. If a feature is not implemented, label it incomplete rather than providing a dummy success response. At the end, provide the exact commands to boot local mode, execute a mock job, connect a real rented GPU, and test the accounting invariants.

---

### Companion references (verify before coding provider-specific integration)
- `inferenceflow_mvp_spec.md` in repository root.
- https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/
- https://docs.vllm.ai/en/latest/design/metrics/
- https://huggingface.co/Qwen/Qwen3-4B
- https://docs.runpod.io/
- https://www.runpod.io/pricing
- https://docs.stripe.com/payments/checkout/quickstarts
- https://docs.stripe.com/api/checkout/sessions/object
