> Current readiness and approval gate: [2026-10-23 validation](validation/2026-10-23/readiness-report.md). That report supersedes older quotes, two-arm commands and beta-gate instructions below. No GPU or Site fix deployment is authorized yet.

# First GPU experiment: RTX 4090 Community Cloud

The [current microbatching readiness and baseline/adaptive comparison](microbatching-readiness.md) supersedes this document's earlier single-policy ordering and restart limitation. The shared payload now embeds hashed instrumented worker overlays, advertises a four-slot hard cap, samples at one second, and optionally supervises a one-shot synthetic-prefix interruption. Loader commands now require `--policy` and a CPU-only metrics credential to verify API flags. No provisioning or execution has occurred.

Status: **prepared, not provisioned; explicit final approval required**. This proposal supersedes the earlier Secure Cloud L40S proposal in `first-gpu-experiment.md`. It does not authorize resource creation, automatic provisioning, payment, or changes to customer wallet/billing behavior.

## Current provider response and cost

Runpod MCP `get-gpu-type` was called on 2026-10-23 around 11:54 UTC (04:54 PDT), GPU `NVIDIA GeForce RTX 4090`, `cloud=COMMUNITY`, `product=[POD]`, `count=1`, `minCudaVersion=12.8`. It returned:

```json
{
  "id": "NVIDIA GeForce RTX 4090",
  "memory": 24,
  "availability": "NONE",
  "price": {"community": 0.34, "secure": 0.89, "serverless": 1.1},
  "cudaVersions": [
    {"version": "12.8", "available": false},
    {"version": "12.9", "available": false},
    {"version": "13.0", "available": false},
    {"version": "13.2", "available": false},
    {"version": "13.4", "available": false}
  ]
}
```

This is a selected-field excerpt of the real response. There was no returned available data center. **Availability is currently a blocker.** No region is invented or silently substituted. The proposed payload leaves data-center selection unset; before any create, obtain a fresh Community/CUDA availability read, confirm the actual data center and placement filters, and record it in the approval. Secure Cloud or another GPU is not a fallback authorized by this proposal.

A second read at approximately 12:05 UTC (05:05 PDT) returned the same `NONE` availability and $0.34/hour Community catalog price.

Compute is quoted at **$0.34/hour**, not the Secure Cloud $0.89 rate. Runpod's current public docs quote container disk at **$0.10/GB/month**, billed per second. For the prepared 80 GB ephemeral disk:

| Component | Quoted rate / derived estimate |
|---|---:|
| GPU compute | $0.34/hour |
| Container disk | $8/month; ~$0.0109589/hour using 730 hours/month |
| Combined before applicable taxes/fees | **~$0.3509589/hour** |
| 120 minutes combined | **~$0.7019178** |
| Persistent/network/global volumes | None requested |

The monthly-to-hourly conversion is an explicit estimate, not a provider machine quote. Exact all-in hourly cost cannot be confirmed from the catalog alone while no machine is available: confirm the selected machine quote, storage proration and account tax/fees before approval execution. Capture the Pod `cost` field after creation and compare it to the approved quote; do not blindly add disk twice if that field already includes it. Invoice/billing rows establish actual cost. No paid CPU hosting, registry, backup, network volume, auto-pay or account top-up is authorized.

## Model, image and memory validation

The existing model/tokenizer SHA remains `1cfa9a7208912126459214e8b04321603b3df60c` for `Qwen/Qwen3-4B`. The exact revision's `config.json` resolves and identifies BF16 `Qwen3ForCausalLM`. The weight index reports 8,044,936,192 bytes (~7.49 GiB).

The image remains `vllm/vllm-openai@sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33`. A fresh Docker Registry read verified that v0.8.5's manifest hashes to this digest. The prior inspected image metadata reports Linux/amd64 and CUDA 12.4.0; vLLM 0.8.5 documents Qwen3 support. Host CUDA capability >=12.8 is a conservative placement filter, not an instruction to change the image's runtime. Runtime/driver/kernel compatibility is still untested on rented hardware.

BF16 KV bytes/token = 2(K,V) × 36 layers × 8 KV heads × 128 head dimension × 2 bytes = **147,456 bytes**. With 10,240 context tokens:

| Resident sequences | KV alone | Implication |
|---:|---:|---|
| 4 | 5.625 GiB | Weights + KV ~13.12 GiB before activations, allocator and graph overhead |
| 16 | 22.5 GiB | Cannot fit alongside weights in 24 GB |

Therefore the proposed launcher explicitly sets `--max-model-len 10240 --max-num-seqs 4 --gpu-memory-utilization 0.85 --dtype bfloat16`, disables prefix caching, and uses `--generation-config vllm`. The CPU control plane uses `MAX_INFLIGHT=4`, adaptive dispatch off, and a single isolated experiment tenant. The worker now advertises four hard slots in the experiment overlay; the experiment tenant cap and the engine's four-sequence cap are intentional independent limits. Default worker capacity remains 16; the inert experiment overlay selects four.

**This is a defensible sizing estimate, not confirmation of actual fit.** Before accepting load, inspect vLLM's available KV blocks and maximum resident tokens, CUDA graphs/activation allocations, then generate a long-context canary. Check that four resident 10,240-token contexts fit the measured cache; if not, stop and revise the configuration rather than claim support. The initial prepared synthetic corpus is much shorter; A CPU-only check of all 1,000 prepared prompts using the pinned tokenizer measured 237–863 input tokens and at most 1,119 input+reserved-output tokens. This is tokenization, not GPU execution. Do not silently reduce context limits while the API advertises 10,240. Do not increase to eight/sixteen resident sequences on this card without a revised memory test and approval.

The worker checks the revision-derived alias and generates a canary before registration. API model/tokenizer identity is checked again by the new load tool. The tokenizer and worker both set thinking off; input/output usage is returned by vLLM and checked by the existing settlement path. No quantization, model revision, rate or wallet behavior is changed.

## Prepared files and execution boundaries

* [`infra/first-gpu/runpod-pod.proposed.json`](../infra/first-gpu/runpod-pod.proposed.json): inert v2 create body, one Community RTX 4090, 80 GB container disk, no mounts/public ports, CUDA floor and conservative CPU/RAM placement filters.
* [`infra/first-gpu/launch.sh`](../infra/first-gpu/launch.sh): sibling loopback-only vLLM and outbound worker processes. It is not Docker-in-Docker. Failure exits clean up local processes; **they do not terminate the paid Pod**.
* [`scripts/prepare_gpu_payload.py`](../scripts/prepare_gpu_payload.py): rebuilds the proposed JSON locally, including the exact reviewed telemetry script and launcher text. It never calls Runpod.
* [`scripts/gpu_experiment.py`](../scripts/gpu_experiment.py): `prepare` writes synthetic inputs without any API; `run`/`collect` require an explicit `--execute` flag. It contains no provider-create operation.
* [`infra/first-gpu/control-plane.env.example`](../infra/first-gpu/control-plane.env.example): configuration overlay only, not an applied `.env`. `PROVISIONING_ENABLED=false`, `STRIPE_ENABLED=false`, v2 on, adaptive off, `ESTIMATOR_CALIBRATED=false`, max one GPU and max 120-minute session. Existing application budgets are supplemental and omit storage/tax.

The bootstrap clones the reviewed existing worker source SHA `c62386b2b6347f2555375fbd448d14769d852646`, installs locked dependencies in a separate worker virtualenv and includes the experiment collector literally. It does not replace vLLM's own dependencies. The CPU API needs `.[gpu]` and the same tokenizer SHA; migration 0006 must already be present on an isolated experiment database. No database migration or service deployment is performed by preparing these files.

A reachable private HTTPS control-plane URL, strong separate experiment bootstrap credential and funded test-tenant API key are prerequisites; the current placeholders are deliberate blockers. Never commit a rendered payload containing credentials. The GPU receives no DB/Stripe/provider secrets. Sites remains a separate static showcase; no inference control plane is assumed to exist there. Community hosts are a different trust tier: use synthetic prompts and expendable credentials only.

## Tests: prepared now, execute only after approval

Offline preparation commands are safe to run before renting:

```bash
python -m scripts.prepare_gpu_payload
python -m scripts.gpu_experiment prepare --count 10 --run-id smoke --output .runtime/gpu-plan/10.json
python -m scripts.gpu_experiment prepare --count 100 --run-id curve --output .runtime/gpu-plan/100.json
python -m scripts.gpu_experiment prepare --count 1000 --run-id load --output .runtime/gpu-plan/1000.json
python -m unittest tests.test_gpu_experiment_tools -v
```

`prepare` refuses to overwrite an existing file; choose a new artifact path/run ID for a new experiment. All inputs are unique synthetic logistics notes with an 80% short / 20% medium mix, max output 128/256 tokens, temperature 0 and top_p 1. Real input lengths are measured with the pinned tokenizer, not a character-count token estimate. The load tool sends each API job at most 100 requests, persists submission intents with stable idempotency keys before POST, polls jobs/performance, paginates results and journal, reads wallet snapshots, validates non-MOCK positive usage and ordered unique custom IDs, and writes JSON/JSONL reports. It never seeds funds, changes rates, tops up, refunds or invokes reconciliation writes.

After explicit approval and proven GPU/worker readiness, commands on the CPU driver are:

```bash
# Credentials must already be in the environment through a secure channel.
# CONTROL_PLANE_URL must be approved HTTPS; INFERENCEFLOW_API_KEY is the test tenant key.
python -m scripts.gpu_experiment run --execute --count 10 --run-id smoke-001 --timeout 600 --output .runtime/gpu-run/smoke-001
python -m scripts.gpu_experiment run --execute --count 100 --run-id cap1-001 --timeout 600 --output .runtime/gpu-run/cap1-001
python -m scripts.gpu_experiment run --execute --count 100 --run-id cap2-001 --timeout 600 --output .runtime/gpu-run/cap2-001
python -m scripts.gpu_experiment run --execute --count 100 --run-id cap4-001 --timeout 600 --output .runtime/gpu-run/cap4-001
python -m scripts.gpu_experiment run --execute --count 1000 --run-id load-001 --timeout 3600 --output .runtime/gpu-run/load-001
```

Between the three 100-request runs, drain outstanding work, change only the experiment scheduler's `MAX_INFLIGHT` to 1, 2 and 4 respectively and restart that isolated scheduler so the setting takes effect. Keep the engine's sequence cap at four and all prompt/model/decoding settings identical; changing the scheduler cap changes dispatch concurrency without restarting the model. The 10-request smoke uses cap1. For the 1,000 tier choose the safest measured cap <=4. The same 100 corpus is replayed with distinct request/idempotency IDs; unique IDs are outside model text, so these three inputs are matched. This is **1,310 planned requests**, plus readiness/context canaries and any separately run GPU test, all within the same approved $10/session ceiling.

Do not start 1,000 requests unless >=65 minutes remain before the provider lifetime cutoff and earlier stages passed. Stop on identity, usage mismatch, tenant leakage, OOM, high KV pressure (>=90%), unexplained errors or an unavailable cost/termination control. Abort initialization after 15 minutes. The 100-tier comparisons share a 25-minute cap; skip later phases rather than overrun the total 120 minutes. A load-tool timeout is not cloud termination and may leave jobs queued: stop admissions/cancel as needed and use the independent provider shutdown path. Do not automatically replay an ambiguous submission under a new ID; recover the persisted intent first.

The existing opt-in `tests/test_gpu.py` is separate and has pytest fixtures that truncate a `_test` DB. Do not point that fixture DB at the running experiment API's database. Use the standalone load runner for these tiers. The first run does not include a forced worker/Pod restart or adaptive replay; those require an additional reviewed fault-injection procedure and matched workload within the budget. A burst completed within an hour is not proof of a production SLA.

## Logging and calculations

The launcher starts private collection every second using `python -m scripts.gpu_experiment collect --execute`. It writes `/opt/experiment-evidence/engine.jsonl` and mirrors records into Runpod container stdout. Records contain UTC observation time, raw loopback `/metrics` Prometheus samples, and `nvidia-smi` CSV (GPU utilization, memory utilization/used/total and power). Missing metrics are logged as missing/error types, never zeros. No prompt or credential is added by this collector.

The CPU driver writes `observations.jsonl` (submission intents, accepted jobs, rate-aware polls (five seconds for one job, eleven seconds for ten) and tenant performance, wallet/journal reads), `workload.json`, `jobs.json`, `results.json`, and `summary.json`. Engine readiness canaries and initialization remain in paid-uptime cost. Provider logs are a secondary export channel, not a guaranteed permanent artifact store: confirm retrieval before deleting ephemeral disk.

| Measure | Calculation and evidence |
|---|---|
| Throughput | Successful requests / stage wall seconds; actual input tokens and output tokens / stage wall seconds separately. Report warm-stage and total-paid-uptime rates separately. |
| Queue latency | Retain tenant `queue_wait_seconds` and `submission_to_dispatch_seconds` p50/p95/p99 from `/v1/performance`; isolate the tenant/window. These are aggregate observations, not per-request timings. Export the attempt/work timestamps read-only for exact per-request analysis. |
| GPU utilization | Time-weight hardware samples, report mean/p95 and missing coverage; distinguish request-slot occupancy from actual NVIDIA utilization. |
| Batching | Compare matched 100-request output token rates at caps1/2/4: speedup=T(c)/T(1), normalized efficiency=speedup/c. Retain vLLM running/waiting/KV/preemption counters and iteration-token histogram deltas when present; tokens/engine-iteration is not automatically a pure decode batch size. |
| Completion within 60 min | Successful jobs within 3,600 seconds / ALL accepted jobs. Runner also reports a conservative request lower bound based on whole-job completion. Results API omits per-request times; use read-only DB attempt export for exact request attainment. Report unfinished/failed/rejected work and cutoff explicitly. |
| Cost per million tokens | Provider session cost (compute + disk + tax/fees, all startup/idle/failure time) ×1,000,000 / actual successful input+output tokens. Also report input/output volumes separately. Engine counters capture retries/waste; customer captures are not provider costs. |

The optional runner `--cost-usd` accepts an explicitly labeled operator-supplied cost with matching coverage; do not enter the customer charge there. Final invoice is only known afterward. Recompute final session CPM from the retained results and cumulative provider bill; do not sum stage estimates and then add the same whole-session invoice again. Costs/metrics are experimental artifacts outside the immutable financial implementation.

An offline `report` command accepts all stage directories and ONE cumulative session cost. For example, after the invoice is available, use `python -m scripts.gpu_experiment report --directories .runtime/gpu-run/smoke-001 .runtime/gpu-run/cap1-001 .runtime/gpu-run/cap2-001 .runtime/gpu-run/cap4-001 .runtime/gpu-run/load-001 --cost-usd ACTUAL_TOTAL --cost-kind actual_invoice --cost-reference INVOICE_AND_COVERAGE --output .runtime/gpu-run/session-cost.json`. This reads saved files, refuses duplicate job coverage, never reruns inference and never writes the customer ledger. Include the whole session's startup/idle/disk/tax/canary costs in ACTUAL_TOTAL; the denominator is successful workload tokens, so that overhead is not hidden.

Read-only pre/post `python -m packages.common.cli reconcile` may verify zero drift; it does not authorize `reconcile-request`, seed, refund or any write. Inspect terminal reservations and captures using existing read paths. Never change billing code/rates to make an experiment pass.

## Budget, shutdown and cleanup

Maximum authorized in any future approval: **$10 all-in**, not automatically enforced by Runpod. Proposed runtime cap: 120 minutes from provider creation, including boot/install/download/warm-up/idle/cleanup. With the current rate estimate, the planned two-hour rental is about $0.70 before applicable taxes/fees; leave the rest unused.

Before creation, prepare an independent, reliably running supervisor outside the GPU Pod with securely supplied provider read/delete capability. It must bind to the exact experiment ID after create, verify the read-back name/config, track actual creation time, poll provider status/cost/billing at least every minute and retain a conservative elapsed-time estimate including storage/tax. Stop admissions at $7 estimate, terminate at $8 or 120 minutes (earliest), and reserve $2 for lag/rounding/cleanup. Reconcile quote/actual discrepancies immediately; terminate on unexpected rates/fees. Confirm the supervisor is armed before load begins, and monitor boot manually until it is attached. No CLI API key is assumed from MCP OAuth: securely establish the supervisor's credentials first. Do not provision if that independent path cannot be established.

The existing platform watchdog is only supplemental: it omits storage/tax and requires tracked attachment. Container exit, shutdown scripts inside the container and a crashed CPU dashboard do not enforce a cloud-spending cap. API outage, billing lag or supervisor failure can defeat software limits; no unconditional $10 provider hard-cap guarantee is claimed. Do not enable account auto-top-up or purchase additional credits without separate approval.

At completion or any failure:

1. Stop new submissions. Drain or explicitly cancel experiment jobs with the existing API; retain all accepted IDs. Check ledger drift via read-only reconciliation.
2. Export CPU reports, private engine samples, startup/worker/provider logs and billing evidence BEFORE stop/delete; ephemeral disk is wiped on stop/restart. If the budget cutoff is reached, terminate immediately even if evidence export is incomplete.
3. Through the Runpod integration, DELETE only the newly created experiment Pod by its recorded ID (`DELETE https://api.runpod.io/v2/pods/POD_ID`). To stop compute immediately in an emergency, use `POST /v2/pods/POD_ID/action` with `{"action":"stop"}`, then DELETE. Never leave it merely stopped.
4. Fresh GET must return not found and list must omit the ID. Check billing/storage inventory for experiment-owned retained resources and final charges. No persistent/network/global volume was requested; do not delete unrelated resources.
5. Only after verified termination, record metadata with existing `gpu-record-stop` and import the actual cumulative invoice with `gpu-invoice` (provider ID, reference and coverage). Those commands do not terminate the provider and do not alter customer wallets. Revoke/discard the experiment bootstrap/test credentials via the existing credential procedures.
6. Record actual spend, all-accepted completion, throughput, queue/batching metrics, failures/missing data and any uncompleted stage. Keep estimator calibration false until separately approved evidence supports it.

## Approval checkpoint

**No Pod or paid resource has been created.** Before requesting an actionable final create approval, require: fresh Community availability and actual placement, a confirmed compute+disk/tax cost within the ceiling, verified private CPU API routing/credentials, measured engine-startup validation gates, and a ready independent teardown supervisor. The remaining memory/kernel check necessarily occurs after an approved small rental, before load admission; failure means terminate, not expand spending.

The approval question is: authorize **one Community RTX 4090 24 GB**, on-demand at compute <=$0.34/hour plus explicitly confirmed 80 GB ephemeral storage/tax/fees, no retained volumes/public ports, <=120 minutes, <=$10 all-in, the pinned Qwen3-4B/vLLM experiment at concurrency <=4, the stated synthetic tests, and complete deletion afterward? No substitution or overrun is included. **Wait for the user's explicit answer; an earlier 'proceed' requesting preparation is not this final approval.**

## Preparation verification

Eight CPU-only unittest checks passed, including a full 1,000-request driver run against an in-process mocked API (ten 100-request POSTs), execution gates, mock-mode rejection, missing telemetry and failure-aware denominators. Ruff and Bash syntax checks passed. The 10/100/1,000 workload artifacts were generated under ignored `.runtime/gpu-plan/`; no inference API or cloud create call was made. The runner respects the existing 120-requests/minute tenant limit rather than changing that application setting. The old Windows-to-WSL DB test connectivity issue was not used or bypassed by these isolated CPU checks; real stack tests remain pending.

## Sources

[Runpod Pod/storage pricing](https://docs.runpod.io/pods/pricing), [storage persistence](https://docs.runpod.io/pods/storage/types), [live v2 API schema](https://api.runpod.io/v2/openapi.json), [pinned model config](https://huggingface.co/Qwen/Qwen3-4B/blob/1cfa9a7208912126459214e8b04321603b3df60c/config.json), [vLLM 0.8.5 models](https://docs.vllm.ai/en/v0.8.5/models/supported_models.html). Stock/compute quote came from the Community-scoped Runpod MCP read described above; model/image checks used official Hugging Face and Docker Registry reads. No live GPU inference has occurred.
