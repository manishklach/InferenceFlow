# One H100 NVL experiment — approval pending

Prepared October 26, 2026 PDT. This exact proposal supersedes the hardware/price/allocation in the earlier SXM proposal. **No H100 pod has been created.**

## Quote and budget

| Item | Proposed configuration / quoted cost |
| --- | --- |
| GPU | One NVIDIA H100 NVL, 94 GB, RunPod Secure Cloud |
| Placement | US-KS-2, LOW stock in the authenticated catalog; console deployment selectable |
| GPU quote | $3.19/hour |
| Storage | 80 GB temporary container disk, displayed $0.011/hour |
| Displayed total | **$3.201/hour** |
| Conservative all-in guard rate | **$3.21/hour**, allowing for displayed-price rounding |
| Normal target | 20–30 rented minutes, about **$1.07–$1.61** |
| Independent cutoff | **45 minutes from watchdog arming**, about **$2.41** at the guard rate for a full 45-minute rented lifetime |
| Internal allocation | **$5**, within the original total $10 experiment budget; not a spending target |
| Last observed balance | $9.62; recheck posted/pending charges immediately before creation |

No network volume, persistent paid storage or optional paid add-on is configured. The controller reserves one rounded hour at $3.21, below 70% of $5. RunPod does **not** enforce this allocation. Neither a requested termination deadline nor a software budget guard guarantees termination through a provider or GitHub outage. The quote is not locked; a changed shape/location or higher all-in price requires a new review rather than an automatic substitution.

H100 SXM was $3.99/hour GPU-only. H100 PCIe had no matching stock. B200 is more expensive and unnecessary for this model-fit validation. NVL is currently the least expensive selectable H100 option among these reads; stock is volatile.

## Deployment

```json
{
  "cloud": "SECURE",
  "dataCenterIds": ["US-KS-2"],
  "gpu": {"id": "NVIDIA H100 NVL", "count": 1, "minCudaVersion": "12.8", "minRamPerGpu": 32, "minVcpuCountPerGpu": 6},
  "disk": 80,
  "ports": [],
  "startSsh": false,
  "startJupyter": false,
  "globalNetworking": false,
  "image": "vllm/vllm-openai@sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33"
}
```

Qwen/Qwen3-4B and tokenizer revision `1cfa9a7208912126459214e8b04321603b3df60c`; vLLM 0.8.5, BF16, context 10,240, max four sequences, memory utilization 0.85, thinking and prefix cache disabled. Tenant concurrency is one for the sequential arm and four for concurrent arms. This same model/configuration fitted the earlier 48 GB A40. H100 is supported in the pinned vLLM version's [hardware requirements](https://docs.vllm.ai/en/v0.8.5/getting_started/installation/gpu.html); actual initialization, KV-cache allocation and canary execution on this H100 remain live smoke gates, not established results.

The private payload embeds reviewed worker overlays with SHA-256 verification and a fresh random experiment identity. Only the approved HTTPS origin and scoped bootstrap credential go to the GPU. No database, Auth0, GitHub, provider or cleanup key is sent there. vLLM binds to 127.0.0.1:8000, and the worker connects outbound to the control plane. Public beta, Stripe and automated provisioning stay disabled. The prepared payload and cleanup plan remain marked approval pending.

## Control-plane readiness established without a GPU

Protected CPU run [40288126492](https://github.com/manishklach/InferenceFlow/actions/runs/40288126492) uses tested source `0459ce9b9e594f64a5f370623d2312333039782d`. Endpoint: `https://requirements-magnificent-hamilton-imported.trycloudflare.com`. PostgreSQL and scheduler are supervised on GitHub; no RunPod key exists on this host.

Verified real-mode HTTPS readiness, authenticated operator report, anonymous wallet rejection, no-worker admission rejection without wallet mutation, and zero workers. The exact owner-approved Auth0 callback was saved and verified after reload; OIDC login returned status ok and the authenticated owner wallet was accessible. Its zero balance is distinct from the isolated synthetic experiment tenant's test credit.

Actual main-branch commands produced visible `verified` Actions receipts for sequential (sequence 1), read-only audit (2), adaptive (3), and restored baseline (4). The baseline command was prepared at 07:56:52.767490 UTC, received at 07:57:01.810406, and verified at 07:57:26.865834: approximately **9.04 seconds delivery + 25.06 seconds transition**, for this one observation. It does not establish a latency SLA. Audits here cover zero accepted real requests; GPU billing/recovery still needs the paid run.

Source validation passed **230 tests, one GPU test skipped**, 31 scheduler-v2 regressions, lint/type checks, and a separate **40/40 mock** policy/reconnect/audit rehearsal with authenticated GitHub Contents access. Revalidate current baseline flags, host lifetime headroom and HTTPS immediately before any GPU create. A fresh engine-canary proof gates each real workload admission.

## Gated test commands and evidence

The operator loads the owner-decrypted four-field connection into each child process environment. Credentials must not appear in Git, command arguments or public output. The existing driver refuses mismatched actual server policies, identity, slots, stale workers and missing live engine proof.

```powershell
# Only after rental approval, armed independent cleanup and a ready real worker:
python -m scripts.gpu_experiment run --execute --policy baseline --count 10 --run-id h100-smoke --workload-file .runtime/third-experiment-prepared/smoke-10.json --output .runtime/h100-smoke

# For each following arm, deliver/verify its policy and audit the previous stage first:
python -m scripts.gpu_experiment run --execute --policy sequential --count 100 --run-id h100-sequential --workload-file .runtime/third-experiment-prepared/comparison-100.json --output .runtime/h100-sequential
python -m scripts.gpu_experiment run --execute --policy baseline --count 100 --run-id h100-baseline-a --workload-file .runtime/third-experiment-prepared/comparison-100.json --output .runtime/h100-baseline-a
python -m scripts.gpu_experiment run --execute --policy adaptive --count 100 --run-id h100-adaptive-a --workload-file .runtime/third-experiment-prepared/comparison-100.json --output .runtime/h100-adaptive-a
```

Smoke: ten real requests, at least 90% joint compact engine/hardware coverage over the accepted-to-terminal window, correct pinned identity/output/tokens and verified PostgreSQL audit. Then identical sequential 100 and baseline/adaptive/adaptive/baseline 100 arms with distinct run IDs. Repeat the displayed 100-request command with the matching policy/run ID; never run an arm against stale flags. The adjacent adaptive arm also requires an acknowledged audit before admission.

Only if all earlier gates pass and remaining cutoff/budget permits: at most 500 requests from the prepared interruption-500 workload. Its controlled worker interruption occurs after physical generation and before settlement; the engine remains running. Verify recovery, retries, unique usage/capture records and zero drift. Maximum **1,010 requests total** across all stages; 500 is optional, not an unconditional load target. Abort cold start if no healthy engine within 15 rented minutes. Stop admissions on critical errors or unexpected spending. Do not wait for the watchdog on a known failure.

Collect compact GPU/provider logs continuously before deletion, overlap/active sequences, queue and dispatch timing, successful input/output tokens, request p50/p95/p99 completion, retries, 60-minute attainment, cold/idle/failure overhead and the full rented lifetime. Audit each stage through the run-bound read-only mailbox and retain reports in the owner-encrypted final export. Report actual posted GPU/disk costs separately from estimates. Cost per million successful output tokens includes the entire provider bill and overhead; synthetic wallet capture is not provider cost. Unknown telemetry intervals remain unknown. Hardware comparisons with A40/L4 are confounded; scheduler comparisons use identical workloads on this one H100. Hosted-provider comparisons remain qualified for model/precision/context/thinking differences. No savings or GO claim precedes measured evidence.

## Independent shutdown and exact approval

Existing dedicated read/write cleanup credentials remain only in protected GitHub `gpu-experiment`. Historical live deletion proof exists; a fresh GET is not new DELETE proof. After explicit one-pod approval, dispatch the reviewed exact-identity watchdog, obtain required owner environment review, then verify fresh authenticated armed status with `max_runtime_minutes: 45` and the $5/$3.21 plan before creating anything. Bind it to exactly the new pod name, random marker, provider ID and creation window. Stop early around 30 rented minutes. The watchdog requests deletion at its 45-minute arm deadline, on over-quote readings, or on cancellation, and verifies a fresh 404. Provider/GitHub outages remain a risk; deadline and outage paths are not claimed as live-proven.

After normal completion or any critical failure: stop new work, cancel unresolved jobs where possible, preserve logs/audit evidence, terminate this exact pod directly or via its independent finalizer, verify authenticated RunPod 404 and absence of experiment storage, then export/stop the CPU host. No paid persistent storage is created or retained. Reconcile posted provider billing and remaining balance afterward. Cleanup authority applies only to the one approved experiment resource.

Required authorization: **one H100 NVL in US-KS-2 under this quote, conservative $3.21/hour ceiling, $5 internal allocation inside the original $10 total, 45-minute independent cutoff, and the gated workloads above**, subject to fresh unchanged stock/price/balance/host checks and armed independent cleanup. Approving this document does not authorize a replacement pod, public ports, persistent volumes, live Stripe, public beta or automated provisioning.
