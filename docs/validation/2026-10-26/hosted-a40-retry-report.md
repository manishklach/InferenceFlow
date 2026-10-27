# Hosted A40 retry: HTTP startup failure, independent cleanup verified

October 26, 2026. **NO-GO for another paid experiment until startup read resilience and diagnostic coverage are verified. No inference-performance result was produced.**

## What happened

After the networking-response fix passed main CI, the actual retained RunPod response passed offline replay. [No-GPU rehearsal 40385331611](https://github.com/manishklach/InferenceFlow/actions/runs/40385331611) passed 40/40 mock requests across sequential/baseline/adaptive/baseline, with reconnect and billing-audit gates. These checks did not prove the real provider/control-plane HTTP path.

The owner separately approved replacement CPU host [40385972361](https://github.com/manishklach/InferenceFlow/actions/runs/40385972361), one A40 rental, and independent watchdog [40386640164](https://github.com/manishklach/InferenceFlow/actions/runs/40386640164). Real-mode readiness, pinned model revision, invalid worker-auth rejection, anonymous wallet rejection and no-worker admission without wallet mutation passed. The displayed balance was $8.24; the quote remained $0.59/hour GPU plus displayed $0.011/hour temporary disk. Guard rate $0.61/hour; allocation $1 within the original $10.

Pod `k9phtgkzl01tgi` was created at **19:27:28.610 UTC** in CA-MTL-1: one A40, 80 GB temporary disk, no ports, mounts or enabled global networking. The watchdog armed at 19:26:45 UTC with a 20:11:45 UTC cutoff and bound at 19:27:37 UTC. The fixed networking verifier accepted the live shape and wrote the private session receipt.

The driver then exited with `HTTPStatusError` during startup. Its encrypted receipt retained only the error type, so **the failing endpoint and HTTP status cannot be established from this attempt**. Do not describe it as a proven 502, a provider authentication failure or model incompatibility. The retained provider-log file was empty; direct operator log reads showed image download/extraction, but hosted SSE ingestion was not proven.

## Cleanup and accounting

The watchdog observed `control_run_finished: true` at **19:28:49.825 UTC**, initiated its approved early cleanup and confirmed absence at **19:28:50.958 UTC**. The subsequent operator DELETE and authenticated GET both returned 404. This is live evidence for the control-completion-triggered cleanup path, not a hard-deadline/outage-path test. No replacement pod was created.

Creation to independent absence confirmation was at most **82.35 seconds**, approximately **$0.014 at the guard rate**. This is an estimate, not an itemized provider bill; initial billing reads returned no records, which does not establish zero charge. No persistent/network storage was requested. The encrypted PostgreSQL snapshot contains **zero jobs, zero job requests and zero usage records**, and only the initial synthetic wallet-funding entry. No inference capture occurred.

## Changes and next gate

Billing addendum, October 27: RunPod's daily read now reports GPU **$0.013441183604300022**, disk **$0**, total **$0.013441183604300022** for this exact pod. These are the currently posted amounts, separate from the earlier upper-bound estimate.

- Experiment GET reads retry only transport errors and HTTP 429/502/503/504, at most three attempts with one- and two-second pauses. Authentication errors fail immediately. Job submissions and cancellation mutations are never retried by this helper. Existing experiment cutoffs remain unchanged.
- Owner-encrypted failure receipts retain status, method, host and path without query strings, headers or response bodies. Collector failures receive a separate private receipt rather than silently leaving an unexplained empty log file.
- A real-driver startup test uses the actual disabled-networking response shape and a temporary 503 followed by a compatible worker, then reaches the plan boundary. Contract tests verify exhaustion, immediate 401 failure and private stream-error diagnostics. These are deterministic tests, not GPU results.

Twelve focused checks and repository lint passed locally. Full CI must pass before merge. Do not claim these changes identify the previous HTTP status or prove hosted SSE permissions; those remain explicit validation gaps. The next preparation should verify authenticated provider reads and failure diagnostics without renting. Another paid pod requires a fresh verified host, quote, armed cleanup and explicit one-pod approval. Public beta, Stripe and automatic provisioning remain disabled; wallet implementation is unchanged.
