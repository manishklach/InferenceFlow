# First GPU experiment: pre-armed cleanup readiness

Prepared on 2026-10-24, approximately 13:25 PDT. **NO-GO for paid provisioning.**
No GPU, endpoint or paid storage was created. Wallet/billing implementation,
automatic provisioning, public beta and Stripe live payments are unchanged.

Local verification: **162 tests passed, 1 real-GPU test skipped**, including
25 new watchdog cases. Ruff, mypy (34 source files), manual-only protected
workflow checks and the publishable-file secret scan passed. Tests simulate
provider success/failure, pagination, identity rejection, deletion confirmation,
retry, interruption and time/budget decisions; they do not prove live DELETE.

## Evidence refreshed

The signed-in RunPod console Billing summary showed **$10.00 credit**, **$0.00/hr
spend**, zero GPUs/vCPUs/endpoints and zero GB storage. The connector's complete
`list_pods` read returned no pods. The GitHub protected-secret read-only
[preflight passed](https://github.com/manishklach/InferenceFlow/actions/runs/40128846861).
It proves inventory-read authentication, not termination permission.

Fresh `get_gpu_type` reads used POD availability, one GPU and minimum host CUDA
12.8. These are catalog rates, not machine-specific all-in checkout quotes:

| GPU/tier | VRAM | Compute USD/hr | Stock in read |
|---|---:|---:|---|
| RTX 4090 Community | 24 GB | 0.34 | NONE |
| L4 Secure | 24 GB | 0.59 | LOW; EU-RO-1, EUR-IS-1, EUR-IS-2, US-MO-2 |
| L40S Secure | 48 GB | 1.09 | HIGH aggregate; individual returned DCs LOW |

L4 Secure is the lowest quoted currently available candidate among these three
requested options. It needs explicit approval as a substitution for the selected
4090. Actual economics versus L40S cannot be decided from hourly rates alone;
startup and measured successful-token throughput remain unknown.

[RunPod pricing](https://www.runpod.io/pricing) lists running container disk at
$0.10/GB/month. For 80 GB ephemeral disk, using a stated 730-hour/month estimate:

| Candidate | Compute + estimated disk USD/hr | Two-hour estimate |
|---|---:|---:|
| L4 Secure | 0.600959 | 1.201918 |
| L40S Secure | 1.100959 | 2.201918 |

These exclude unverified taxes/fees and are not final quotes. Confirm selected
machine resource constraints, disk proration and charges before approval.
The undeployed console L4 hardware draft with 80 GB disk displayed GPU
$0.59/hour, disk $0.011/hour and a rounded total $0.60/hour, billed per
millisecond. It advertised 55 GB RAM and **6 vCPU**. That does not satisfy the
existing 4090 payload's minimum 8-vCPU filter: a prospective L4 configuration
must explicitly review a six-vCPU floor, never blindly reuse that payload.
This hardware-price draft still selected the console's default PyTorch image,
not our pinned vLLM image; no Deploy button was pressed and it is not a final
application deployment configuration or an exact tax-inclusive quote.
Avoid double-counting storage if the provider's pod `cost` already includes it.
No persistent/network/global volumes, public ports or paid CPU host are planned.
The $10 credit balance is not a guaranteed or configured hard spending cap.

## Model and control plane

The exact pinned Hugging Face config resolves: Qwen3ForCausalLM, BF16, 36 layers,
8 KV heads, head dimension 128, maximum positions 40,960. The unchanged model and
tokenizer SHA is `1cfa9a7208912126459214e8b04321603b3df60c`.
Docker Registry's v0.8.5 manifest still hashes to the pinned
`sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33`.
Identity resolution is verified; actual CUDA execution is not.

Keep context 10,240, maximum 4 resident sequences, GPU memory utilization 0.85,
BF16, thinking disabled and prefix caching disabled. Prior weight metadata is
approximately 7.49 GiB; four full-context KV caches add approximately 5.625 GiB,
before runtime overhead. This is an estimate, not a demonstrated VRAM fit.
Check vLLM startup cache capacity and maximum-context canaries before admission;
fail closed rather than silently shrink the advertised context.

The temporary staging endpoint currently responds 200 for HTTPS health/readiness
and 401 for an unauthenticated wallet. Real owner OIDC login was verified.
API, scheduler and isolated PostgreSQL are running. **It remains mock mode.**
The local supervisor expires at 14:49 PDT today, which is insufficient for a
new two-hour experiment started around 13:25. A reviewed restart/extension,
real-mode configuration and identical pinned CPU tokenizer are required before
arming. A temporary tunnel depends on this machine's power/network availability.
The Sites showcase is not the inference backend.

Prospective GPU configuration: one approved GPU, pinned image above, 80 GB
ephemeral disk, no mounts/public ports, vLLM on 127.0.0.1:8000 and outbound HTTPS
worker connection with an expendable scoped bootstrap credential. No database,
Stripe or RunPod key belongs on the GPU. Add exact cleanup ownership metadata
from the [cleanup runbook](../../github-cleanup-host.md). Existing payload
placeholders and Community tier must be explicitly reviewed before rendering a
private approved L4 payload; no substitution is deployed here.

## Test sequence after approval only

Use the existing synthetic short/medium corpus unchanged across sequential,
baseline concurrency four and adaptive policies. Start with 10 requests, then
100 only after identity, output, token metering and ledger checks pass. Run up
to 1,000 only if remaining time/budget permit; skip arms rather than exceed the
approved total. Configure actual server policy/cap before each arm; the loader
refuses mismatched configuration. A 110-minute cleanup limit includes startup.

```powershell
# Offline preparation only; choose new paths/run IDs on each experiment.
python -m scripts.gpu_experiment prepare --count 10 --run-id gpu-test-smoke --output .runtime/gpu-reviewed/10.json
python -m scripts.gpu_experiment prepare --count 100 --run-id gpu-test-curve --output .runtime/gpu-reviewed/100.json
python -m scripts.gpu_experiment prepare --count 1000 --run-id gpu-test-load --output .runtime/gpu-reviewed/1000.json

# ONLY after explicit GPU approval and real-mode worker readiness.
# Supply existing control URL, synthetic tenant API key and metrics token securely.
python -m scripts.gpu_experiment run --execute --policy baseline --count 10 --run-id gpu-test-smoke --output .runtime/gpu-reviewed/baseline-10 --timeout 600
python -m scripts.gpu_experiment run --execute --policy baseline --count 100 --run-id gpu-test-curve --output .runtime/gpu-reviewed/baseline-100 --timeout 1200
python -m scripts.gpu_experiment run --execute --policy adaptive --count 100 --run-id gpu-test-adaptive --output .runtime/gpu-reviewed/adaptive-100 --timeout 1200
```

Repeat matched arms for other counts only within the cumulative deadline.
Configure `--policy sequential` with actual cap one for its arm. A one-shot
synthetic worker interruption uses the existing opt-in launcher; verify requeue,
fenced stale results, one capture per successful request and zero ledger drift.
Do not enable fault injection on other workloads or change wallet balances/rates.

Capture worker overlap, vLLM running/waiting sequences and KV metrics,
one-second NVIDIA utilization, startup/idle/failed time, successful input/output
tokens/sec, API queue latency, p50/p95/p99 completion and actual 60-minute
attainment. A short successful run cannot establish a sustained 60-minute SLA.
Compute fully loaded USD/million successful output tokens from total provider
cost including startup, idle, failures and disk. Keep estimated costs distinct
from eventual invoice/billing evidence. Missing samples or aborted arms must
remain missing, never replaced with simulated results.

## Remaining approval gates

1. Controller code and deterministic failure/cancellation tests reviewed;
   workflow merged, then live armed heartbeat verified immediately before create.
2. Actual DELETE authority still unverified. No existing pod exists to test and
   no paid disposable test has been authorized. GET success, R/W label, fake HTTP
   tests and a nonexistent-ID 404 do not satisfy this requirement. Stop if this
   cannot be resolved without relaxing the user's safeguard.
3. Refresh full machine quote, balance and stock; confirm storage/tax fees.
4. Refresh real-mode CPU staging and tokenizer, extend supervised lifetime to
   cover the whole experiment plus cleanup, and verify worker credentials.
5. Present final exact configuration/cost/risks and obtain explicit one-pod
   creation approval. Current instruction authorizes preparation only.

There is no measured economic advantage or performance GO recommendation yet.
The missing repository LICENSE remains unresolved; Apache-2.0 is a reasonable
option for an openly reusable platform, but only the owner can select it. No
license is added by this preparation.
