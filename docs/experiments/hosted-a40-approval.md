# One A40 hosted experiment — consumed approval

The owner approved this exact rental. It was created and terminated before inference because of a provider-response validation bug; see the [attempt report](../validation/2026-10-26/hosted-a40-startup-report.md). This document is the historical proposal, not authorization for a replacement.

Prepared October 26, 2026 PDT. No GPU has been created for this session. Prior H100 approval covered its completed single rental; this is a new request.

| Item | Exact proposed configuration |
| --- | --- |
| GPU/provider | One NVIDIA A40 48 GB, RunPod Secure Cloud |
| Placement | CA-MTL-1; fresh catalog LOW stock, console deployment selectable |
| GPU quote | $0.59/hour |
| Disk | 80 GB temporary container disk, displayed $0.011/hour |
| Displayed total | **$0.601/hour** |
| Conservative guard rate | **$0.61/hour**, allowing for rounding |
| Normal target | 20–30 rented minutes, approximately **$0.20–$0.31** |
| Independent cutoff | **45 minutes from watchdog arming**; about **$0.46** for a full 45-minute rented lifetime at the guard rate |
| Internal allocation | **$1 within the original total $10 experiment budget** |
| Last observed account balance | $8.26; recheck balance/pending costs before creation |

No persistent/network volume or optional paid add-on is requested. The guard reserves a rounded hour ($0.61), below 70% of $1. This allocation is not a spending target or a RunPod-enforced cap; provider/GitHub outages can defeat requested termination timing. Price and stock are not locked. Do not substitute a GPU/location or accept a higher quote without review.

## Choice and deployment

The same pinned model/context/slots passed a prior A40 smoke test, and this avoids paying H100 rates while validating orchestration. The catalog also listed a cheaper 24 GB RTX A5000, but that would add a new unvalidated hardware combination to the first hosted-driver integration run. This choice is not a claim that A40 has the lowest token cost.

Qwen/Qwen3-4B and tokenizer revision `1cfa9a7208912126459214e8b04321603b3df60c`; vLLM image `vllm/vllm-openai@sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33` (0.8.5). BF16, context 10,240, four-sequence hard cap, memory utilization 0.85, thinking/prefix cache disabled. Sequential tenant concurrency one; concurrent arms four. vLLM is loopback-only; worker connections are outbound HTTPS. No public ports, SSH, Jupyter, global networking or mounted storage. Pinned worker overlays are hash-verified. Actual startup and fit remain smoke gates on the rented pod.

## Verified hosted control plane

Protected CPU run [40380907617](https://github.com/manishklach/InferenceFlow/actions/runs/40380907617), source `091ea47fa430901b8947d8a4ada746980fd40a2e`, is running in opt-in hosted-plan mode. HTTPS origin: `https://accomplish-chris-russia-referenced.trycloudflare.com`. The API, PostgreSQL and scheduler are supervised on GitHub. The dedicated reader authenticated through [preflight 40379775238](https://github.com/manishklach/InferenceFlow/actions/runs/40379775238); live SSE log access still needs this approved pod.

Verified real-mode readiness, pinned model/tokenizer revision, invalid worker registration returning 401, anonymous wallet rejection, and no-worker submission returning 503 without wallet mutation. There are zero workers. Public beta, Stripe and provisioning remain false. This is an API-only experiment using its isolated synthetic API key and scoped worker authentication; browser OIDC login on the new origin is not part of the test and Auth0 settings were not changed. Synthetic tenant credit is not RunPod funding or a customer wallet change.

The driver, policy transitions, stage audits, checkpoints and continuous provider-log collection run on GitHub, not this workstation. Default plan mode remains off outside this explicitly prepared job. The experiment process has only provider-read authority; API/DB containers and GPU do not receive that key. The cleanup key remains in the separate protected watchdog job. Code passed 239 tests (one GPU skipped), 31 scheduler regressions, lint/type checks and 40/40 mock staged requests. Real plan-mode execution, streaming and early cleanup are still integration-test requirements.

## Gated workload and measurement

The hosted runner automatically executes: smoke ten → sequential 100 → baseline/adaptive/adaptive/baseline 100 → optional controlled-interruption 500. Maximum **1,010 requests**, not an unconditional target. Each stage requires the correct effective policy and a fresh engine-canary admission proof. Each completed stage requires read-only PostgreSQL settlement/timing audit; the first ten also require at least 90% compact engine/hardware coverage. Failures, stale metrics or inactive cleanup stop admissions. Existing intent is never blindly replayed.

Stages that cannot fit their reserved time are not admitted. Normal work ends at 30 rented minutes or two minutes before independent cutoff, whichever is earlier. Startup exceeding fifteen rented minutes ends the host. The optional 500 runs only after earlier gates pass and time/budget permit; it exercises worker interruption after physical generation and before settlement.

Record actual request/job completion, p50/p95/p99 from request timestamps, dispatch components, input/output tokens, worker overlap, active/waiting sequences, throughput, GPU samples, retries, deadline attainment and ledger reconciliation. Audits are cumulative; compute per-arm percentiles from the retained stage job IDs and raw request timestamps rather than subtracting cumulative quantiles. Provider logs and raw synthetic evidence stay private and are exported under owner encryption with one-day artifact retention. Full-rental costs include cold/idle/failed work; synthetic captures are not provider cost. Unknown utilization intervals remain unknown. No savings, batching-efficiency or GO claim precedes measured results.

The reviewed execution entrypoint is `python -m scripts.hosted_experiment --execute`, invoked by the protected host with its approved session/connection files. It uses the existing `scripts.gpu_experiment run --execute` per arm and existing read-only audits; no operator needs to drive stages from a local terminal after initial setup.

## Cleanup and requested authority

After explicit one-pod rental approval, dispatch the reviewed independent watchdog with this exact random experiment identity, the $1/$0.61/45-minute plan and control run/attempt `40380907617`/`1`. Obtain GitHub's required owner review, then verify authenticated armed status before creating the one pod. Add the exact CPU run/attempt, armed cutoff and watchdog run/attempt metadata to its private payload; verify the independent watchdog binds immediately after creation.

The watchdog retains time/budget/quote/identity guards and can terminate the bound pod when the CPU job completes. This early-completion path is contract-tested but not yet live-proven; a public GitHub API outage leaves the independent deadline guard in force. Historical live DELETE permission proof exists; a fresh GET is not DELETE proof. On critical errors, stop work and terminate this exact pod promptly. Verify authenticated provider 404 and absence of experiment storage, then reconcile posted GPU/disk billing and remaining credits. No replacement pod or automatic provisioning is authorized.

**Required approval:** exactly one A40 in CA-MTL-1 under the displayed $0.601/hour quote, conservative $0.61/hour ceiling, $1 internal allocation inside the original total $10, independent 45-minute cutoff and gated workload above, subject to fresh unchanged stock/price/balance/host checks and armed cleanup.
