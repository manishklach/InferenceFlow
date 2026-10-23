# InferenceFlow readiness decision — October 23, 2026

**NOT READY — BLOCKERS REMAIN.** No billable capacity was created, no GPU inference run, no live payments enabled, no backend deployed, and no website fix published in this task.

1. Community RTX 4090 stock is NONE in the latest RunPod read (2026-10-23 18:53:03 UTC / 11:53 PDT). $0.34/hour is a catalog compute price, not a reservable complete quote.
2. Configured control plane is http://localhost:8080, not reachable private staging HTTPS. Worker auth/queue/results/accounting pass locally; remote routing/TLS/OIDC and a GPU registration are unverified. The ChatGPT Site is a separate static showcase.
3. Exact placement, all-in tax/ancillary cost and independent supervisor credentials/read-delete recovery remain unverified. The $10 intention is not a provider-enforced cap.
4. Actual CUDA startup, memory headroom, long-context concurrency, engine metrics and interruption recovery require a separately approved rental. No benchmark or cost advantage can be claimed before then.

## A. Website

See [website report, evidence, issue table and eight screenshots](website-report.md). All three LIVE pages were accessed in-browser; navigation/back links, both SVGs and no mobile page overflow verified. Linked internal assets returned 200, warn/error logs empty in tested window. Missing homepage canonical, poor small-label contrast, unversioned test count and prototype copy were corrected LOCALLY. Static content/link/fragment/metadata checks and desktop/mobile regression passed. Publication requires your confirmation under Phase 1.5; existing owner-private audience is preserved. The current live Site still has the listed original issues.

## B. Scheduling and microbatching audit

| Component / exact file | Implemented and tests | Default enablement | Limitations / GPU status |
|---|---|---|---|
| Queue/fairness/model affinity, packages/common/service.py | Durable per-request PostgreSQL leases, tenant caps, exact artifact identity; lifecycle, concurrent/tenant/recovery tests | Active in local mock pipeline | Physical execution can repeat; no real GPU |
| DeadlineEstimator, packages/common/scheduling.py | Prefill+decode estimate, backlog, warm slots, calibrated/source flags; tests/test_scheduler_v2.py boundaries and strict rejection | SCHEDULER_V2_ENABLED=false, ESTIMATOR_CALIBRATED=false | Observed per-request service-rate proxy; not aggregate GPU throughput; no SLA |
| DispatchPolicy, same file | Weighted fairness, bounded urgency/aging, affinity; ranking/starvation tests | Legacy policy active; v2 disabled | Estimates depend on uncalibrated profiles |
| AdaptiveDispatch, same file | Two initial slots on missing telemetry, +1/halve, 30-second cooldown, KV pressure stop; stale/error/pressure tests | ADAPTIVE_DISPATCH_ENABLED=false independently of v2 | GPU utilization is an optional input; backlog is boolean demand; deadline risk affects ranking, not a direct adaptive slot formula; no calibrated token-budget control |
| CapacityPlanner, same file | Cold-start, max-GPU and spend/session recommendations, respects four-slot hard capacity; cap/no-spend tests | Recommendation only; PROVISIONING_ENABLED=false | Homogeneous worker approximation, no automatic provider routing, compute-only platform budget omits disk/tax |
| Admission, same file + apps/api/main.py | Best-effort prediction; strict mode rejects unsafe or uncalibrated estimates before reserve; idempotent prediction snapshot | V2 off | No guaranteed admission SLA; best effort may miss target |
| Worker, apps/worker/main.py + engines.py | Independent asyncio HTTP calls; tests/test_worker_overlap.py proves four overlapping fake-engine requests | Mock mode; hard cap default16, proposed experiment4 | HTTP overlap is NOT evidence of GPU batching |
| vLLM continuous batching | Engine owns active sequences, token scheduling, KV cache and GPU execution | Real adapter dormant | Real engine/GPU untested; no additional application microbatch buffer is justified yet |
| Rollback, config.py + service.py | Turn BOTH v2/adaptive flags off; restart API/scheduler, inspect protected configuration and scheduler startup log | Legacy defaults retained | KV>=90% safety pause remains even fixed; process-log check required, API report alone cannot certify separate scheduler |
| Customer accounting, service.py | Unique Usage/capture sources, transactional locks, epoch/generation fencing; test_batching_recovery.py interruption and audit | Existing implementation unchanged | Exactly-once accepted accounting, not exactly-once physical GPU execution; hardware recovery pending |

Layer A is InferenceFlow queueing/fairness/affinity/deadlines/dispatch/capacity/provider orchestration. Layer B is vLLM continuous sequence execution/token scheduling/KV/model kernels. Layer C is adaptive dispatch feedback from demand and fresh telemetry. Layer C is implemented and simulated, disabled by default, and has no proven economics advantage. Capacity planning is not on a paid-provisioning path. No second microbatch queue was added.

### Actual measurement map

- Active/waiting sequences: vllm:num_requests_running / num_requests_waiting, exported through fresh worker heartbeat gauges. Missing stays missing.
- Prompt/output rates: deltas of vllm:prompt_tokens_total / generation_tokens_total divided by observed wall interval. Worker rolling 60-second gauges are proxies, not equivalent aggregate engine throughput. Counter resets must split windows.
- Dispatches/sec: rate of inferenceflow_dispatched_attempts (DB-derived cumulative gauge); retries included. Deletions/test resets invalidate rate windows.
- Hardware utilization/memory: nvidia-smi utilization.gpu,memory.used,memory.total; fractional utilization and MiB heartbeats, plus raw private collector samples every second.
- KV: v0.8.5 gpu_cache_usage_perc and kv_cache_usage_perc alias when present. No missing alias becomes zero.
- HTTP overlap/idle: in-flight, peak, integrated request-seconds, seconds with >1 request, idle seconds. Process restart resets; idle is no HTTP work, not GPU zero kernel use.
- Queue latency/end-to-end/deadline: per-request immutable acceptance/first-dispatch/completion timestamps in read-only audit; p50/p95/p99 successful latency and successes within target / ALL accepted.
- Engine iteration batching efficiency: retain raw histogram/counters if actually exposed; no iteration-token metric is guaranteed by the pinned docs. Tokens per iteration can mix prefill/decode; not an invented decode batch size. Compare fixed-cap1 vs fixed-cap4 speedup and speedup/4 separately from adaptive caps.
- Cost/completed workload: complete provider session cost including startup, idle, retries, disk/ancillary divided by successful work; never customer capture as infrastructure cost.

Metrics/operator report require separate operator authentication. No prompt, result, credential or URL is emitted by the optional request trace. Tenant APIs retain tenant predicates. No metrics label contains customer content. Telemetry is optional validated numeric metadata; no schema migration is needed. GPU observations are not yet available.

## C. Provider readiness

[Provider architecture and verified API sources](../../architecture/providers.md). RunPod remains sole selectable execution adapter. Existing create gate stays off; first experiment uses manually reviewed payload, not automatic create. Vast/Lambda provide authenticated read-only catalog/inventory and normalized states/hardware where supplied, sanitized bounded read retries, and blocked create/terminate interface stubs. They cannot be selected for execution or failover. No live Vast/Lambda credentials were requested or used. Unit tests use httpx.MockTransport.

compare_offers accepts only complete fresh one-GPU USD quotes; unknown storage/fees/billing increments exclude an offer. provider_selection.compare_workload adds model compatibility, measured-or-explicit-synthetic input/output throughput, startup latency, availability, reliability/retry allowance and deadline slack. It ranks expected full workload cost, not headline hourly rate. This module is simulation-only, not a scheduler activation. Missing performance is a blocker, not fabricated defaults. Heterogeneous performance calibration and operational health probes remain future work.

The watchdog now audits untracked prefix-matching pods instead of deleting them. Persistent tracked instance IDs/create intents, not arbitrary names, establish cleanup ownership. Default automated provisioning remains disabled.

## D. Approval package — NOT authorization to create

Source: RunPod MCP get_gpu_type, one POD, minCudaVersion12.8, read 18:53 UTC / 11:53 PDT; full evidence [runpod-quotes.json](runpod-quotes.json). Account list_pods returned empty, confirming a read works; it does not verify an independent supervisor key.

| GPU / cloud | Stock from read | Compute USD/h | 80 GB disk estimate/h | Two-hour estimate before tax |
|---|---|---:|---:|---:|
| RTX 4090 24 GB / Community | NONE | 0.34 | 0.010959 | 0.701918 |
| L4 24 GB / Secure | LOW, EU-RO-1 / US-MO-2 | 0.59 | 0.010959 | 1.201918 |
| L40S 48 GB / Secure | LOW, EUR-IS-2 / US-NC-1 / US-TX-3 / US-TX-4 | 1.09 | 0.010959 | 2.201918 |

RunPod storage docs quote container disk $0.10/GB/month. The hourly figures use 730 hours/month as an ESTIMATE; actual provider conversion, final placement price, tax and any ancillary charge must be confirmed before actionable approval. No exact all-in total can be confirmed for an unavailable Community machine. No network/persistent/global volume, public IP/port add-on or new CPU service is included. Secure L4 is the lowest quoted available alternative in this limited comparison; L40S offers more memory. There is no measured throughput comparison and no substitution is authorized. Recommend retaining RTX4090 preference until stock returns or obtaining explicit L4 approval after staging is ready.

### Exact proposed deployment

- One Community NVIDIA GeForce RTX 4090, 24GB, on demand; no invented DC placement. CUDA host floor12.8; public ports empty; vLLM listens on127.0.0.1:8000 only.
- Qwen/Qwen3-4B model AND tokenizer SHA `1cfa9a7208912126459214e8b04321603b3df60c`.
- vLLM0.8.5 Linux amd64 image `vllm/vllm-openai@sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33`.
- BF16, context10240, engine max-num-seqs4, GPU memory fraction0.85; prefix caching off, generation-config vllm, thinking off; 80GB ephemeral container disk, no volume.
- Registry manifest digest was fetched and matched; compressed image layers total9,044,092,803 bytes. Pinned model index total weights8,044,936,192 bytes (~7.49GiB). Qwen3ForCausalLM is in vLLM0.8.5's supported model list. Version docs describe CUDA12.4 binaries; conservative host floor12.8 remains. Actual host driver and generation canary are post-approval gates, not prevalidated hardware claims.
- Config has36 layers,8 KV heads,head_dim128. BF16 KV is147456 bytes/token, ~1.40625GiB per10240-token sequence,5.625GiB for4. Weights+KV ~13.12GiB before activations/graphs/allocator.16 full contexts cannot fit24GB. Inspect measured cache blocks and four-context canary before load. If fit fails, terminate and revise; do not silently lower the advertised API limit.
- Bootstrap fetches reviewed source commit c62386b2b6347f2555375fbd448d14769d852646 and embeds hashed current worker/config/collector overlays, with separate worker virtualenv. It checks installed vLLM version. No floating main or unreviewed image replacement. Startup download/install/canary time all count toward budget. Abort boot after15min. Launcher exits do NOT stop paid cloud billing.
- Private experiment uses REVIEWED_GPU_EXPERIMENT_ENABLED=true, PUBLIC_BETA_ENABLED=false; both defaultfalse in normal config. PROVISIONING_ENABLED=false, STRIPE_ENABLED=false, ESTIMATOR_CALIBRATED=false. The new gate changes runtime validation only, not prices/wallet/capture.

### Tests and exact actions after approval only

Prepare free workloads: `python -m scripts.prepare_gpu_payload`, then `python -m scripts.gpu_experiment prepare --count 10 --run-id ready10 --output .runtime/ready10.json` (repeat count100/1000 with unique output). Prepared inputs use deterministic80% short/20% medium logistics notes, temperature0, top_p1, output limits128/256. Prior pinned CPU tokenizer observation was237–863 input tokens; rerun CPU tokenization against the same artifact before approval. It is not GPU throughput. Arrivals are burst submissions of at most100 requests/job.

On an isolated HTTPS CPU staging stack, verify managed auth/keys, migration0006, matching pinned tokenizer, worker bootstrap, one expendable tenant and existing test-credit procedures. Do not seed production, expose public beta or deploy backend as part of this report. Review protected operator config and scheduler startup log after every policy restart.

| Arm | v2 | adaptive | MAX_INFLIGHT | Engine / worker cap |
|---|---|---|---:|---:|
| sequential | false | false | 1 | 4 |
| baseline (fixed concurrency) | false | false | 4 | 4 |
| adaptive | true | true | 4 | 4 |

Drain between arms. Restart API and scheduler only, keep model warm and all corpus/model/decoding parameters identical. The runner rejects public beta, Stripe, auto provisioning, wrong caps/flags, mock mode, wrong model/tokenizer or missing/fresh worker evidence. Operator must independently confirm the scheduler process matches its API configuration.

After that arm's config is verified:

```bash
python -m scripts.gpu_experiment run --execute --policy sequential --count 10 --run-id gpu-test-seq10 --timeout 300 --output .runtime/runpod/seq10
python -m scripts.gpu_experiment run --execute --policy baseline --count 10 --run-id gpu-test-base10 --timeout 300 --output .runtime/runpod/base10
python -m scripts.gpu_experiment run --execute --policy adaptive --count 10 --run-id gpu-test-adapt10 --timeout 300 --output .runtime/runpod/adapt10
# Repeat three arms for --count 100 with unique IDs/directories, timeout600.
# Only when prior audits pass and time/cost remains, repeat for1000, timeout2400.
python -m scripts.audit_gpu_run --run-directory .runtime/runpod/base10 --output .runtime/runpod/base10/audit.json
```

Audit every stage immediately. Expected files: workload.json,jobs.json,results.json,observations.jsonl,summary.json,audit.json; private GPU engine.jsonl and worker-overlap.jsonl. TestA requires all10 accepted/terminal/successful with real positive usage and no duplicate capture. TestB measures all three arms at100; p50/p95/p99, queue time, engine counter rates, GPU utilization/memory/KV, overlap and errors. TestC is conditional: project from100-stage timing plus safety margin; require at least45min remaining and predicted stage fit plus10min cleanup. If full three-arm1000 comparison cannot fit remaining time, skip it and report incomplete; do not claim a complete comparison. Maximum nine runs3330 requests plus canaries; no requirement to exhaust budget or finish every optional arm. Additional controlled100-request worker interruption is separately approved and audited with the existing opt-in prefix procedure; default prefix empty.

Matched complete report: `python -m scripts.compare_gpu_runs --include-sequential --directories ALL_NINE_RUN_DIRECTORIES --output .runtime/runpod/comparison.json`. It refuses missing/mismatched arms. Never insert synthetic replacements for skipped stages. Partial runs are reported individually. Recovery audit must show stale epoch rejected, original reservation conserved, one Usage/capture per successful request and zero reconciliation drift. Physical work may repeat after interruption.

### Budget, monitor, rollback and full cleanup

Maximum lifetime120min from actual provider creation, including boot/idle and cleanup. Total intent<=10USD including all storage/taxes/fees; not a RunPod hard cap. Stop admissions at7 estimate, terminate at8 or120min (earliest), preserve2 for lag/cleanup. Initial two-hour4090 compute+disk estimate~0.702USD before unknown tax; no guarantee of final invoice.

`scripts/experiment_guard.py` prepares an independent exact-pod termination guard, disabled unless --execute and an operator-approved receipt are supplied. The receipt is created securely AFTER approved pod read-back: pod_id,pod_name,provider_created_at,all_in_hourly_usd,all_in_hourly_cost_confirmed=true,operator_approved=true. No secrets in receipt; independent RUNPOD_API_KEY stays in supervisor environment, never GPU. Start on a reliable independent CPU host: `python -m scripts.experiment_guard --execute --receipt PRIVATE_RECEIPT.json --log PRIVATE_GUARD.jsonl`. Unit mocks prove mismatch refuses DELETE and deletion requires fresh404. It uses confirmed-rate elapsed estimates, not live invoice enforcement, and cannot guarantee spending during network/auth/host failures. Do not claim it is armed merely because script exists.

Manual monitor: inspect actual provider rate/elapsed/billing and guard heartbeat every minute; inspect startup until canary, and sequence/KV/util/error/latency samples each stage. Stop on any mismatch, OOM, high KV>=90%, missing termination capability, credential issue or billing drift. Freeze new admissions, drain/cancel only experiment jobs; export evidence if time permits. Independently DELETE exact newly created pod ID at RunPod, then fresh GET404 and inventory omission. Emergency stop is not final cleanup: stop compute, then delete pod. Container disk disappears on stop; persistent disk/network/global volumes may continue billing and must not be added casually. Check only experiment-owned retained resources; never delete unrelated account resources. Guard and container exits do not replace read-back verification.

After confirmed deletion, record existing gpu-record-stop metadata and actual cumulative invoice via gpu-invoice; these metadata commands do not stop cloud billing or change customer wallets. Revoke experiment credentials using normal procedures. Restore v2/adaptive flagsfalse if a comparison fails, keep calibration/provisioning/Stripe/public betafalse. Do not restart load or enlarge capacity automatically.

## E. Economics and quality

[Unit economics](../../economics/first-gpu-economics.md) supplies null-before-execution report/template and offline calculations/sensitivity. No real total tokens/GPU utilization/provider invoice/20–30% advantage is available. OpenRouter public models API returned no exact qwen/qwen3-4b row on this check; its static model page is not proof of a currently purchasable equal-revision quote. No unrelated model price is substituted. A20–30% advantage must be established against a sourced equivalent paid quote, real successful token mix, quality/latency and full operating cost.

Quality results and changed-file index are in [quality report](quality-report.md). Database tests use only isolated inferenceflow_batching_test and synthetic tenants. Final counts are recorded after final verification. No production/customer DB or wallet algorithm was changed. Existing uncommitted preparation is incorporated into the review branch rather than silently left out.

## Next decision

**NOT READY — BLOCKERS REMAIN.** Approve website publication independently if desired. Before paid approval: establish private staging HTTPS/auth and independent supervisor credentials, get available exact placement/full-cost quote, then explicitly authorize one specified GPU/config, <=120min, <=10USD all-in, approved synthetic workloads and complete deletion. Community4090 is unavailable; an alternative needs a new explicit choice. Do not interpret preparing files or the10USD intention as permission to provision.

Sources: [RunPod storage pricing](https://docs.runpod.io/pods/pricing), [vLLM0.8.5 supported models](https://docs.vllm.ai/en/v0.8.5/models/supported_models.html), [vLLM0.8.5 GPU binaries](https://docs.vllm.ai/en/v0.8.5/getting_started/installation/gpu.html), [pinned metrics](https://docs.vllm.ai/en/v0.8.5/serving/metrics.html), [pinned Qwen config](https://huggingface.co/Qwen/Qwen3-4B/blob/1cfa9a7208912126459214e8b04321603b3df60c/config.json), [provider comparison sources](../../architecture/providers.md).
