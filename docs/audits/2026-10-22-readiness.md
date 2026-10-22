# InferenceFlow production readiness audit

> Historical audit of commit `1204670`. The source findings have since been addressed; see the [remediation and upgrade guide](2026-10-22-remediation.md). External GPU and production deployment validation remain outstanding.

Date: 2026-10-22
Repository: https://github.com/manishklach/inferenceflow
Audited commit: `1204670b4ec3a0396073324aa33e8a35b962c2b1` (main / v0.1.0)

## Assessment

**Do not enable paid production traffic yet.** This is a working mock execution MVP with substantive accounting, isolation, and lifecycle tests. The audit nevertheless found defects affecting worker trust, recovery, artifact correctness, refund handling, GPU provisioning, and scheduler availability. Passing ledger reconciliation does not establish financial correctness.

No application fixes, cloud provisioning, real payment transactions, commits, pushes, or release changes were performed during this audit. New files are this report and ignored local reproduction probes.

## Scope and evidence

Reviewed FastAPI authentication and internal worker routes; PostgreSQL models and transaction paths; scheduler, worker and vLLM adapters; provider creation/watchdog; Stripe event processing; metering, ledger and reconciliation; callbacks; dashboard authentication/proxy; deployment and operational documentation.

Validation performed against the dedicated PostgreSQL test database:

| Check | Result |
|---|---|
| Existing pytest suite | 32 passed, 1 skipped; one Starlette/AnyIO deprecation warning |
| Ruff | Passed |
| mypy apps packages | Passed, 26 source files |
| Additional defect reproduction probes | 7 passed, confirming the unsafe behaviors described below |
| Dashboard npm audit --omit=dev | Zero reported production dependency advisories |

The seven probe tests intentionally assert defective behavior; their passing results are evidence of defects, not acceptance criteria. Local script: `.runtime/audit_tests/test_probes.py`. Run from the repository root:

~~~powershell
.venv/Scripts/python -m pytest -q --tb=short
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m mypy apps packages
.venv/Scripts/python -m pytest -p tests.conftest .runtime/audit_tests/test_probes.py -q --tb=short
cd apps/dashboard
npm audit --omit=dev --json
~~~

Only the dashboard-directory npm audit result applies to this repository. An initial root-directory invocation resolved an ancestor npm project; its findings were excluded. No Python advisory or container-image vulnerability scan was performed. Neither dependency audit nor static checks establish absence of exploitable defects.

## Findings

### IF-01 — High / P1: Production accepts the published worker bootstrap credential

**Evidence:** `packages/common/config.py:10,42`; `apps/api/main.py:445`; `apps/dashboard/next.config.ts:5`.
**Confirmed by:** `test_production_accepts_default_worker_bootstrap`.

Production validation requires a replacement application secret and OIDC settings, but leaves `WORKER_BOOTSTRAP_TOKEN=local-worker-only` valid. A caller with that published value can register a worker, poll assigned customer requests, and submit results. Registration also permits replacement of an existing worker ID. The dashboard catchall proxy forwards internal API paths, so merely hiding the API origin does not remove this route.

**Impact:** If deployed with the default worker token and reachable internal routes, an unauthenticated outsider can obtain customer prompts and falsify billable inference results.

**Remediation:** Reject default, missing, and weak bootstrap credentials outside development; use short-lived, scoped enrollment credentials and unique worker identities. Restrict internal routes at both API ingress and dashboard proxy. Add a production configuration test that fails with the documented default.

### IF-02 — High / P1: Heartbeats indefinitely renew requests the worker no longer executes

**Evidence:** `apps/api/main.py:466`; `apps/worker/main.py:44,54`.
**Confirmed by:** `test_restart_renews_abandoned_running_request`.

Heartbeats renew every unexpired leased/running request assigned to a worker ID, without receiving active request IDs or epochs. After a restart under the same ID, old running requests are not returned by poll, but the new worker's heartbeat continues renewing them. Separately, after three failed finalization attempts, the task exits without a durable completion record; the process can continue renewing that request.

**Impact:** Jobs and prepaid reservations can remain stuck indefinitely, and worker slots remain occupied. Existing expired-lease tests do not cover this live-heartbeat failure.

**Remediation:** Introduce worker boot/session generations and renew only explicitly reported active request epochs. Fence prior generations on registration. Persist/retry finalization until acknowledged or deliberately relinquish the lease. Test same-ID restart, lost finalization acknowledgments, and prolonged control-plane failures.

### IF-03 — High / P1: Scheduling does not enforce immutable model revision or execution mode

**Evidence:** `packages/common/service.py:306,352`; `apps/api/main.py:445,498`; `apps/worker/main.py:13,25`; `apps/worker/engines.py:36`.
**Confirmed by:** `test_model_revision_not_checked_at_dispatch`.

Admission snapshots a request's revision, but dispatch filters only the public model alias. A request admitted under revision A is dispatched to a worker enrolled under the current revision B. Workers do not retain a verified revision/mode identity for compatibility filtering, and poll does not return the required revision. Registration trusts the worker's configured revision string. The engine canary checks response availability, not artifact identity; its boolean result is ignored by worker startup.

**Impact:** Outputs and usage may come from a different model/tokenizer than the customer job snapshot. Input-token mismatches can quarantine billing, while matching token counts do not prove the correct artifact ran. Configuration alone also does not prevent a mock engine claiming a real revision.

**Remediation:** Store worker model repository, revision, tokenizer revision, execution mode, and boot generation; match all required fields at dispatch. Validate the served deployment artifact at startup, fail closed on a failed canary, and include required artifact identity in the work contract. Test rolling revision changes and mock/real mismatches.

### IF-04 — High / P1: Refunded or disputed reserved funds can still finance inference

**Evidence:** `packages/common/payments.py:29`; `packages/common/service.py:79,254,306,406`.
**Confirmed by:** `test_refunded_frozen_tenant_still_executes`.

A refund freezes the tenant and debits available balance, but reserved funds remain attached to queued work. Only submission checks the freeze; dispatch and successful finalization continue. A full refund can therefore be followed by successful inference and capture, with unused reservation released back into available credit. The reversal shortfall is an audit entry rather than an enforced financial liability; reconciliation still returns no drift.

**Impact:** The platform can spend GPU money against reversed customer funding while reporting internally balanced wallets.

**Remediation:** Define and enforce freeze/reversal semantics across queued, leased, running, and quarantined requests under wallet locks. Stop new dispatch immediately; cancel/release or settle in-flight work according to an explicit policy. Represent funding reversals/debt in accounting invariants and prevent released reserved funds from becoming spendable before debt is cleared. Reconcile outstanding reservations, usage captures, payment reversals, and liabilities in addition to ledger sums.

### IF-05 — High / P1: The independent watchdog can delete a pod during successful creation

**Evidence:** `packages/common/providers.py:117,151,172,180`.
**Confirmed by:** `test_creation_watchdog_race`, with all provider calls replaced by an in-memory fake.

Creation commits an `intent_<source>` row, calls the provider, and subsequently changes the row's ID to the actual pod ID. Between those steps, inventory can contain the new pod while the database tracks only the intent ID. The watchdog identifies the pod as an orphan and immediately terminates it. Creation can then return success and store the now-terminated pod as active.

**Impact:** Paid startup capacity can be destroyed, requests receive no capacity, and the active-instance cap can block replacement.

**Remediation:** Reconcile inventory against deterministic creation names/source identifiers as well as provider IDs. Distinguish pending, ambiguous, active, and terminated states; apply a bounded creation grace period and coordinate reconciliation with creation. Also reconcile tracked instances that disappear from provider inventory. Keep the concurrent create/watchdog test as a regression test.

### IF-06 — High / P1: Customer callback delivery blocks scheduling and recovery

**Evidence:** `apps/scheduler/main.py:7`; `packages/common/webhooks.py:45,55,63,67`.
**Evidence type:** Code-path review; no external slow-endpoint traffic generated.

The single scheduler loop calls synchronous callback delivery before its next scheduling/recovery pass. Up to ten due deliveries execute sequentially, each with a ten-second HTTP timeout and an open delivery transaction. Ten connect/read stalls can delay the next pass by roughly 100 seconds; the HTTP timeout is not a strict whole-request deadline, and synchronous DNS adds further uncertainty.

**Impact:** A tenant-controlled slow public callback endpoint can delay other tenants' inference dispatch, deadline processing, and lease recovery while rented GPUs remain idle.

**Remediation:** Move callback delivery to a separate worker/process with bounded concurrency and overall deadlines. Keep database transactions short around claiming and recording delivery, rather than holding them during network I/O. Test that stalled callbacks do not affect scheduler cadence.

### IF-07 — Medium / P2: One tenant wallet lock can stall all scheduling

**Evidence:** `packages/common/service.py:66,119,306`.
**Evidence type:** Code-path review; no load benchmark performed.

Every scheduler transaction locks every tenant wallet, including wallets without active work, before dispatch finishes. These wallet locks do not skip locked rows. Submission also holds its wallet lock during token counting. A long-running transaction for one tenant can therefore block the global dispatch/recovery transaction; the global advisory lock prevents another scheduler from making progress. Candidate loading and per-worker tenant count queries further increase transaction duration with scale.

**Impact:** Queue isolation and multi-tenant availability degrade under contention; `SKIP LOCKED` on request rows does not resolve the preceding wallet bottleneck.

**Remediation:** Process bounded tenant/request batches, avoid blocking on unrelated idle wallets, and retain a consistent lock order. Move expensive tokenization outside the wallet-critical section with safe admission revalidation. Add contention and throughput tests using multiple tenants and API processes.

### IF-08 — Medium / P2: Dashboard sessions bypass customer rate limiting

**Evidence:** `apps/api/main.py:107,124,139`.
**Confirmed by:** `test_cookie_session_bypasses_api_rate_limit`.

The rolling per-tenant rate limit exists only in API-key authentication. A valid dashboard cookie routes requests directly through session authentication, without applying that limit. In the reproduction, 121 wallet requests using a session all succeeded; the same number using an API key produced the expected 429 on request 121. API-key counters are also process-local, so multiple replicas multiply the effective allowance.

**Impact:** Authenticated tenants can bypass documented API request limits and amplify control-plane/database load.

**Remediation:** Apply one tenant-level rate limiter after either authentication mechanism, backed by shared state or a verified ingress policy. Independently limit expensive endpoints and unauthenticated login/enrollment traffic.

### IF-09 — Medium / P2: Operational metrics are publicly reachable through the application

**Evidence:** `apps/api/main.py:165`; `apps/dashboard/next.config.ts:5`.
**Confirmed by:** `test_metrics_public`.

The metrics endpoint requires no authentication. It exports operational and accounting aggregates; the dashboard proxy forwards `/api/metrics` to it. A deployment that only closes direct access to the API origin still exposes the proxied route unless ingress adds an explicit restriction.

**Impact:** External callers can inspect platform operations and financial/activity aggregates. This is not evidence that prompts or API credentials are exported.

**Remediation:** Bind metrics to a private management surface or authenticate/restrict scraping. Exclude management and internal worker paths from the public dashboard proxy; verify the deployed ingress policy.

### IF-10 — Medium / P2: Secret rotation has no compatible data/key migration path

**Evidence:** `packages/common/security.py:13,17,25`; `apps/api/main.py:124`.
**Evidence type:** Code-path review.

The application secret is used for API/worker credential HMACs, dashboard JWTs, and derivation of the single prompt/result encryption key. Replacing it immediately invalidates credentials and makes existing encrypted payloads unreadable. Ciphertexts carry no application key version and decryption supports no historical key ring.

**Impact:** Routine rotation or incident response can interrupt active inference and prevent result retrieval; keeping an exposed old secret indefinitely undermines recovery.

**Remediation:** Separate signing, credential hashing, and encryption key domains. Add versioned encryption keys, explicit key lifecycle/rotation tooling, and a migration/revocation plan. Test rotation with queued work, stored results, and webhooks.

## GPU and production readiness gaps

These are validation/deployment gaps, distinct from the reproduced defects:

- **Actual NVIDIA execution is unverified.** The real GPU test was skipped. No assertion is made about VRAM fit, throughput, tokenizer agreement, vLLM image/flag compatibility, cancellation, OOM recovery, or provider billing accuracy.
- **Provisioning is not a complete startup controller.** The provider create payload supplies image and ownership metadata, but does not arrange vLLM and worker startup, enrollment, or readiness transitions. A prepared image/operator procedure is still necessary. The documented manually attached route is the current practical deployment path.
- **Financial limits are estimates.** Admission uses an operator-supplied hourly quote. Watchdog budget calculation includes only currently active rows, omitting prior terminated sessions from that watchdog's daily total; admission's calculation does include historical sessions. Provider invoices and egress/storage/startup charges are not reconciled. Do not describe the watchdog as a hard provider spend guarantee.
- **External integrations need sandbox validation.** Run real OIDC login/logout and key lifecycle tests, Stripe test-mode checkout/refund/dispute/reordered-event tests, callback TLS/egress tests, and provider inventory/create/delete contract tests. No real credentials or paid resources were used here.
- **Deployment hardening must be demonstrated.** Verify private PostgreSQL, narrowly scoped application/migration roles, least-privilege service secrets, non-root containers, TLS and ingress restrictions, restore-tested backups, alert delivery, retention enforcement, and documented recovery objectives. Missing evidence of an edge control is not proof that a live deployment lacks it.
- **Observability is insufficient as a launch gate.** Alert on request progress/lease age, stuck reservations, billing quarantine, scheduler cadence, callback backlog, provider instance discrepancies, and reversal liabilities. A zero-drift ledger and an HTTP/database readiness check do not establish a healthy execution pipeline.

## Existing strengths

The implementation has tenant-scoped API access, strict request schemas, wallet-first locking, idempotent submission, lease epochs and stale-finalization rejection, integer usage charges, unique ledger sources, billing quarantine, encrypted customer content, OIDC/PKCE and session CSRF checks, webhook signatures and public-address pinning, and disabled provisioning/test-only payment defaults. The passing tests provide useful evidence for those exercised paths. They do not cover the failure combinations above.

## Recommended release gates

1. Resolve IF-01 through IF-06 before allowing paid or untrusted traffic. Add regression tests that assert the safe behavior.
2. Resolve or explicitly mitigate IF-07 through IF-10 before a multi-tenant beta; validate ingress restrictions in the actual deployment.
3. With explicit expense approval, run a tightly capped NVIDIA end-to-end exercise: revision verification, concurrent tenants, worker restart, engine failure/OOM, lost finalization, deadline expiry, callback stalls, usage capture and reservation release.
4. Complete Stripe test-mode financial lifecycle validation and reconciliation of reversals/debt, followed by provider invoice and margin checks on the approved GPU exercise.
5. Demonstrate backup restoration and operational alerts, then publish an updated readiness statement based on measured evidence.

This is a targeted source and local-test audit, not a penetration test, infrastructure inspection, or certification.
