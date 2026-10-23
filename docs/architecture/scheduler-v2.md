> October23 verification: see [current readiness package](../validation/2026-10-23/readiness-report.md). No real GPU or public alpha validation is claimed.

# Scheduler v2: best-effort sub-hour inference

See the [current readiness review](../microbatching-readiness.md) for exact implementation/default/test state, HTTP-overlap versus GPU-batching evidence, optional read-only provider contracts and the manually approved Runpod comparison. The [editable diagram](scheduler-v2.mmd) now shows CapacityPlanner as an operator-report side calculation rather than an automatic dispatch-to-provisioning step. Planner slot assumptions follow registered/configured hard capacity, including the four-sequence 4090 experiment; hardware calibration remains false.

## Gap analysis and baseline

Baseline: v0.2.0, main commit `76551f4`. Before changes: **56 passed, one real-GPU test skipped**, Ruff and mypy passed. The baseline uses PostgreSQL, wallet-first locking, bounded SKIP LOCKED tenant scans, per-request fencing epochs, worker generations, exact artifact affinity, fairness/aging, backoff, and immutable financial settlement. These remain in place.

| Existing capability | v0.3 addition |
|---|---|
| Explicit tier targets, unstarted expiration | Configurable 3,600s v2 default, acceptance estimates and strict admission option |
| Weighted fairness and aging | Bounded deadline urgency and bounded age bonus, preserving served counters and tenant caps |
| 16-slot warm workers and KV pressure stop | Optional adaptive slots, cooldowns, stale-data fallback, error/latency feedback |
| Worker telemetry | Observation timestamps, per-attempt execution records, sampled active/idle coverage |
| Provider kill switch and watchdog | Pure capacity recommendations with startup/billing-increment/cap inputs |
| Quoted provider uptime costs | Cost profiles, invoice coverage/reference, token revenue and unit economics |
| Queue/financial metrics and dashboard | Tenant performance, separately authenticated operator economics/capacity view |
| Mock correctness tests | Reproducible offline scheduler comparisons and new regression tests |

No queue replacement, custom token batcher, Redis, Kubernetes, automatic provisioning, customer repricing, or model hot-swapping is introduced. vLLM owns token-level continuous batching.

## Flags and rollback

`SCHEDULER_V2_ENABLED=false` and `ADAPTIVE_DISPATCH_ENABLED=false` are defaults. Enable v2 to use the new default target, admission estimator, and dispatch policy. Enable adaptive dispatch separately to tune slots. `DEFAULT_COMPLETION_TARGET_SECONDS=3600` applies to newly accepted v2 jobs in either tier; explicit `deadline_seconds` still wins. Existing jobs keep their original target and immutable rates. Disabling both flags restores the legacy dispatch/default-target behavior without reverting additive migration 0006. Restart API/scheduler/worker together when upgrading; do not downgrade financial schema with live data.

`PROVISIONING_ENABLED=false` and `STRIPE_ENABLED=false` remain unchanged. The planner has **no provider client** and no execution method. Its recommendations never create or stop instances, even if provisioning is separately enabled. The existing independent, deliberately configured provider watchdog retains its safety role.

## Acceptance and DeadlineEstimator

Successful acceptance is the committed job creation and reservation; `created_at` is assigned within that transaction. The objective ends at the latest terminal request completion. Successful attainment requires **all requests succeeded**. Partial success, failure, cancellation, expiration, and billing quarantine do not count as successful deadline attainment. A running request may finish after target; unstarted queued/leased work expires at `target <= now` and releases credits.

For each request, conservative slot time is `(input/input_rate + max_output/output_rate) × uncertainty_margin`. Default hypothetical rates are 100 input and 20 output tokens/s, margin 1.5. When at least 20 successful observations exist for the same artifact and current worker IDs within 24h, observed rates replace defaults. Input and output rates both divide by complete attempt duration: their sum deliberately double-counts shared service time and is conservative, not a prefill/decode profiler.

Prediction adds backlog slot-seconds / usable warm slots to the larger of the longest new request and new slot-seconds / allowed parallelism. Parallelism respects the tenant cap. All queued/leased/running/quarantined compatible work is conservatively counted at full maximum size. Retry backoff, residual running time, arrival uncertainty and heterogeneous devices are not precisely modeled. No warm capacity means unknown completion time and risk, never an invented guarantee.

Estimates remain uncalibrated unless `ESTIMATOR_CALIBRATED=true`, sufficient observations exist, and execution mode is vLLM. This switch is an **operator assertion after load testing**, not an automatic conclusion. Reset it whenever GPU hardware, worker IDs, model/tokenizer, engine configuration, or workload distribution changes. Mock observations never become real-GPU calibration. Cold-start/model-load assumptions are reported separately and used by the planner; unapproved future GPUs cannot justify confident admission.

`admission_policy=best_effort` is the backward-compatible default. Responses persist an immutable prediction snapshot, source, calibration status, reasons and best-effort outcome. `reject_if_at_risk` returns actionable HTTP 503 if capacity is missing, estimated time exceeds target, or estimates are uncalibrated. Rejection precedes reservation. A global admission advisory lock serializes estimates with concurrent accepts; wallet locks remain tenant-local. This trades admission throughput for understandable initial backlog estimates. Strict admission still does not offer an SLA. Legacy default-policy idempotency fingerprints are preserved.

## DispatchPolicy and fairness

Workers must pass the existing exact repo/revision/tokenizer/mode match, freshness and credential checks. Available capacity dispatches on the next one-second scheduler tick; the 60-minute target is never a batching delay.

The v2 score is `served/weight − min(age_minutes, 3) − urgency`, followed by target slack and request ordinal. Standard weight is 4; economy weight is 1 until five-minute aging promotes it to 4. Urgency rises from 0 to at most 2 as slack falls below estimated service time. Both urgency and age bonuses are bounded so an old large batch cannot monopolize dispatch indefinitely. Five-minute served counters, tenant in-flight limits, and wallet scan rotation remain. Fairness is request-count weighted, not token-cost fair queuing; skewed workload sizes need real-load validation.

## Adaptive dispatch

Hard worker capacity stays at most 16; tenant in-flight limits remain independent. Fresh KV/cache and engine running/waiting counts are required to expand. Initial/fallback limit is two slots, bounded by the worker hard cap. Every 30 seconds, a fresh uncongested sample with demand can add one slot. KV >=80%, engine waiting above `max(2, limit)`, recent error rate >10%, or latency ratio >1.5 can halve the limit after cooldown. At >=90% KV usage dispatch pauses immediately, including when that last critical sample becomes stale. Existing work is not preempted.

Missing, malformed, inconsistent, future-dated or >45s-old telemetry falls back conservatively; it cannot increase concurrency. New registration clears telemetry/controller state. The engine reports a bounded 128-attempt/60s error and token window; latency ratio compares medians of the last two groups of eight. Rates are separate input/output wall-clock observations. Metrics names are read from vLLM's private endpoint, using the existing aliases; validate their presence for the pinned engine. [Official vLLM metric reference](https://docs.vllm.ai/en/stable/design/metrics/).

## CapacityPlanner

The pure planner divides conservative backlog slot-seconds by available target time minus startup/model-loading assumptions and 16 slots per hypothetical GPU. It reports required versus warm capacity, recommended additions bounded by GPU-count and daily quoted-spend/session limits, and idle shutdown recommendations when backlog is empty. Pending creation intents and untracked warm workers count toward the GPU ceiling. GPU startup arriving after target is explicitly blocked. Billing increments round costs upward. Planning is deliberately single-model and conservative; it does not optimize heterogeneous GPUs or provider price markets.

## Measurements and privacy

`GET /v1/performance` is tenant scoped. It reports requests queued, oldest age, pending/risky jobs, successful attainment, separate unsuccessful terminal counts, p50/p95/p99, dispatch delay, queue wait and execution time. Window: jobs accepted in the last 24h plus older active jobs. Successful latency ends when all requests finish; attempt duration includes failed/retried executions separately. Wall-clock tokens/s uses the last 24h, not summed concurrent execution seconds.

Prediction accuracy compares persisted acceptance predictions with successful actual outcomes (risk/hit confusion counts and mean absolute latency error). This survivor-only comparison excludes failed jobs; unsuccessful terminal jobs are separately visible and must be included in experiment conclusions.

`GET /internal/scheduling/report` requires the separate metrics bearer credential. Tenant sessions/keys cannot retrieve platform economics, provider IDs or other customers' data. The dashboard's operator panel forwards a user-supplied credential to this single read-only target, never injecting server secrets or persisting it. `python -m packages.common.cli scheduling-report` provides the same report to trusted operators. Prometheus metrics remain authenticated. Historical modes are listed explicitly in reports; mock byte-based token units are not comparable to tokenizer/GPU throughput.

## Recovery and limits

Attempt records are operational, not billing sources. Fenced finalize, wallet settlement, unique usage, retries and immutable ledger semantics are unchanged. Attempt observations commit with successful settlement, record transient errors and lease loss, and do not permit stale completions. Unknown heartbeat intervals are not idle time. A missing invoice or cost attribution stays unknown. Planner estimates, sampled activity and provider invoices are distinct.

Remaining limits: estimator accuracy/calibration under unmeasured GPU load; one curated model; bounded per-tenant fairness; no automatic scaling; no invoice API ingestion; no formal SLA. Validate actual deadline reliability and economics with approved hardware before enabling v2 for customer promises.
