# API v1

The authenticated `/internal/scheduling/report` now includes nonsecret API policy configuration, provider instance identity and fresh worker HTTP-overlap telemetry. It remains protected by the separate metrics credential; tenant API keys cannot read platform-wide data. Optional worker heartbeat fields add in-flight/peak HTTP calls, integrated overlap/request/observed seconds, completion/error counts and trace-write errors. These are not GPU kernel/sequence measurements; retain vLLM and hardware samples separately. See [the readiness report](microbatching-readiness.md) and regenerated `docs-openapi.json` for the measurement boundaries.
Interactive schemas: `/docs`; machine-readable `/openapi.json`. Requests/responses are JSON with `X-Request-ID`; JSON envelopes include `request_id`. TLS is required outside local development. Bearer API keys grant inference access. Dashboard uses HttpOnly SameSite cookies and a separate CSRF token for mutations. API keys cannot create keys.

| Method | Path | Purpose |
|---|---|---|
| GET | /v1/models | Exact revision, tokenizer, rates and mode |
| POST | /v1/jobs | Accept 1–100 requests, requires Idempotency-Key, returns 202 |
| GET | /v1/jobs | Tenant job history, offset cursor and limit |
| GET | /v1/jobs/{id} | Status, counts, timing, usage and money |
| GET | /v1/jobs/{id}/results | Ordered paginated partial results |
| GET | /v1/jobs/{id}/results.jsonl | Authenticated download |
| GET | /v1/jobs/{id}/receipts | Tenant-scoped, paginated terminal execution/settlement receipts |
| POST | /v1/jobs/{id}/cancel | Cancel queued/leased, signal running cancellation |
| GET | /v1/wallet | Available/reserved/total micro-USD |
| GET | /v1/wallet/transactions | Immutable paginated ledger |
| POST/GET | /v1/keys | Dashboard-only create once/list metadata |
| DELETE | /v1/keys/{id} | Immediate revocation |
| POST | /v1/webhook-destination | Dashboard-only HTTPS destination and one-time signing secret |
| POST | /v1/billing/checkout-session | Gated Stripe test top-up of $10/$25/$100 |
| POST | /auth/login | Local dev identity |
| GET | /auth/oidc/start | Managed OIDC authorization-code + PKCE redirect |
| GET | /auth/oidc/callback | State/nonce verification, session creation |
| GET | /auth/session | Recover session CSRF token after reload |
| POST | /auth/logout | Clear session |

```json
{"model":"qwen3-4b","tier":"standard","requests":[{"custom_id":"doc-1","messages":[{"role":"user","content":"Summarize this document"}],"max_output_tokens":128,"temperature":0.2,"top_p":1}]}
```

A same-tenant idempotency key and canonical body replay returns the same job; changed body returns 409. Bodies <=5 MiB; output <=2048, prompt <=8192 tokens; 2000 pending and 16 in-flight per tenant. Prompt URLs are inert text. Tools/multimodal/code execution are unsupported. Rates are test-only until measured and reviewed. Targets default to standard 30 minutes/economy 24 hours, best effort. Unstarted requests past target expire and release money; running work completes with `late=true`.

Results include input ordinal, custom_id, status, output_text, finish_reason, usage, charge and error. Pagination walks all input slots so pending/partial results retain order. Poll again from cursor 0 to refresh pending slots. Content disappears after 7 days while financial metadata remains.

Errors: 400 missing idempotency/invalid signature; 401 authentication; 403 CSRF/frozen; 404 missing or another tenant; 402 prepaid balance; 409 idempotency/stale lease; 413 body cap; 422 validation; 429 quota/rate; 503 gated external service. Envelope: `{"error":{"code":"...","message":"...","retryable":false},"request_id":"req_..."}`.

Webhooks are registered first, exact HTTPS URL required on submit. Terminal notification payload: event_id, type=job.completed, created_at, job_id, status. HMAC SHA256(timestamp + '.' + raw body), headers `X-IF-Timestamp`, `X-IF-Signature: v1=<hex>`. Verify within five minutes and dedupe event_id. Delivery retries exponentially for 24 hours; callbacks never change billing. New DNS IP requires re-registration. Redirects are rejected.

Internal routes have separate worker bearer credentials. Bootstrap register issues a one-hour token; heartbeat renews valid leases, poll returns assigned work, finalize requires current epoch. Stripe callback verifies raw-body signatures and never credits on browser redirect.

## Worker protocol and operational endpoints (migration 0005)
Worker enrollment includes repo, revision, tokenizer_revision and execution_mode; these must match the deployment configuration. Enrollment issues a fresh generation as well as a rotated worker token. Work items include an identity object with those four fields. Heartbeats include active: [{id, epoch}, ...] for requests still executing or retrying finalization, alongside optional telemetry. Only those current-generation epochs receive lease extensions. Old worker binaries must be restarted/upgraded with the API.

GET /metrics requires a separate METRICS_TOKEN bearer credential and is excluded from the dashboard proxy. Dashboard sessions and API keys share a database-backed fixed-window rate limit of 120 authenticated requests per tenant per UTC minute. Wallets expose debt_micro_usd; ledger entries expose debt_delta. Stripe webhooks use the API origin directly, never the dashboard proxy.

Worker poll accepts an optional JSON body `{ "available_slots": 0..16 }` and returns at most that many leased items. Workers subtract all still-running physical attempts from capacity, including stale attempts awaiting a finalization response. Active attempts are tracked by request ID plus epoch so an old completion cannot remove renewal for a newer attempt.


## v0.3 opt-in scheduling additions

`POST /v1/jobs` accepts `admission_policy` (`best_effort`, default; or `reject_if_at_risk`). With v2 enabled, omitted deadlines use `DEFAULT_COMPLETION_TARGET_SECONDS=3600`; explicit deadlines and existing accepted targets remain. The response adds persisted `admission` metadata: outcome, estimated seconds or null, target seconds, warm slots, backlog request count, risk, calibration/source, reasons, prediction time and startup/load assumptions. `deadline_is_guaranteed` stays false.

Strict admission returns 503 `deadline_not_feasible` before reservation if uncalibrated, without warm capacity, or estimated beyond target. If v2 is disabled it returns `deadline_estimator_disabled`. Increase target, attach approved calibrated capacity, or choose best effort. Normal idempotent retry returns the original prediction; legacy default-policy body hashes remain compatible.

`GET /v1/performance` uses normal tenant authentication and returns only that tenant's lifecycle/queue/deadline aggregates. `InferenceFlowClient.get_performance()` wraps it. `GET /internal/scheduling/report` uses the separate metrics bearer credential and returns platform capacity/economics and workers; tenant keys/sessions are denied. Dashboard operator access forwards a supplied credential to this single read-only path without storing it. See the scheduler architecture for windows, percentile denominators and provenance.
