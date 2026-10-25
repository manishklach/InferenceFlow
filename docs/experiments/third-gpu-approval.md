# Third GPU experiment — one-Pod approval request

October 25, 2026, 13:33 PDT. **Preparation only: no GPU is running or provisioned.** Fresh catalog/inventory reads returned L4 Secure LOW stock in US-MO-2, an empty Pod inventory, and no network volumes. The deployment form showed $9.67 account credit. Availability and quote must be checked again before create; they are not reservations.

## Proposed rental and cost

| Item | Configuration / quoted cost |
|---|---|
| GPU | One NVIDIA L4 24 GB, RunPod Secure Cloud, US-MO-2 |
| Compute | $0.59/hour from GPU catalog and deployment form |
| Storage | 80 GB temporary container disk, $0.011/hour from deployment form |
| Combined rental | **$0.601/hour** from quoted line items; rounded UI total is $0.60 |
| Persistent storage | None; no disk/network-volume mounts |
| CPU control plane | Existing standard GitHub-hosted runner in public repository; no paid runner selected |
| Projection | 30–60 minutes: $0.3005–$0.601; 90-minute target: $0.9015 |
| Independent time cutoff | 110 minutes from watchdog arming; about $1.10184 at 110 rented minutes |
| New internal guard allocation | **$2**, within original $10 combined ceiling; not a RunPod-enforced spending cap |

No credit purchase, tax-bearing new payment, paid persistent storage, larger runner or additional paid provider is proposed. Quote projections are not posted invoices. Existing approximately $0.33 account spend remains part of the original budget. The form does not itemize a new tax charge; do not claim a provider hard cap or immunity to delayed billing/outages. Standard GitHub runner compute is free for this public repository; ciphertext artifact storage has separate allowance/retention rules. Evidence artifacts are small and retained one day; paid overages are not enabled by this experiment.

## Deployment and control-plane readiness

GPU image: `vllm/vllm-openai@sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33` (vLLM 0.8.5). Model/tokenizer: Qwen/Qwen3-4B, revision `1cfa9a7208912126459214e8b04321603b3df60c`. BF16, max context 10,240, maximum four sequences, memory fraction 0.85, thinking and prefix caching off. A previous L4 run loaded these weights and observed four active sequences on the short/medium workload. Four simultaneous maximum-context requests remain unvalidated.

No public Pod ports, SSH, Jupyter, global networking or persistent storage. vLLM binds to 127.0.0.1 only. The outbound worker receives the approved HTTPS origin and a scoped bootstrap credential, never the database, Auth0, metrics/tenant or RunPod management keys. Reviewed bootstrap/source hashes and unique experiment ownership are retained in the private candidate review; no credential-bearing payload is committed.

The [real CPU-host run](https://github.com/manishklach/InferenceFlow/actions/runs/40230155968) is holding independently of this PC. Verified HTTPS origin: `https://pollution-girlfriend-cove-mostly.trycloudflare.com`. Readiness returned vLLM mode; authenticated models matched model/tokenizer SHA; operator report confirmed baseline flags, max-inflight four, uncalibrated estimator, disabled beta/Stripe/provisioning. Anonymous wallet and invalid worker registration returned 401. The owner approved the exact callback; Auth0 save succeeded, owner login returned status ok, and the signed-in owner's wallet remained zero. A separate disposable synthetic experiment tenant has test credits; those are not payments or GPU funding.

There are **zero real workers currently**. Real engine health, GPU fit, live worker canary and telemetry coverage are post-creation smoke gates, not pre-creation claims. The private connection handoff decrypted successfully. The mock rehearsal already demonstrated ten completed requests, exactly-once accounting and encrypted export/decryption; those results are not real GPU measurements.

The host's conservative expiry is approximately 15:49 PDT (150 minutes from startup). Require at least 120 minutes of host lifetime remaining before watchdog arming and enough approved creation-window time. If approval is delayed or the host/quote changes, refresh readiness rather than use an expiring session.

## Independent cleanup procedure

The existing protected `gpu-experiment` workflow uses only its dedicated cleanup secret, owner deployment review and main-only policy. Its exact-Pod deletion/cancellation finalizer was live-tested in earlier experiments; this does not prove a new job is armed. **No new watchdog is armed yet.**

After explicit one-Pod approval, dispatch the exact reviewed identity/marker/name cleanup plan with $0.601 all-in hourly input, zero fixed cost and $2 guard allocation. Require the owner's GitHub deployment review, successful current authentication and a fresh `armed=true` heartbeat. Never create a Pod before that read succeeds. The reviewed creation window is ten minutes from arming. The watchdog binds only the matching identity, detects cost above quote, and terminates no later than 110 minutes from arming. Prior live delete proof remains historical evidence; provider/GitHub-wide outages and permissions changing remain risks.

Stop load at 90 minutes or earlier on errors/evidence gaps; trigger the independent finalizer immediately after testing or any critical failure. Verify fresh Pod GET 404, no matching active/stopped Pod, and no network/persistent storage. Preserve API results and operator-side audits during execution; request the host's encrypted final database export before the temporary runner shuts down. Missing export is a reported failure, never inferred zero drift. Reconcile posted GPU/disk billing and remaining credits after termination. No paid storage should remain because none is created.

## Workload and pass/fail gates

Follow [the third-experiment runbook](third-gpu-experiment.md). At most **910 requests total**: 10 smoke, baseline/adaptive/adaptive/baseline 100-request clean arms with identical prepared workload bytes, then one gated 500-request controlled-interruption validation using the selected configuration. Use separate run IDs, verify actual flags and consume a fresh live worker challenge after each policy switch. The 500 fault arm is not a clean throughput comparison. Run it only after all earlier audits and coverage pass and sufficient reserve remains. No 1,000-request arm is planned.

Commands and prepared hash manifest are in the runbook. Measure full rented lifetime, successful input/output tokens, latency/deadline attainment, dispatch components, overlapping requests/active sequences, queue depth, utilization with missing intervals explicit, retries, unique usage/captures and zero ledger drift. Calculate posted GPU/disk cost per million successful output tokens, distinguish quality-passing outputs and any separately allocated operating costs, and do not claim adaptive savings from a single best result or mismatched hosted model price.

**Requested authorization:** create exactly one matching L4 Secure Pod at no more than $0.601/hour quoted GPU+temporary-disk rental, with a $2 internal allocation inside the original $10 budget, only after the independent watchdog is freshly armed and all host/stock/quote checks still pass. This authorization would not enable automatic provisioning, live payments, public beta, another Pod or a replacement rental after a critical failure.
