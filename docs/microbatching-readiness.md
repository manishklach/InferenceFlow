> Current evidence, October 27: [complete hosted A40 run](validation/2026-10-27/a40-hosted-1010-report.md): 1,010/1,010 real requests, repeated matched 100 arms, four active vLLM sequences, 500-request interruption/recovery, 1,010 verified receipts and zero wallet drift. Adaptive was 13.9% slower by mean server span. Cohort joint telemetry coverage was 100%; full-rental coverage remains incomplete and the itemized bill is pending. The pod is terminated. No public-beta, competitive-savings or production-readiness claim is supported.

> Updated audit: [October23 readiness](validation/2026-10-23/readiness-report.md) supersedes the older two-arm plan and prior test counts below. The current runner adds sequential mode and rejects public beta/Stripe.

# Multi-provider and continuous-batching readiness

The implementation/default audit below was prepared 2026-10-23, before paid validation. The October 27 evidence above supersedes its unverified-GPU statements. RunPod remains the only selectable execution adapter; optional Vast.ai/Lambda adapters are read-only. Wallet/rate/settlement algorithms remain unchanged; receipt metadata is additive.

## What is implemented, tested and enabled

Defaults were verified in `packages/common/config.py` and `.env.example`; the local `.env` explicitly selects mock execution and disables provisioning/Stripe, with v2/adaptive/calibration keys unset so their false defaults apply. Existing processes were not restarted; this is an on-disk configuration audit, not a claim about an independently deployed API. The protected operator report now returns nonsecret API configuration, and the scheduler emits its own startup configuration log so operators can check both processes after a restart.

| Feature | Implemented behavior | Test evidence | Default / local state |
|---|---|---|---|
| Durable queue, artifact affinity | PostgreSQL leases, tenant limits, exact model/tokenizer/mode matching | Database lifecycle, tenant, concurrency and stale-worker tests | Active in mock stack |
| Concurrent outbound execution | Worker creates asyncio tasks; each calls `/v1/chat/completions` without a serial model lock | Actual worker loop reaches four overlapping fake vLLM HTTP calls, then four finalizations | Enabled; worker hard cap defaults 16, approved 4090 overlay uses 4 |
| Continuous token batching | Delegated to vLLM; no prompt concatenation or Python batch buffer | Four active engine sequences observed in matched real A40 arms; baseline pooled output throughput 2.67x sequential | Enabled only in the bounded real experiment; local default remains mock |
| DeadlineEstimator | Conservative prefill+decode work, compatible backlog, warm slots, tenant cap, explicit calibration/source | Boundary/admission/uncalibrated rejection tests | V2 false; calibration false |
| DispatchPolicy | V2 ranking combines served/tier weight, bounded age bonus and urgency; legacy ranking retained | Weight/aging/urgency/fairness tests | Legacy ranking active until v2 true |
| AdaptiveDispatch | Fresh KV/running/waiting telemetry, cooldown, additive increase and halving on pressure, hard-cap fence | Controller/stale/malformed/KV/error/latency tests | False; independent of v2 flag |
| CapacityPlanner | Read-only recommendation, cold-start/load overhead, count/budget/session ceilings | No-spend/cold-start/cap tests plus four-slot sizing regression | Report computation only; never rents GPUs |
| Provider adapters | Existing Runpod REST v2; optional Vast/Lambda inventory and price discovery | Mocked deterministic contracts, auth/schema/timeout/rate-limit/price tests | Runpod sole execution selection; other mutations blocked |
| Exactly-once customer accounting | Unique usage per request, unique capture source, generation/epoch fencing and transactional locks | Stale/duplicate/concurrent finalizers, reserve concurrency, new interruption audit in fixed/adaptive modes | Existing behavior preserved; physical execution can repeat |
| Real GPU comparison | Gated 10/100/1,000 workload runner, raw telemetry, scoped read-only audit, offline matched comparison | CPU fixtures and mocked 1,000-request driver | Prepared, NOT executed |

The completed database suite and final counts are recorded under **Validation** below. Simulation results remain synthetic. Neither a passed HTTP-overlap test nor a `vllm` label in a fabricated test fixture proves GPU batching.

## Scheduling interaction and microbatching decision

1. API admission reserves credits after validation. With v2 enabled, DeadlineEstimator predicts a best-effort duration; strict admission rejects uncalibrated/unsafe estimates before a reservation. Accepted prediction snapshots and target timestamps remain immutable under idempotent retries.
2. On scheduler ticks, the same estimator supplies expected service duration to DispatchPolicy. Candidates must match immutable artifact identity. Ranking determines WHICH request is leased next, subject to tenant and worker limits.
3. AdaptiveDispatch separately determines HOW MANY request slots may be leased. It starts conservatively at two when telemetry is missing, uses a 30-second cooldown and new telemetry samples, increases by one when eligible demand/headroom exists, and halves for pressure/errors/latency regression. KV >=90% pauses dispatch even with adaptive disabled. Disabling v2 does not automatically disable adaptive: set both flags explicitly for comparisons.
4. The worker polls available slots and creates independent asynchronous HTTP calls. `WORKER_CAPACITY` now controls both registered hard capacity and its task limit, so the 4090 experiment's four slots match `--max-num-seqs 4` and tenant `MAX_INFLIGHT=4`.
5. vLLM alone forms token-level execution batches across the overlapping requests. It owns prefill/decode, sequence admission and KV allocation. Request overlap at the HTTP layer is necessary evidence, but actual engine sequence/counter observations are needed too.
6. CapacityPlanner runs as an operator-report side calculation, not a provisioning step on the dispatch path. It now uses the minimum compatible registered worker hard cap (or configured fallback), rather than assuming 16 slots for a four-sequence engine. This remains an uncalibrated homogeneous-capacity estimate, not a hardware sizing or financial guarantee.

**No additional application microbatch queue is necessary for this MVP's independent generation requests.** Continuous batching plus bounded concurrent dispatch is the appropriate foundation. A batching timer/size barrier would add queue latency and complicate cancellation, fairness and per-request accounting. Tune dispatch from real measurements first. Length-aware admission, token-budget control, model-specific profiles and heterogeneous capacity planning remain possible later improvements, not implemented performance claims.

The estimator's observed throughput divides tokens by summed request durations. Under overlap this is a per-request service-rate proxy, not aggregate GPU tokens/second; do not calibrate from the 24-hour dashboard average or advertise a deadline guarantee. Unknown calibration, startup and backlog estimates remain explicit. The planner treats one worker as one GPU in this experiment; multi-GPU workers need further accounting/design.

See the corrected [editable diagram](architecture/scheduler-v2.mmd).

## Instrumentation and evidence boundaries

Real-mode VllmInferenceEngine now tracks current/peak HTTP in-flight calls, integrated request-seconds, wall seconds with >1 concurrent HTTP call, lifetime completed/error counts and trace-write failures. Cancellation releases the in-flight slot in `finally`. These are process-local counters and reset on worker restart; they describe HTTP requests, not GPU kernels.

`WORKER_TRACE_PATH` enables a metadata-only JSONL trace, mirrored to stdout, with UTC/monotonic timestamps, hashed request ID, epoch, start/end, in-flight count, outcome, duration and token counts. It records no prompts, outputs, URLs or credentials. It is empty/off by default; the reviewed experiment overlay enables it under `/opt/experiment-evidence/worker-overlap.jsonl`.

Heartbeats transmit the new fields using optional validated Telemetry fields. Existing JSON storage handles them without a migration. The protected operator report includes fresh HTTP-overlap fields and provider instance ID; `/metrics` exports fresh per-worker overlap, engine running/waiting, KV, hardware GPU utilization and observed input/output throughput gauges. Missing/stale observations are omitted, not labeled zero. Existing queue-depth/age and tenant-scoped latency/attainment measures remain available.

The experiment collector samples raw vLLM Prometheus output and `nvidia-smi` at **one second** in the proposed launcher. This helps short workloads but still may miss brief active-sequence peaks. Use pre/post counter deltas, worker traces and sufficiently long controlled work together; insufficient observation is inconclusive. KV aliases cover the pinned version's known names; absent version-specific metrics remain missing. Rolling worker throughput is a bounded 60-second sample proxy, whereas cumulative engine counters and stage timestamps supply benchmark throughput.

Batching evidence requires: same pinned real engine/Pod, actual worker overlap >1, vLLM active-sequence/iteration evidence consistent with concurrent execution, and measured tokens/time. `iteration_tokens_total_sum/count` gives tokens per engine iteration where present; it mixes prefill/decode and is not by itself an exact decode batch size. GPU utilization is hardware sampling, not slot occupancy. A throughput gain alone does not prove batching efficiency or equivalent output quality.

## Optional providers and cost comparison

`packages/common/provider_discovery.py` implements the existing GpuProvider method surface for optional discovery adapters:

`RunpodDiscovery` also normalizes the existing provider's catalog and paginated inventory reads into the same Offer contract, with explicit Community/Secure tier selection and per-data-center availability filtering. It does not replace or enable the existing lifecycle adapter. Its discovery wrapper blocks paid mutations too; only separately approved existing Runpod lifecycle operations may act on infrastructure.

* Vast.ai: authenticated GET inventory/instance and POST `/api/v0/bundles` offer search. This POST is a read-only search per the official API. `dph_total` is preserved as the quoted rental component; disk/transfer/tax/billing coverage is not invented.
* Lambda: authenticated GET inventory/instance and `/api/v1/instance-types`, exact cents-to-integer-microUSD conversion, GPU count and regional availability. The quoted price is per INSTANCE, not per GPU.
* Both reject `create_instance` and `terminate_instance` before HTTP, regardless of credentials. A read-path allowlist also rejects mutation methods. Read failures are sanitized, redirects rejected, transient read/transport failures get at most one retry; auth/malformed catalog failures stop without fallback.

Pure capability discovery reports adapter capabilities separately from live stock or hardware compatibility. Only `active_provider('runpod')` is selectable; requesting Vast/Lambda for execution raises NotConfigured. There is no provider failover, routing-by-price, new provider secret, optional-provider API call or paid lifecycle integration activated by import/discovery.

`Offer` records provenance/time, GPU count, currency, rental/storage/other hourly components and billing increment. `compare_offers` excludes unavailable, stale/future, non-USD, multi-GPU, malformed and incomplete totals, then sorts complete comparable quotes deterministically with explicit tie-breakers. Unknown fees/storage are NOT zero. Its result is a recommendation only, never a rental instruction or a throughput-per-dollar claim. Optional live reads require separately supplied credentials; tests use synthetic fixtures, not current prices.

Runpod's existing auto-create adapter still lacks the full manually reviewed launch/placement setup. Keep `PROVISIONING_ENABLED=false`; use the reviewed manual payload only after approval. The existing provider watchdog remains supplemental, with its previously documented cost/availability limitations.

## First manually approved Runpod comparison: exact sequence

The [Community RTX 4090 runbook](rtx4090-community-experiment.md) remains the source for pinned model/image, 24 GB memory sizing, private connection, price snapshot, storage and complete cloud teardown. This comparison plan supersedes its earlier single-policy test sequence. Its last recorded Community read had no stock at the $0.34/hour catalog compute price; no fresh availability claim is made here. A fresh quote/placement check is mandatory before approval execution.

### A. Free preparation and approval gate

```bash
python -m unittest tests.test_provider_discovery tests.test_worker_overlap tests.test_gpu_experiment_tools tests.test_experiment_interruption tests.test_gpu_comparison -v
python -m scripts.prepare_gpu_payload
python -m scripts.gpu_experiment prepare --count 10 --run-id gpu-test-10 --output .runtime/comparison-plan/10.json
python -m scripts.gpu_experiment prepare --count 100 --run-id gpu-test-100 --output .runtime/comparison-plan/100.json
python -m scripts.gpu_experiment prepare --count 1000 --run-id gpu-test-1000 --output .runtime/comparison-plan/1000.json
```

Prepare an isolated CPU control plane with the CURRENT code and migration 0006, reviewed HTTPS connectivity, unchanged financial implementation, same pinned CPU tokenizer, experiment tenant funds via existing approved procedures, bootstrap/test/metrics credentials and independent provider read/delete supervisor. Do not give provider/DB/metrics secrets to the GPU. No CPU/cloud deployment was performed in this task.

Review the regenerated payload: it fetches the reviewed base worker SHA and embeds hashed current worker/config/collector/experiment-wrapper overlays, rather than silently fetching floating main. It uses the exact vLLM image digest, Community RTX 4090, one GPU, 80 GB ephemeral disk, empty public ports/mounts, model context 10,240, engine/worker cap4, and metadata-only tracing. Check `IF_SOURCE_HASHES` against source before approval. Unknown actual GPU driver/fit remains a post-rental canary gate, not a pre-rental hardware success claim.

If the recovery phase is explicitly approved, change only `EXPERIMENT_INTERRUPT_PREFIX` in the unrendered proposal to `gpu-test-recovery` before credential substitution. Otherwise leave it empty and report recovery untested on hardware. Never commit rendered secrets. The wrapper is dormant except for synthetic custom IDs matching that prefix, and its one-shot marker persists across process restart.

Request explicit authorization for the exact Community machine/DC, confirmed full hourly quote including disk/taxes, <=120-minute lifetime and **$10 maximum all-in**, the listed workloads and recovery injection, and complete deletion. Do not create before that answer. There is no verified automatic $10 Runpod cap. Independent shutdown must be configured before rental; no auto-top-up, new volume, optional provider or substitution is approved.

### B. After approval only: attach and prove readiness

1. Create ONE approved Pod via the reviewed configuration; do not use automatic provisioning or retry ambiguous create responses. Read it back and confirm actual GPU/type/cloud/DC, disk/mounts/ports, image, rate and provider creation time; terminate if mismatched. Arm the independent lifetime/cost supervisor against exactly that ID.
2. Record `gpu-attach` using the actual start/quote. Observe startup, pinned engine alias, long-context/cache headroom and successful canary. Require exactly one registered vLLM worker with `hard_limit=4` and the Pod ID. Do not accept test load on an unverified engine. Keep estimator calibration false.
3. Export worker/engine logs plus private metrics from the GPU. The loader receives `CONTROL_PLANE_URL`, tenant `INFERENCEFLOW_API_KEY` and separate `METRICS_TOKEN` through a secure CPU-side environment only. It requires the protected operator configuration endpoint; an old API without it is rejected.

### C. Compare the same corpus in six runs

Use the same warm model, decoding, engine cap4, tenant `MAX_INFLIGHT=4`, CPU configuration and arrival pattern. Every request explicitly gets `deadline_seconds=3600` even for the legacy baseline. Drain all work between runs. Keep the model alive; changing scheduler policy should not reload weights.

| Arm | SCHEDULER_V2_ENABLED | ADAPTIVE_DISPATCH_ENABLED | Meaning |
|---|---|---|---|
| baseline | false | false | Legacy ranking, fixed worker/tenant cap4 |
| adaptive | true | true | V2 ranking plus adaptive slots up to4 |
| optional diagnostic | true | false | Isolates v2 ranking from adaptive slots; NOT part of the default budget plan |

On the isolated CPU deployment, change only the two policy keys in the service environment file and restart **both API and scheduler**, retaining all secrets and other settings. For the repository Compose layout after approved CPU setup, `docker compose up -d --force-recreate api scheduler` reloads that file. These commands are instructions, not executed deployments. Check the scheduler's `scheduler_policy_configuration` startup log and compare it to the protected API configuration. The runner verifies API flags but cannot certify that a separate stale scheduler process was stopped; operator process/log verification is required. Save both pieces of evidence.

After each policy change execute the appropriate command (choose a new output directory for every run):

```bash
python -m scripts.gpu_experiment run --execute --policy baseline --count 10 --run-id gpu-test-base10 --timeout 300 --output .runtime/runpod-comparison/base10
python -m scripts.gpu_experiment run --execute --policy adaptive --count 10 --run-id gpu-test-adapt10 --timeout 300 --output .runtime/runpod-comparison/adapt10
python -m scripts.gpu_experiment run --execute --policy adaptive --count 100 --run-id gpu-test-adapt100 --timeout 600 --output .runtime/runpod-comparison/adapt100
python -m scripts.gpu_experiment run --execute --policy baseline --count 100 --run-id gpu-test-base100 --timeout 600 --output .runtime/runpod-comparison/base100
python -m scripts.gpu_experiment run --execute --policy baseline --count 1000 --run-id gpu-test-base1000 --timeout 2400 --output .runtime/runpod-comparison/base1000
python -m scripts.gpu_experiment run --execute --policy adaptive --count 1000 --run-id gpu-test-adapt1000 --timeout 2400 --output .runtime/runpod-comparison/adapt1000
```

These six runs total **2,220 requests**, plus canaries. Order alternates for the 100 tier to reduce simple warm-order bias; one pair is not a significance study. Observed adaptive initial limits/history are retained in operator reports; do not pretend every run begins with identical controller state. A ten-request stage may finish before any cooldown expansion and adaptive may be slower; report that result.

The timeout numbers are individual ceilings, not permission to exceed 120 minutes total: maintain a remaining-time ledger, reserve cleanup time, start each 1,000 tier only with >=45 minutes remaining, and skip a stage if the total budget/time cannot support it. An unfinished stage is censored/incomplete, not a successful deadline result. Do not double the rental or buy more capacity to complete a report. Optional third-arm or repeated comparisons require a revised approved plan within the ceiling.

### D. Exact timing, accounting and cost evidence

After EACH completed run, on the trusted CPU control plane using a DB account with read-only access:

```bash
python -m scripts.audit_gpu_run --run-directory .runtime/runpod-comparison/base10 --output .runtime/runpod-comparison/base10/audit.json
```

Repeat with that run's directory. This command explicitly starts a read-only SQL transaction. It scopes all accepted jobs to one tenant, reads per-request acceptance/dispatch/finalization times, reports successful-request p50/p95/p99 and successful-within-60-minutes / ALL accepted requests, validates terminal reservation conservation, one unique Usage/ledger capture source with exact tokens/charge, and checks global wallet reconciliation drift. Non-real/missing attempts or pending/mismatched billing fail the audit. No seed, `reconcile-request`, settlement, refund or wallet write is performed.

Record total paid uptime from provider create through confirmed deletion, including boot/download/idle/errors/canaries. Compare p95 successful latency together with failures and deadline attainment, not alone. Calculate batching speedup from matched actual output tokens/time; adaptive caps vary, so do not divide by a fabricated fixed concurrency. Review raw HTTP overlap and vLLM active sequences/counters separately.

After actual billing is available, `scripts.gpu_experiment report` reads saved results and ONE explicitly scoped provider cost/reference to produce cost per million actual successful input+output tokens. For each arm, use a documented non-overlapping stage allocation (including an explicit share of cold/idle/cleanup) and label it an estimate/allocation; a single whole-session invoice is not six separate actual stage invoices. Preserve whole-session cost separately, avoid double counting and never use customer capture as GPU cost. Missing costs remain unknown.

Finally run the offline comparison:

```bash
python -m scripts.compare_gpu_runs --directories .runtime/runpod-comparison/base10 .runtime/runpod-comparison/adapt10 .runtime/runpod-comparison/base100 .runtime/runpod-comparison/adapt100 .runtime/runpod-comparison/base1000 .runtime/runpod-comparison/adapt1000 --output .runtime/runpod-comparison/comparison.json
```

It requires all six real-mode passing audits, matched prompt/decoding hashes (custom IDs excluded), model revision and worker instances. It reports acceptance-to-last-terminal completion time separately from driver observation wall time, exact request p95, all-accepted deadline attainment, retries, customer capture separately, provider CPM/provenance or missing cost, and output-throughput ratio. It does not interpret the result as proof of batching, quality equivalence or an SLA.

### E. Approved worker interruption and recovery gate

If authorized and enough time/budget remains, return the CPU API/scheduler to adaptive mode and run:

```bash
python -m scripts.gpu_experiment run --execute --policy adaptive --count 100 --run-id gpu-test-recovery --timeout 600 --output .runtime/runpod-comparison/recovery
python -m scripts.audit_gpu_run --run-directory .runtime/runpod-comparison/recovery --output .runtime/runpod-comparison/recovery/audit.json
```

With the optional prefix enabled at creation, the experiment-only wrapper exits **after a real engine result but before finalization** on its fifth matching completion. The launcher restarts that worker once, preserving vLLM and the one-shot marker. Worker re-enrollment rotates generation/credentials, stale completion is fenced, abandoned leases recover and physical inference may repeat. This is **100 additional requests** (2,320 planned total), not a billing bypass. Require at least one abandoned/retried attempt, terminal results, unique Usage/capture counts equal accepted successes, zero drift/reservations, and no uncharged duplicate customer usage. Keep retry GPU time in provider costs. No marker/prefix means no injected failure; do not claim recovery was hardware-tested.

This fault mechanism is isolated to the experiment script; production worker execution/accounting is not patched to kill itself. Its threshold/prefix/one-shot behavior has CPU tests; actual process interruption and GPU recovery remain unexecuted.

### F. Shutdown, cleanup and report

Follow the Community runbook's complete teardown: stop admissions, drain/cancel via existing API, read-only reconciliation, export logs/artifacts, DELETE the exact experiment Pod, fresh GET not-found/list-absent verification, storage/billing inventory check, then record verified stop/invoice metadata and discard scoped credentials. At the time/spend cutoff, terminate even if evidence export is incomplete. Container exit is not provider termination. No persistent/network/global volume is requested; do not delete unrelated account resources.

Keep $10 all-in as the absolute authorized ceiling, warn/stop admissions at $7 estimated spend and terminate at $8 or 120 minutes, whichever comes first, leaving a buffer for billing delay/fees. No software policy is represented as a guaranteed provider hard cap. If the independent supervisor cannot be established, do not rent. Real Qwen/vLLM fit, CUDA startup, performance, batching and cost remain pending until this run produces artifacts.

## Validation

The initial Python 3.12/PostgreSQL run passed 97 tests; the final expanded suite passed **102 tests, one opt-in GPU skip**. It includes provider discovery contracts, actual worker-loop HTTP overlap, comparison-driver fixtures, interruption-wrapper/comparison-report tests and fixed/adaptive interruption/accounting audits. Earlier Windows-to-WSL forwarding became unreliable; the full successful run used Linux Python and a separate `inferenceflow_batching_test` database. No saved application DB URL or production schema was changed. No GPU test was enabled.

Ruff and mypy passed across 33 source files. After the final telemetry/configuration changes, 27 targeted scheduler/worker/recovery tests passed, and all 31 existing platform tests passed again with scheduler v2 enabled. Source-hash consistency, safe payload defaults, documentation links, Bash syntax and regenerated OpenAPI were checked. The same immutable model/image remain unvalidated on a GPU. Runpod/Vast/Lambda paid APIs were not called; optional-provider real account integration remains unverified. No dashboard UI or Sites deployment was changed in this task.

## Sources

[Vast official offer search](https://docs.vast.ai/api-reference/search/search-offers), [Lambda official API and authentication](https://docs.lambda.ai/api/cloud), [vLLM 0.8.5 metrics](https://docs.vllm.ai/en/v0.8.5/design/v1/metrics.html). Provider contracts were checked against these official schemas; mocked fixture prices are not live quotes.
