# H100 follow-up proposal — no rental authorized by this document

Prepared October 25, 2026 PDT. Prefer H100 over B200 for this controlled follow-up. The vLLM [0.8.5 hardware requirements](https://docs.vllm.ai/en/v0.8.5/getting_started/installation/gpu.html) explicitly include H100. The exact container/model still require a live readiness canary and smoke test on the selected hardware; catalog support does not prove that this image has booted there.

## Current observations, not a locked offer

- H100 NVL Secure catalog: $3.19/hour, LOW stock in US-KS-2. The console nevertheless reports the instance unavailable for the inspected deployment shape. Do not attempt repeated paid creates or subscribe to automatic deployment.
- H100 SXM Secure console: $3.99/hour GPU plus $0.011/hour for 80 GB container disk = **$4.001/hour**. Its deployment button is available. Re-read per-location stock and exact shape immediately before approval; no location is selected by this proposal.
- H100 SXM Community: no stock in the fresh CUDA-floor-filtered catalog. Its listed price is not a deployable quote.
- Last observed account balance: $9.62; A40 posted billing was not yet available. Reconcile pending charges and verify balance again before approval. No empty billing response is treated as zero spend.

## Proposed safeguards and scope

One H100 SXM, no public ports, no persistent/network storage, 80 GB temporary disk, same pinned model/tokenizer/container as the A40 report. BF16, context 10,240, four vLLM slots, memory utilization 0.85, thinking/prefix cache disabled. Worker hard capacity remains four; tenant limit is one for sequential and four for concurrent. Hardware changes are a confound in comparisons with L4/A40.

Target 20–30 rented minutes: approximately **$1.33–$2.00** at the inspected all-in rate, including cold start and idle time. Propose a **45-minute independent termination deadline from watchdog arming**, with a 30-minute normal stop target and **$6 internal allocation**, remaining inside the original total $10 ceiling. A 45-minute quoted lifetime is about $3.00; the guard conservatively reserves a full hour ($4.001), below 70% of $6. This allocation is neither a spending target nor a RunPod hard cap. No paid operation is approved until pending costs, balance, exact location/quote, host health, reviewed cleanup code and a fresh armed authenticated watchdog are verified.

The reviewed cleanup-plan schema now optionally accepts `max_runtime_minutes` from 15 through 110. Existing plans retain their 110-minute default/two-hour rounded reserve. Shorter deadlines are explicit per-experiment approvals; they cannot extend the original ceiling. Independent deletion, cancellation finalizer, exact pod identity matching, over-quote deletion and fresh 404 confirmation remain required. Provider outages/GitHub outages can defeat a requested termination time; no software budget ceiling is claimed.

Proposed tests: smoke ten with ≥90% compact telemetry coverage and PostgreSQL audit; identical sequential 100; repeated baseline/adaptive/adaptive/baseline 100 arms; then **at most 500** controlled-interruption requests if every prior gate passes and enough cutoff/budget remains (maximum 1,010 requests across all stages). The optional stage is skipped if timing, billing, recovery or telemetry gates fail. All policy switches and audits use the [trusted hosted controls](hosted-policy-controls.md), followed by a fresh real engine canary before each load arm. No wallet algorithm or product feature changes are included.

Measure full provider lifetime, successful input/output tokens, request completion percentiles, dispatch components, idle/failure overhead, engine active/waiting sequences, worker overlap, GPU utilization with explicit unknown intervals, retries, 60-minute attainment, unique settlement and fully loaded provider cost per million successful output tokens. Use posted provider billing when available; keep estimates separate. Preserve raw synthetic evidence encrypted, terminate and freshly verify removal, and remove ephemeral storage. Do not infer savings from engine-only throughput.

## Remaining approval sequence

1. Complete updated CI and no-GPU mailbox/Compose rehearsal; merge reviewed code.
2. Owner-approve a fresh protected CPU-host job. Verify its HTTPS/auth boundaries and exercise actual main-branch commands without a GPU. Approve only the new exact Auth0 callback if owner login is needed.
3. Recheck account, model/image, live stock/location and complete quote. Present a final one-pod request including the 45-minute cutoff/$6 allocation and exact workload limits.
4. Obtain explicit rental approval and owner-review a fresh independent watchdog deployment. Confirm its armed heartbeat before creating exactly one pod.

No H100/B200 pod has been created. Public beta, Stripe live payments and automatic provisioning remain disabled.
