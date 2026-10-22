# InferenceFlow — Executable MVP Product Specification
**Version:** 1.0  
**Date:** 22 October 2026  
**Status:** Implementation-ready proposal; prices, benchmarks and savings are hypotheses until measured.  
**Working name:** InferenceFlow (trademark/domain not checked).

## 0. Executive decision
Build a **self-service, prepaid, asynchronous inference API** for non-interactive text processing. Users send a job containing one or more chat-generation requests, receive a job ID immediately, and later fetch results or receive a signed webhook. InferenceFlow owns the queue, GPU execution, recovery, cost accounting and customer billing. It does **not** rent customers a slice of a physical GPU, and it is **not** a benchmarking product.

**MVP deployment choice:** one curated open-weight model on one NVIDIA GPU, with a second model behind a feature flag. Implement a local deterministic worker, a real vLLM worker, and a provider adapter capable of attaching to or creating a rented GPU. Use a strict provisioning kill switch and cost ceiling. A second GPU and multi-provider optimization are phase two.

**Wedge:** cost-sensitive developers running document extraction, enrichment, classification, summaries and synthetic-data batches that can wait minutes or hours. This is a **crowded market**: batching, serverless and usage billing already exist. The only viable differentiation is a better *measured* combination of price, deadline reliability, supported models and developer experience.

## 1. User, problem, promise
**User:** a solo developer or small engineering team with 10,000–10 million independent text inference requests per month, no desire to operate GPU infrastructure, and no hard interactive-latency requirement.

**Problem:** deploying models, reserving GPU capacity, model cold starts, batching, queueing, failures and per-job accounting are tedious. Traditional GPU rentals charge while idle. Existing hosted inference APIs solve much of this already; the startup must offer an objectively useful improvement.

**Promise:** “Submit text-generation batches to one API; pay by input/output tokens; choose an execution priority; get traceable results without managing GPUs.” Do **not** claim “cheapest inference” or “guaranteed deadlines” before evidence exists.

**North-star metric:** paid, successful inference requests per paid GPU hour, subject to acceptable quality and completion reliability. Commercial metrics: retained weekly active API customers, contribution margin, cost per million *successful* output tokens, deadline hit rate, and support burden.

## 2. MVP boundaries
### In scope (P0, required)
- Self-service account creation via a managed OIDC provider (dashboard) and API-key management (API).
- Prepaid USD credits: sandbox funding locally; Stripe Checkout top-ups for gated public beta, only after security and accounting review.
- Model catalog with exact revision, context cap, tokenizer and rates. One model enabled by default: `qwen3-4b`; optionally `qwen3-8b` behind a feature flag. Check model card/license and inference behavior for the pinned revision before launch.
- Async `POST /v1/jobs` with 1–100 independent chat requests, idempotency, status, results, cancellation, error detail and optional signed webhook.
- `standard` and `economy` priority tiers, **best-effort** target completion time, explicit expiration semantics, no guaranteed SLA.
- Durable per-request queue; one NVIDIA vLLM worker; worker registration/heartbeat; retries, lease expiry, idempotent finalization, safe partial results.
- Accurate usage metering and immutable wallet ledger; reserve worst-case cost on submission, capture completed usage once, release unused credit.
- GPU instance lifecycle interface with safe default `PROVISIONING_ENABLED=false`, one-GPU cap, daily cost ceiling, manual attach path and at least one provider adapter implemented against its **current official** API.
- Minimal dashboard: key management, top-up, submit sample job, status, result download, credit and usage history.
- Documentation, Python SDK, security controls, monitoring, alerts, tests and runbooks.

### Explicitly out of scope (P1/P2)
Real-time streaming chat, training, fine-tuning, arbitrary uploaded models or code, images/audio/video, embeddings, tool execution, multi-region residency, enterprise SSO, custom SLAs, complex autoscaling, Kubernetes, TPU, AMD/ROCm, custom CUDA kernels, and automatic routing across many providers. Do not represent a mock worker as live GPU execution.

### Defaults and limits (configurable)
| Parameter | Initial setting |
|---|---|
| Models | `qwen3-4b` live; `qwen3-8b` feature flagged |
| Max requests/job | 100 |
| Max JSON body | 5 MiB |
| Max prompt tokens/request | 8,192 (including chat template) |
| Max output tokens/request | 2,048 |
| Max pending requests/tenant | 2,000 |
| Max in-flight requests/tenant | 16 |
| Max active GPU instances | 1 |
| Result/prompt retention | 7 days by default, then delete; retain non-content financial ledger as legally needed |
| Standard target | default 30 minutes, best effort |
| Economy target | default 24 hours, best effort |
| Deadline missed before start | mark `expired`, release reservation; do not execute |
| Billing currency | integer micro-USD internally (1 USD = 1,000,000 micro-USD) |

Limits are product decisions, not hardware claims; reduce them if a selected GPU/model cannot support them safely.

## 3. Customer journey and core acceptance flow
1. Customer signs in, receives a one-time-displayed `if_live_...` API key and adds $10 in credits.
2. Calls `GET /v1/models` to discover allowed models, prices, context and tier limits.
3. Calls `POST /v1/jobs` with `Idempotency-Key`; the API validates messages, uses the exact pinned tokenizer/chat template to count prompt tokens, calculates a **maximum** output charge from `max_output_tokens`, atomically reserves credits and creates job/request rows.
4. API responds **202** immediately with job ID, `queued` status, price quote, and best-effort target time.
5. Scheduler selects runnable requests for a model-compatible warm worker using fairness, priority and age; worker pulls leased work over an authenticated outbound connection, invokes local vLLM, and records outputs and usage. vLLM handles **continuous batching** of concurrently submitted requests.
6. Worker atomically finalizes each request. Completed requests are billed exactly once; transient failures retry; permanent failures release their reservations.
7. Job becomes `succeeded`, `partially_succeeded`, `failed`, `canceled`, or `expired`. Customer polls results or receives a signed webhook.
8. Dashboard shows tokens, billed amount, remaining credits, execution duration and queue delay; customer can download a JSONL result file.

**Core promise to prove in a real GPU smoke test:** a paid account can submit 100 requests, get real model outputs, observe exact token usage and ledger entries, and recover correctly from a worker restart.

## 4. API contract v1
Base: `/v1`; JSON UTF-8; TLS required in production. Bearer API key required for all customer API calls. All responses include `request_id`. Timestamps are ISO-8601 UTC. API keys are displayed once and stored as a prefix plus keyed hash. Customer job IDs are opaque and tenant-scoped.

### `GET /v1/models`
Returns array of `{id, display_name, revision, max_context_tokens, max_prompt_tokens, max_output_tokens, input_price_micro_usd_per_million, output_price_micro_usd_per_million, supported_tiers, availability}`. Publish rates before accepting requests. Pricing is snapshotted onto each accepted request.

### `POST /v1/jobs`
Headers: `Authorization: Bearer if_live_...`, `Idempotency-Key: <random unique string>`.

```json
{
  "model": "qwen3-4b",
  "tier": "economy",
  "deadline_seconds": 86400,
  "requests": [
    {
      "custom_id": "doc-001",
      "messages": [
        {"role": "system", "content": "Return a concise summary."},
        {"role": "user", "content": "Summarize: ..."}
      ],
      "max_output_tokens": 256,
      "temperature": 0.2,
      "top_p": 1.0
    }
  ],
  "webhook_url": "https://customer.example/hooks/inference"
}
```

`webhook_url` is optional; safer alternative is a pre-registered webhook destination with a stored secret. Reject unsupported message content, tools, URLs embedded as external retrieval instructions, non-string multimodal inputs, duplicate `custom_id`, invalid token caps, and over-context requests. A text URL inside a prompt is treated as **text only**; InferenceFlow never fetches it.

**202 Accepted:**
```json
{
  "id": "job_01...",
  "status": "queued",
  "model": "qwen3-4b",
  "tier": "economy",
  "request_count": 1,
  "estimated_max_charge_micro_usd": 8500,
  "reserved_micro_usd": 8500,
  "created_at": "2026-10-22T12:00:00Z",
  "target_completion_at": "2026-10-23T12:00:00Z",
  "deadline_is_guaranteed": false
}
```

The `8500` above is **illustrative, not a public price**. Actual quotes must be computed from catalog rates and tokenizer counts.

### `GET /v1/jobs/{job_id}`
Returns `{id, status, model, tier, total, completed, failed, queued, running, created_at, started_at, completed_at, target_completion_at, reserved_micro_usd, captured_micro_usd, released_micro_usd, usage:{input_tokens,output_tokens}, error_summary}`. Polling supported with `Retry-After` on active jobs.

### `GET /v1/jobs/{job_id}/results?cursor=...&limit=100`
Returns `{job_id, items:[{custom_id,status,output_text,finish_reason,usage:{input_tokens,output_tokens},charge_micro_usd,error}],next_cursor,complete}`. Pending requests may be omitted; `complete=false` means partial results. Results preserve input order via `ordinal`. For large output provide short-lived signed download URL or authenticated JSONL endpoint.

### `POST /v1/jobs/{job_id}/cancel`
Returns `{id,status:"cancel_requested"}` if running, or `canceled` if no work started. Cancellation is **best effort** for running requests. Already completed work is billed; work not executed is not billed. Requests that finish despite cancellation may be billed if their outputs are made available. Make this policy visible to customers.

### `GET /v1/wallet` and `GET /v1/wallet/transactions`
Return `{available_micro_usd,reserved_micro_usd,total_balance_micro_usd}` and immutable paginated entries. Ledger includes top-ups, reservations, captures, releases, refunds and adjustments with references.

### `POST /v1/keys`, `GET /v1/keys`, `DELETE /v1/keys/{id}`
Create/show once; list metadata only; revoke immediately. Use dashboard session auth for key management; API-key-authenticated key creation is disabled unless narrowly scoped.

### `POST /v1/billing/checkout-session` (public beta gate)
Creates hosted Stripe Checkout Session for fixed top-up amounts; returns URL. Credits are **not** granted on redirect. `POST /internal/stripe/webhook` verifies signature and credited paid session idempotently. Reversals/chargebacks freeze or debit wallet according to published policy.

### Standard error envelope and status codes
`{"error":{"code":"insufficient_credits","message":"...","retryable":false},"request_id":"req_..."}`. Use `400` malformed JSON, `401` missing/invalid key, `403` forbidden, `404` resource not found/other tenant, `402` insufficient prepaid balance, `409` idempotency key reused with different body, `413` oversized body, `422` invalid model/parameters, `429` quota, `503` capacity unavailable. Do not reserve credits on validation errors. Store `(tenant_id, route, idempotency_key, canonical_body_hash, response_id)` with at least 24-hour retention.

### Webhook
Signed POST `{event_id,type:"job.completed",created_at,job_id,status}` with headers `X-IF-Timestamp` and `X-IF-Signature: v1=<hex HMAC-SHA256(timestamp + '.' + raw_body)>`. Verify using tenant-specific secret, five-minute replay tolerance, event ID deduplication, exponential retries for up to 24 hours. Webhook failures never change job/billing status. Block internal IPs, redirects, DNS rebinding, localhost, metadata endpoints and unapproved schemes; strongly prefer verified/pre-registered endpoints.

## 5. Data model and invariants
Tables (PostgreSQL 16; UUID/ULID PKs, UTC timestamps, tenant foreign keys, indexes):
- `tenants`, `users`, `tenant_memberships`, `api_keys` (prefix, keyed hash, scopes, revoked_at).
- `model_versions` (public id, provider repo, exact commit SHA, tokenizer revision, serving parameters, enabled flag, license review).
- `model_prices` (immutable versioned rate card and tier multiplier).
- `jobs` (tenant, status, tier, target, idempotency fingerprint, total count, cancel flag).
- `job_requests` (job_id, ordinal, custom_id, messages encrypted or in object store, prompt token count, max output, status, attempts, lease epoch, worker, output pointer, engine usage, timestamps).
- `worker_nodes`, `worker_leases`, `provider_instances`, `provider_cost_samples`.
- `wallets`, `wallet_ledger` (append-only signed integer micro-USD deltas with immutable unique source reference), `credit_reservations` (request-level amount, captured, released), `usage_records` (unique request_id for final bill), `payment_events` (unique processor event/session id), `webhook_deliveries`.
- `audit_events`, `idempotency_records`.

**Ledger invariant:** `available + reserved = funded_credits - captured_charges - reversed_funds + manual_adjustments`. More robustly, model wallet as an append-only accounting journal, with balances computed from postings and a materialized balance row updated under `SELECT ... FOR UPDATE`. Every accepted request has one reservation. Each request can have **at most one** successful capture (`UNIQUE(request_id, charge_type)`). Any unspent reservation is released exactly once. Never use floating point money.

**Request state machine:** `queued -> leased -> running -> succeeded | failed | canceled | expired`. `leased` and `running` may return to `queued` on recoverable lease expiry if `attempts < MAX_ATTEMPTS`; otherwise `failed`. Job status is derived from its requests, with `cancel_requested` an orthogonal flag. Terminal request state is immutable except via an explicit, audited administrative reconciliation workflow.

**Exactly-once accounting, at-least-once execution:** duplicate GPU work is possible if a worker dies after inference but before finalization; never promise exactly-once GPU execution. Use lease epochs/fencing tokens and an atomic compare-and-swap finalize transaction. Old worker completions are rejected. Persist usage + output pointer + ledger capture in one transaction, or via an idempotent transactional outbox if object storage is involved. Upload result object before DB commit, then garbage-collect orphan objects. No duplicate charge, even under concurrent completion events.

## 6. GPU worker and control-plane architecture
```text
Customer SDK / Dashboard
        | HTTPS
        v
FastAPI gateway -----> Postgres (auth, jobs, reservations, ledger)
        |                        ^
        |                        |
        +-----> Scheduler -------+    <--- provider cost samples
                    |
                    v
           Worker registry / leases
                    ^
                    | outbound authenticated polling
          GPU worker agent (rented VM/pod)
                    |
                    v
          vLLM localhost :8000 (pinned model)
                    |
                    v
             NVIDIA GPU (CUDA)

    Object storage: encrypted inputs/results, TTL purge
    Observability: traces, Prometheus metrics, alerts
    Stripe: hosted Checkout -> verified webhook -> wallet
```

**Why worker pulls:** rental GPU machines may not share a VPC with the control plane. The worker connects outbound to the API over TLS, authenticates with a short-lived scoped worker credential, heartbeats, leases work, calls its own vLLM server over loopback, and submits signed results. Never expose vLLM directly to the public internet. vLLM documentation notes that its `--api-key` does not authenticate all server routes; enforce network isolation in addition to an API key.

**Control plane:** FastAPI/Pydantic v2; PostgreSQL and SQLAlchemy 2/Alembic; scheduler as separate process. Start with Postgres `FOR UPDATE SKIP LOCKED` and row-level leases; no Redis or Kafka until queue pressure warrants it. Store short results in encrypted DB columns or object store; large results in S3-compatible object store with per-tenant access controls and expiring download URLs.

**Worker:** pinned container image; pinned vLLM version; pinned model repo SHA; fixed quantization/dtype; configured GPU memory cap, max context, max sequences and max batched tokens based on empirical fit. On boot, load weights once, run health/readiness and one inference canary, then register `ready`. Engine processes concurrent requests with continuous batching; do not build custom GPU kernels or assume physically partitioned GPU capacity.

**Model choice:** `Qwen/Qwen3-4B` first, `Qwen/Qwen3-8B` optional. Official model cards identify Apache-2.0 licensing as of this spec date; still pin and review exact weights, tokenizer, use restrictions, reasoning mode, template and output behavior. Treat max context and VRAM as **tested deployment parameters**, not promises inferred from model card.

**GPU choice:** first test a 24–48 GB NVIDIA GPU suitable for 4B model, then compare an 80 GB A100/H100 for higher concurrency. Actual throughput, latency, batch size, input/output mix, model quantization and price determine cost. Do not select H100 solely because it is fast.

## 7. Scheduling, admission and batching
**Admission:** validate tenant quotas, provider/model availability, request context, exact prompt tokenization and credit reservation. If there is no feasible capacity, return `503` (or accept with clearly disclosed best-effort delay policy); never accept a strict guarantee you cannot meet. In MVP target deadlines are preferences, not SLAs.

**Scheduler v1:** per model, consider only ready workers; pick requests using weighted fair queuing by tenant with aging (standard priority > economy, but economy cannot starve indefinitely). Prioritize warm-model affinity. Respect worker concurrency and KV-cache headroom. Lease requests transactionally in small chunks; lease TTL 60 seconds renewed by heartbeat (configurable); do not hold DB locks during GPU calls. Worker may send up to 16 concurrent async vLLM requests; vLLM performs continuous batching. Cap long prompts/output sizes to avoid head-of-line blocking.

**Deadline behavior:** if an unstarted request passes `target_completion_at`, expire it without charging. If already running at target time, let it finish and mark `late=true`; the target is best effort. Track p50/p95 queue wait, deadline hit rate, and age by tier. If this behavior is too confusing commercially, rename `deadline_seconds` to `target_completion_seconds` before public launch.

**Scale-up decision (P1):** compare (i) cost of leaving jobs queued until warm capacity is free versus (ii) cost of provisioning and loading another worker. Inputs: current backlog by model, estimated token workload, model throughput, startup latency, per-GPU price, utilization, and target slack. Never autoscale if `MAX_ACTIVE_GPUS`, daily provider spend or balance safety caps would be exceeded. Keep one model pinned per worker; do not hot-swap weights per request.

**Retries:** network failures, worker eviction and 5xx are retryable with exponential backoff; validation/4xx and context overflow are permanent. Max 3 attempts; after a lease expires, retry using a higher lease epoch. Failed attempts incur **provider cost to us** but no customer token charge unless a completed output is durably available under the published policy. Preserve partial success and bill successful requests only.

**Isolation:** no cross-tenant prompt/response logs. Disable cross-tenant prefix caching unless tested with per-tenant cache salting and memory isolation. Never expose engine metrics or control endpoints to customers. Scrub worker memory/ephemeral files between reassignments where needed; review hardware/provider multi-tenancy risks.

## 8. GPU provider lifecycle and cost controls
Use a `GpuProvider` interface:
```python
class GpuProvider(Protocol):
    async def create_instance(self, spec: GpuSpec, idempotency_key: str) -> Instance: ...
    async def get_instance(self, provider_id: str) -> Instance: ...
    async def terminate_instance(self, provider_id: str) -> None: ...
    async def list_instances(self, tag: str) -> list[Instance]: ...
    async def get_price_quote(self, gpu_type: str, region: str) -> PriceQuote: ...
```
Implement `FakeProvider` for CI, `AttachedWorkerProvider` for a manually provisioned rented GPU, and a real `RunpodProvider` behind credentials and `PROVISIONING_ENABLED=true`. Use official provider API/schema and pin integration tests; do not invent endpoints. **Creation is off by default**. Require instance tagging (`owner=inferenceflow`, `environment`, `created_by`, `job_group`) and an external reconciler that lists active instances every minute and terminates or alerts on untracked/orphaned resources.

Hard guardrails: `MAX_ACTIVE_GPUS=1`, `MAX_DAILY_GPU_SPEND_USD=25` initially, `MAX_GPU_SESSION_MINUTES=120`, idle shutdown after 10–15 minutes (tune to cold-start economics), no auto-provision in CI, separate provider account/project with limited funds, alert at 50/80/100% of budget. Daily spend cap is a **control-plane policy, not a perfect guarantee**: a provider may keep billing if control plane is down. Use provider-side spend alerts/limits where available and a separate watchdog.

**Observed provider context as of 22 Oct 2026:** Runpod's official pricing page (updated 8 Oct 2026) lists Pod L40S around $1.09/hour, A100 around $1.79/hour and H100 PCIe around $2.89/hour for the displayed configuration; these are *illustrative snapshots*, not guaranteed quotes or availability. The provider offers a different serverless tariff. Always query/confirm the live price and billing granularity before launch. Modal's public page publishes per-second GPU prices and hosted shared endpoints, making it a direct alternative rather than merely an infrastructure supplier.

## 9. Prepaid wallet, token metering and pricing
**Meter:** per request, exact `prompt_tokens` and `completion_tokens` reported by the engine. Count with pinned tokenizer at admission to estimate maximum; reconcile differences against engine usage. If engine usage is absent/inconsistent, quarantine for review; do not guess a customer charge. Capture only once.

**Price:** configurable model/tier rate card, denominated in micro-USD per 1,000,000 tokens, snapshotted at acceptance. For each request:

`reserved = ceil(prompt_token_upper_bound * input_rate / 1e6) + ceil(max_output_tokens * output_rate / 1e6)`

`actual = ceil(actual_input_tokens * input_rate / 1e6) + ceil(actual_output_tokens * output_rate / 1e6)`

`release = reserved - actual` (nonnegative; if not, flag mismatch and cap billing at reserved until reviewed). Economy discounts are a rate-card choice only if unit economics permit. Make rounding and refund behavior explicit. **No invented fixed public token prices**: populate catalog from measured throughput and target margin.

**Funding:** Stripe-hosted Checkout top-ups of $10/$25/$100 after beta gate. Verify signature on raw webhook body, require `payment_status=paid` or an equivalent verified successful settlement event, uniquely credit by Checkout Session/PaymentIntent, and reconcile chargebacks/refunds. Payment redirect alone never grants credit. Disallow negative available balance and disable submissions on disputed funding. Account for processing fees, tax/VAT and refunds in contribution margin; consult counsel/accountant for prepaid-credit rules in launch jurisdictions.

**Economics formula:**
- Customer revenue = input tokens × input rate + output tokens × output rate.
- Direct cost = billable GPU uptime (including warm/idle/cold starts) + CPU/control plane + storage/egress + payment fees + failed attempts + provider overhead.
- `cost_per_1M_successful_output_tokens = total_cost / successful_output_tokens * 1e6` (compare only on matched workload mix and quality).
- `gross_margin = (revenue - direct_cost) / revenue`.
- `break_even_output_tps = gpu_usd_per_hour * 1e6 / (3600 * productive_utilization * revenue_usd_per_1M_output_tokens)` if **all** revenue were output tokens; this intentionally ignores input revenue and other costs, so it is only a sanity check.

**Illustrative caution:** at $1.09/GPU-hour, 50% productive utilization and $0.30 revenue per million output tokens, the simplified break-even throughput is **~2,019 aggregate output tokens/second**. This is *not* a measured throughput number and does not establish feasibility; input charges and workload composition change the economics. The conclusion: a rented GPU may be **more expensive** than established batch APIs at low demand. Do not publish prices before representative load tests.

**Public launch price rule:** choose rates only after a 48-hour representative workload run and a model-matched comparison; target positive contribution margin and a defensible value proposition. Prefer a clear, modest niche advantage over a blanket “50% cheaper” claim.

## 10. Security, privacy and abuse
- Dashboard uses OIDC, secure cookies, CSRF protection and verified issuer/audience; API uses high-entropy scoped keys with keyed hashes at rest, rotation and revocation.
- All customer DB reads/writes require tenant predicate and tenant-aware object storage keys; enforce with repository layer and tests; optional PostgreSQL RLS as defense in depth.
- Encrypt data at rest and TLS in transit; secrets in environment/secret manager, not source; redact prompts, completions, API keys and payment details from logs. Retain payloads/results 7 days by default and delete via audited purge job. State third-party GPU-provider data processing explicitly.
- Restrict worker egress and control-plane access; private/loopback vLLM, scoped short-lived worker tokens, authenticated heartbeats, anti-replay/fencing. vLLM `--api-key` alone is insufficient to protect all server routes.
- Strict body, token, rate, credit and concurrency caps; deny arbitrary code execution, tool calls, external URL fetching, model uploads and arbitrary shell commands.
- Webhook URL SSRF defense (DNS/IP validation on every redirect/connect, no redirects preferred), TLS, signature, retry budget, per-tenant webhook rate cap.
- Fraud: first payment limits, refund/chargeback handling, suspicious signup detection, daily tenant quotas, API key abuse alerts, manual account suspension.
- Publish Terms, acceptable-use policy, data-retention/privacy notice, model license attribution, and provider processing disclosure before accepting public payments. Do not claim HIPAA/SOC 2/GDPR compliance without actual controls and review.

## 11. Operational metrics, alerts and dashboards
Instrument API submit p50/p95, accepted/rejected jobs, queued/running requests, queue age, completion target misses, model cold-start time, vLLM running/queued requests, prompt/output tokens, tokens/paid GPU-hour, engine error rate, retry rate, GPU utilization, KV cache pressure, paid provider uptime, spend, wallet ledger drift, untracked instances, webhook failures, revenue and contribution margin. Export Prometheus `/metrics`, OpenTelemetry traces and structured logs without content.

Alerts: worker no heartbeat >90 sec, queued standard job age >target, instance exists with no active worker, provider spend >80% budget, negative/imbalanced ledger, capture mismatch, error rate >5% for 5 minutes, API availability <99% over a rolling hour. Provide runbooks for stuck leases, leaked GPU instances, failed payments and corrupted token usage.

## 12. Competition and positioning (verified categories, not an exhaustive price audit)
| Alternative | Existing customer value | Implication for us |
|---|---|---|
| Modal | Per-second GPU execution, autoscaling, shared token-billed endpoints | Fractional/usage-based GPU economics are not novel. |
| Runpod | Pods and serverless GPU workers with usage-based billing | Renting/queueing GPUs alone is not a moat. |
| Together AI | Hosted model APIs and a Batch API with discounted async processing | “Batch = cheaper” is not unique. |
| Fireworks AI | Self-service token billing, prepaid credits, serving tiers | Prepaid credits and token pricing are commodity features. |
| Baseten / Replicate | Managed model deployment/execution APIs | Strong developer-experience substitutes. |
| AWS Bedrock / Google Vertex AI | Managed serving and batch workflows | Large-scale incumbent alternatives. |

**Possible wedge to test:** narrower support for high-volume, asynchronous small-model extraction jobs, transparent completion targets and billing, better reliability/cost at an identical pinned model, and simple migration tools. Do not promise customers an unverified cost advantage. Compare *same model revision, same tokenizer and decoding, input/output distribution, target window, failures, payment/egress overhead*.

## 13. Moat hypothesis and validation experiments
**Not moats:** an API wrapper, generic queues, prepaid billing, basic batching, standard vLLM, GPU provisioning, or a one-off price cut. These are replicable and largely available elsewhere.

**Potential compounding advantages:** (1) predictable demand aggregation that keeps models warm at high utilization; (2) scheduler data connecting workload shape, hardware, model and deadline to realized cost; (3) deadline-aware capacity procurement; (4) trust built by accurate billing and reliable execution; (5) embedded recurring batch pipelines and migration costs. All are hypotheses.

**Validation protocol:**
1. Recruit 5–10 users through self-service signup (not formal design partners) and obtain permission to use *anonymized workload metadata*, never raw prompts, for analysis.
2. Test at least three workloads: short classification, medium extraction and long summarization, with varying input/output lengths and burstiness.
3. For each, run a pinned model on InferenceFlow and comparable hosted/batch APIs; compare actual paid cost per 1M successful output tokens, output quality checks, failure rate, p50/p95 completion, and deadline hit rate. Include idle/cold start and provider bill.
4. Repeat at 10%, 30%, 60% and 80% demand occupancy. Show whether pooling reduces unit cost as volume rises; check if standard tier subsidizes economy.
5. Gate: >99% accounting reconciliation, >99% terminal completion under normal conditions, nonnegative contribution margin at projected load, and a meaningful matched-cost or UX win. A proposed >20% cost advantage is a **hypothesis test threshold**, not a launch promise.
6. If no advantage after a few representative cycles, narrow the segment or change product; do not keep adding infrastructure features without evidence.

## 14. Implementation milestones and exit gates
**M0 — days 1–3, skeleton:** monorepo, Postgres migrations, local Docker Compose, OIDC local dev substitute, API key auth, model catalog, health checks, CI. Exit: clean install boots and all migrations pass.

**M1 — days 4–7, real vertical slice:** submit → exact token count → reserve → queue → deterministic mock worker → capture/release → results/cancel. Exit: 100 mock requests and crash/retry tests pass with zero duplicate charges.

**M2 — week 2, GPU execution:** pin Qwen3-4B and vLLM image; worker agent outbound polling; attach rented NVIDIA GPU; run real prompts; test worker crash and recovery; metrics. Exit: 100 real GPU requests finish and match engine usage, without publicly exposing vLLM.

**M3 — week 3, payments and self-service:** dashboard, SDK, docs, Stripe sandbox Checkout, verified webhook, top-ups/refunds, usage views, quotas, signed callbacks. Exit: payment duplicate/reversal tests and tenant-isolation tests pass.

**M4 — week 4, safe beta:** provider lifecycle adapter and kill switch, cost reconciler, rate card based on measured costs, abuse/security review, retention purge, runbooks and load test. Exit: one-GPU cap verified, no orphan GPU after forced crash test, nonnegative expected contribution margin, 5–10 beta users can self-onboard.

**P1 (after signal):** economy pricing, second model, smarter model-affinity scheduler, multiple GPUs, workload-aware provider choice, batch file upload, detailed SLA tiers. **P2:** AMD/ROCm, multi-region, custom models, enterprise controls.

Timeline is an engineering estimate, not a promise. A lone engineer with Codex should implement M0–M2 before turning on payments.

## 15. Definition of done / test matrix
**Functional:** local `docker compose up --build` works; account/key, 100-request batch, polling, results, cancel, wallet, and dashboard. Separate real GPU instructions work against rented NVIDIA instance.

**Concurrency/correctness:** 100 concurrent submits; same idempotency key returns same job; same key with different body gives 409; insufficient balance never queues; concurrent wallet reserves cannot overspend; crash after inference before finalize causes at most one charge; stale lease completion rejected; terminal state immutable; cancel releases unstarted reservations; failed request does not charge; result order preserved; partial failure accurately reflected.

**Security:** tenant A cannot list/read/cancel tenant B jobs, results, wallet or keys; API key never logged; SSRF webhook URLs blocked; public vLLM unreachable; worker token cannot call customer API; no unbounded request size; TTL purge deletes raw content.

**Economics:** one complete sample cost report reconciles provider bill, paid uptime, failed attempts, tokens and customer revenue; no silent negative margin; provider cap tests prove no second instance launches when max=1.

**Operational:** `/healthz`, `/readyz`, `/metrics`; basic Grafana/Prometheus setup or documented equivalent; alerts for spend and orphan instances; README runbook and deployment checklist.

## 16. Implementation decisions that must remain explicit
- A **single rented GPU** can serve many customers concurrently via time-sharing and continuous batching; customers are charged for requests, not given GPU partitions.
- Exactly-once **billing** is attainable; exactly-once **physical execution** is not guaranteed after crashes.
- Prepaid credits protect against runaway customer bills but do not cap the company's provider bill unless GPU watchdogs work.
- Model compatibility, token accounting, output quality and throughput depend on exact pinned versions and must be tested.
- No live provider API keys, Stripe keys or user secrets should be embedded in code or sent to Codex; configure via environment/secret manager.
- Pricing and competitive claims must be revalidated before any public launch.

## 17. Official references checked 22 Oct 2026
- vLLM OpenAI-compatible serving/security: https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/
- vLLM metrics: https://docs.vllm.ai/en/latest/design/metrics/
- Qwen3-4B model card/license: https://huggingface.co/Qwen/Qwen3-4B
- Qwen3-8B model card/license: https://huggingface.co/Qwen/Qwen3-8B
- Runpod pricing (page says updated 8 Oct 2026): https://www.runpod.io/pricing
- Runpod official docs: https://docs.runpod.io/
- Modal pricing: https://modal.com/pricing
- Together Batch API: https://www.together.ai/blog/batch-api
- Fireworks pricing: https://fireworks.ai/pricing
- Stripe Checkout: https://docs.stripe.com/payments/checkout/quickstarts
- Stripe session payment status: https://docs.stripe.com/api/checkout/sessions/object
- Stripe idempotency: https://docs.stripe.com/api/idempotent_requests
