# First real GPU experiment — approval proposal

Prepared 2026-10-23. Nothing in this proposal was deployed or provisioned. Maximum proposed total expense: **$10**, including compute, storage and applicable taxes/fees. This supersedes the older illustrative $5/30-minute proposal for this experiment only.

## Live catalog evidence and recommendation

Runpod MCP `get-gpu-type`, product `POD`, cloud `SECURE`, count 1, minimum host CUDA 12.8, read around 11:40 UTC (04:40 PDT):

| GPU | VRAM | Secure hourly compute quote | Latest stock in this review |
|---|---:|---:|---|
| NVIDIA L4 | 24 GB | $0.59 | NONE |
| NVIDIA GeForce RTX 4090 | 24 GB | $0.89 | NONE |
| NVIDIA L40S | 48 GB | $1.09 | LOW: EUR-IS-2, OC-AU-1, US-TX-4 |

Recommend **one L40S in US-TX-4**, on demand, Secure Cloud. It is the cheapest of these three with stock in the latest reads; this is not a measured throughput-per-dollar claim. L4 is cheapest by hourly rate if it returns to stock. All three briefly showed LOW during earlier reads; the latest reads above supersede those. Quoted capacity is not reserved. Re-read price, stock and placement constraints immediately before approval execution; no GPU, tier, price increase, data-center or storage substitution without approval. The stock read reports host CUDA 13.2 capacity, not the CUDA runtime inside the pinned image. CPU/RAM placement filters in the payload have not been placement-tested.

Community catalog rates ($0.44 L4, $0.34 RTX 4090, $0.79 L40S) are NOT the approved tier, and Community stock was not checked. No spot/savings-plan commitments.

## Compatibility verified without a GPU

Reviewed `docs/gpu-deploy.md`, `infra/model-lock.json`, `packages/common/providers.py`, `apps/worker/{main,engines}.py`, identity/tokenizer code, the scheduler and `tests/test_gpu.py`.

* Model and tokenizer: `Qwen/Qwen3-4B`, SHA `1cfa9a7208912126459214e8b04321603b3df60c`. The exact revision resolves through Hugging Face. Config reports `Qwen3ForCausalLM`, BF16, 36 layers, 8 KV heads and head dimension 128. Safetensors index reports 8,044,936,192 bytes of weights (~7.49 GiB).
* Engine: `vllm/vllm-openai@sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33`. Docker Registry manifest bytes hash to that digest; the current `v0.8.5` tag resolves to the same digest. Image config is Linux/amd64, CUDA 12.4.0, with the Python OpenAI server entrypoint. vLLM 0.8.5 documents Qwen3 support. Newer host drivers are expected to run the older runtime; actual CUDA/kernel compatibility remains a smoke-test gate.
* Rough BF16 KV requirement is 2(K,V) × 36 × 8 × 128 × 2 bytes = 147,456 bytes/token. Sixteen full 10,240-token contexts alone need 22.5 GiB KV, plus weights/runtime: **do not claim 24 GB can hold that worst case**. The first workload uses about 512 input tokens and at most 128 output tokens, with later bounded 2,048/256 mixes. L40S gives headroom without quantization. Context length remains 10,240 to match API limits (8,192 prompt + 2,048 output).
* Prefix caching stays explicitly disabled. CPU API tokenizer and engine tokenizer use the same SHA and `enable_thinking=False`. Verify the pinned image's actual `--help`, BF16, VRAM allocation, alias, canary and usage accounting after authorization. Documentation/manifest compatibility is not real-hardware validation; `gpu_validated` remains false.

## Repository findings that shape the deployment

The provider adapter is REST v2, disabled unless explicitly enabled, and has a durable create intent. It does **not** currently supply a CUDA floor, explicit cloud tier, worker environment, engine launch command or port configuration. Its catalog quote is an unfiltered catalog plus an operator-confirmation marker, not a binding machine quote. Its budget estimate includes GPU compute only. Therefore do not call its automatic create path for this experiment. Keep `PROVISIONING_ENABLED=false`; use the reviewed MCP payload and record a manual attachment.

Do not run the guide's `docker run` command inside a Runpod container: Docker-in-Docker is not the deployment path. Run engine and outbound worker as sibling processes in the pinned container, with a separate worker virtualenv to avoid replacing vLLM's dependencies. No public vLLM/metrics/SSH/Jupyter port is required. Pod logs provide the initial diagnostic channel. The GPU receives only the experiment bootstrap secret and a scoped HTTPS control-plane address, never DB, Stripe or Runpod API credentials.

`tests/test_gpu.py` covers one successful request, positive real usage and a positive charge; it does not test the requested load tiers, cost or batching. The root pytest fixtures migrate/truncate a database ending `_test` even for this test. Use a dedicated experiment control plane/database; never point its API at that fixture database while running the test. Use the standalone SDK from another process for the load stages. Provider/vLLM protocol unit tests use mocked HTTP, not rented hardware.

## Prepared configuration and connection sequence

Review [`infra/first-gpu/runpod-pod.proposed.json`](../infra/first-gpu/runpod-pod.proposed.json), [`control-plane.env.example`](../infra/first-gpu/control-plane.env.example), and [`launch.sh`](../infra/first-gpu/launch.sh). All are inert until explicitly executed. The JSON references this reviewed source SHA for the existing worker: `c62386b2b6347f2555375fbd448d14769d852646`. It bootstraps the small worker virtualenv; launch script text is included in the payload. No new image/registry/storage service is needed. Dependency install and startup time are paid Pod uptime. The ephemeral disk is 80 GB; no persistent, network or global volume is requested.

Before provisioning: install `.[gpu]` on a separate CPU control plane, apply migration 0006 there, retain all existing identity/encryption/DB secrets, and establish an approved private HTTPS path reachable from the Pod. Sites is currently a static showcase, not this control plane. The bootstrap URL/secret placeholders must be securely substituted into the create request; never commit a rendered request. No working external control-plane address or secret is assumed by this proposal.

After authorization and creation:

1. Read the Pod back and verify exact GPU count/type, actual hourly quote, image digest, disk, cloud, placement and empty public ports. If anything differs, terminate immediately. Record provider ID, creation/billing start and disk rates before workload admission.
2. On the CPU control plane, record the attachment (metadata only):

   ```bash
   python -m packages.common.cli gpu-attach --instance-id POD_ID --provider runpod --gpu-type 'NVIDIA L40S' --hourly-micro-usd 1090000 --billing-increment-seconds 1 --started-at ACTUAL_START_ISO_UTC
   ```

3. Confirm engine startup and worker readiness canary in Pod logs. `/v1/models` must report `vllm` and the pinned identity; operator scheduling report must show exactly one attached real-mode worker with the Pod ID. Model loading observation remains unknown until extracted from engine logs; startup-to-health is recorded separately. Healthy heartbeats renew the worker credential; a disconnected worker must re-register before expiry.
4. Give only the test driver a seeded/funded synthetic test-tenant API key and the private control-plane URL. Keep Stripe off. Use the SDK against the deployed API: `InferenceFlowClient(api_key, base_url=control_plane_url)`. Never call the engine directly for the platform's measured load.
5. Run `RUN_GPU_E2E=1 ... pytest tests/test_gpu.py -q` only after confirming the isolated fixture DB is distinct from the running experiment API DB and matching real-mode settings. This is one extra smoke request beyond the 1,110 planned load requests; engine readiness canaries also consume GPU time and belong in total cost.

## Test stages and time limits

Prepare seeded, unique synthetic prompts before rental, record actual pinned-tokenizer lengths and request payload hashes. Use no customer/private data. Temperature 0, top_p 1, thinking disabled. Do not require identical generated text across batch sizes, but review correctness/quality.

| Stage | Submission shape | Main checks | Stop/gate |
|---|---|---|---|
| 10 requests | One job, 10 unique `custom_id`s, ~512 input / max 128 output | Full API → queue → engine → results → meter → wallet flow, non-MOCK text, identity, ordered results, positive tokenizer usage | Zero usage mismatch/drift; <=10 minutes |
| 100 requests | Five matched 20-request jobs, drained sequentially; tenant `MAX_INFLIGHT` 1,2,4,8,16, adaptive off | Sequential baseline and continuous batching curve; CPU scheduler restart between cap changes, same worker/model, persist overhead separately | <=25 minutes total; stop expansion at OOM, preemption pressure, KV >=90%, errors or worse latency |
| 1,000 requests | Ten jobs ×100 requests submitted promptly, bounded to best safe measured cap; 80% short and 20% medium (<=2,048 input/max256 output), v2 on/adaptive off | Queue durability, completion under load, all-accepted 60-minute target, one controlled worker-process restart (engine stays up), fenced recovery and no duplicate capture | <=60 minutes from first acceptance; reserve time to drain, reconcile, export and terminate |

API schema caps each job at 100 requests: a single 1,000-request body would be rejected. Use unique stable idempotency keys and retry the same key/payload after ambiguous responses. Drain the queue before changing caps. Use `deadline_seconds=3600`, `admission_policy='best_effort'`; expired/failed/canceled/rejected work is reported, not silently excluded. No adaptive-vs-fixed result is claimed by this first test; a matched adaptive replay would add requests/time and requires an explicitly revised plan within the same approved ceiling.

The 100-request curve is exploratory (20 samples/cap), not statistically strong. The full first experiment lasts at most 120 minutes from provider creation, including <=15 minutes initialization, stage limits and cleanup reserve. Do not start the 1,000 tier unless at least 65 minutes remain. If a stage uses its maximum time, skip later stages rather than overrun. A burst that finishes within an hour is evidence for that workload only; it does not establish a sustained-load SLA. Stop immediately on identity, tenancy or billing defects.

## Measurements and retained evidence

Collect synchronized UTC timestamps and monotonic intervals, provider create/delete responses, engine/worker logs, request/job IDs, acceptance/start/final times, ordered results and token usage, attempts/retries, tenant wallet and ledger snapshots, operator report, and actual provider invoice/billing rows. Redact credentials; keep full raw outputs in an access-controlled experiment artifact folder. Paginate all results; the ten 100-request jobs fit one results page each.

* **Batching:** compare output tokens/s for the matched 20-request cap1 baseline against cap2/4/8/16; speedup = throughput(c)/throughput(1), normalized concurrency efficiency = speedup/c. Also sample vLLM running/waiting requests, KV cache, preemptions and engine metrics every 5 seconds over private loopback. If `vllm:iteration_tokens_total` exists, delta sum / delta count gives tokens per engine iteration (not a pure decode batch-size measurement). Record unavailable metrics as missing. Client concurrency alone does not prove GPU batching.
* **GPU utilization:** `nvidia-smi` samples every 5 seconds, including memory/power; time-weighted mean/p95 and missing intervals, plus 15-second worker heartbeats. Hardware utilization is distinct from request-slot occupancy and from SM efficiency. The launcher emits hardware samples to Pod logs. Set up the private metrics collector before approval execution; existing worker telemetry is a rolling snapshot, not a complete historical metric archive.
* **Throughput:** successful requests / workload wall seconds, output tokens / wall seconds, input tokens / wall seconds separately. Report warm-window and total paid-uptime denominators, queue latency, API-to-terminal p50/p95/p99, failed/retried attempts, and cold start. Existing dashboard 24-hour averaged token rate is not benchmark throughput.
* **Completion:** report successful jobs AND requests completed within 3,600 seconds from their acceptance, divided by ALL accepted jobs/requests respectively; report rejected submissions separately. Successful-only percentiles and the tenant performance endpoint's successful-only attainment are insufficient alone. Include age of all unfinished work and observation cutoff.
* **Cost:** total provider compute + disk + any tax/fee from creation through confirmed termination, including downloads, cold start, idle, failures and canaries. Token revenue/customer ledger capture is separate from provider cost. Cost per successful request and provider dollars per million actual input+output tokens include waste; report prefill/output token denominators separately too. Import the final cumulative invoice with its reference/coverage; do not call the quote an actual bill.

## $10 ceiling and termination

Runpod's docs currently quote container disk $0.10/GB/month and per-second Pod compute/storage billing. Using 730 hours/month for an estimate, 80 GB is ~$0.01096/hour. L40S + disk is ~$1.10096/hour; 120 minutes is **~$2.20192 before applicable tax/fees**. Exact provider quote/bill wins. No persistent/network/global storage is requested, so no intended retained storage balance after deletion. No paid CPU hosting, registry, network volume, backup or top-up is authorized by this plan.

Requested ceiling is $10 ALL-IN, not a request to buy $10 credit. Aim for <=$3; retain the rest as contingency. Stop new admissions at $7 estimated all-in spend; terminate at $8 estimate or 120 minutes, whichever is first, leaving $2 for lag/rounding/cleanup. Check itemized provider billing at least every minute alongside an elapsed-time estimate and terminate immediately on quote increases or unknown fees. Abort initialization after 15 minutes. Require an independent supervisor on a separate reliable host with read/delete permission and provider budget alerts. Configure it BEFORE creation. The existing watchdog may help with session/idle limits after `gpu-attach`, but omits storage/taxes and cannot enforce a hard provider cap during an outage. Container/process exit and in-Pod timers do NOT stop Pod billing. There is no verified atomic $10 provider hard cap in this review; do not claim an unconditional guarantee. If independent teardown cannot be established, do not provision.

After every run, including failures: stop admissions, drain/cancel remaining jobs, reconcile ledger and export evidence while container disk still exists. Then **terminate**, rather than leave a stopped Pod:

```text
POST https://api.runpod.io/v2/pods/POD_ID/action  {"action":"stop"}  # optional immediate compute stop
DELETE https://api.runpod.io/v2/pods/POD_ID                         # full termination
GET https://api.runpod.io/v2/pods/POD_ID                            # require not found
GET https://api.runpod.io/v2/pods                                  # require ID absent
```

Prefer direct DELETE after evidence export; stopping wipes ephemeral disk and is not an evidence-preserving intermediate step. On the console: Pods → named experiment → Stop (emergency) or Terminate/trash (full teardown). Stopping a Pod with persistent volume disk can leave storage charges; terminating a Pod does not delete a separately created network/global volume. This proposal creates neither. Re-read storage inventory and billing to confirm no experiment-owned resource or ongoing charge remains. Do not delete unrelated resources. Finally record verified stop with `gpu-record-stop` and invoice with `gpu-invoice`; these metadata commands do not stop resources. Remove the experiment bootstrap credential afterward.

## Exact authorization required

Approval must cover (1) one Secure Cloud on-demand L40S in US-TX-4 at a freshly confirmed rate no higher than $1.09/hour compute, (2) 80 GB ephemeral disk at the confirmed storage rate, no persistent volumes, (3) <=120 minutes and <=$10 all-in with independent emergency deletion, (4) the pinned engine/worker and private control-plane connection plus a scoped bootstrap secret, (5) the smoke/canaries and 10/100/1,000 synthetic requests and controlled worker restart, and (6) evidence export and irreversible termination of THIS experiment Pod. A changed quote, unavailable placement, new charge or alternative hardware/tier requires a revised approval. Account funding/auto-top-up, public exposure and additional infrastructure are not authorized.

No provisioning authorization has been given. No Pod, template, endpoint, secret, storage volume or deployment was created/changed in preparing this proposal. Read-only inventory showed no Pods and no network volumes; this does not assert the whole account has zero spend.

## Preparation checks actually run

The launcher and complete embedded container command pass `bash -n`. Payload top-level/GPU field names were checked against the live v2 OpenAPI schema, with explicit assertions for empty exposed ports, no persistent mounts, one Secure GPU, exact image digest and matching inline launcher. This is not a remote create validation or a full JSON Schema validator. Linux line endings are preserved in the shell script and embedded command.

Two existing mocked HTTP checks (`test_vllm_http_protocol`, `test_provider_catalog_endpoint`) passed by direct invocation without database fixtures. A normal focused pytest run selected four provider/vLLM tests but all four stopped at fixture setup because Windows-to-WSL PostgreSQL connections timed out; retrying via localhost also failed. PostgreSQL reported ready inside WSL, but the Windows client path remains unresolved. No claim is made that those four pytest tests or a real GPU test passed in this review. No application/schema deployment or database-network configuration was changed to work around this preparation issue.

Before spending, resolve that CPU test connectivity, establish the independently supervised delete path, verify live control-plane routing, and choose a private process-control channel for the worker-restart injection. The zero-inbound-port payload does not provide SSH/exec. The launcher stops when its worker dies, so a worker-only restart under load needs a reviewed supervised-worker launch adjustment before that stage; do not silently substitute a whole-Pod restart that wipes ephemeral disk. This is an explicit preflight gap, not a validated recovery result.

## Official sources checked

* Live Runpod MCP `list-gpu-types` and later `get-gpu-type` availability/quotes; final reads supersede initial stock.
* [Runpod Pod pricing](https://docs.runpod.io/pods/pricing), [storage pricing/persistence](https://docs.runpod.io/pods/storage/types), [v2 create schema](https://api.runpod.io/v2/openapi.json), [Pod management](https://docs.runpod.io/pods/manage-pods).
* [Pinned Qwen config](https://huggingface.co/Qwen/Qwen3-4B/blob/1cfa9a7208912126459214e8b04321603b3df60c/config.json), [vLLM 0.8.5 supported models](https://docs.vllm.ai/en/v0.8.5/models/supported_models.html), [CUDA installation](https://docs.vllm.ai/en/v0.8.5/getting_started/installation/gpu.html), [metrics](https://docs.vllm.ai/en/v0.8.5/serving/metrics.html), Docker Registry manifest/config public reads.
