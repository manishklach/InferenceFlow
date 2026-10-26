# Third GPU experiment: A40 smoke validation

Run on October 25, 2026 PDT (provider timestamps October 26 UTC). This is real GPU evidence, not a simulation. **GO for the observed ten-request baseline pipeline; NO-GO for economics, adaptive savings, larger-load reliability or public beta.**

## Configuration and safeguards

Exactly one approved RunPod Secure Cloud NVIDIA A40, CA-MTL-1, pod `vio7n9ucbcyh6e`, 80 GB ephemeral disk, no public ports or network volumes. Quote: $0.59 GPU/hour + $0.011 disk/hour = $0.601/hour. Qwen3-4B model and tokenizer revision `1cfa9a7208912126459214e8b04321603b3df60c`; vLLM 0.8.5 image digest `sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33`. BF16, context 10,240, four active sequence slots, memory utilization 0.85. vLLM listened on loopback only; the worker connected outbound to the authenticated HTTPS control plane.

The protected [independent watchdog](https://github.com/manishklach/InferenceFlow/actions/runs/40278438294) authenticated, armed at 06:13:44 UTC and bound at 06:16:07 UTC. The [real CPU host](https://github.com/manishklach/InferenceFlow/actions/runs/40239096286) ran on GitHub. Public beta, Stripe, automatic provisioning and adaptive dispatch stayed disabled. Fresh engine-canary proof gated admission; heartbeat alone was insufficient.

## Measured results

| Metric | Observation |
| --- | --- |
| Requests | 10/10 succeeded, no request failures |
| Successful input / output tokens | 3,618 / 358 |
| Submission-to-job-completion | 5.230020 seconds |
| Driver duration, including canary/poll/result reads | 12.375 seconds |
| Driver-window input / output tokens per second | 292.36 / 28.93 |
| Peak worker HTTP overlap / sampled active vLLM sequences | 4 / 4 |
| Smoke telemetry coverage | 100% over the 5.230020-second job window |
| GPU utilization on covered smoke intervals | 60.85%, time weighted |
| Accounting | 10 attempts, 10 usage records, 10 unique captures; zero wallet drift |
| Synthetic customer charge | 476 micro USD ($0.000476), not provider cost or revenue |

Coverage uses the existing one-second compact collector and 1.5-second maximum sample hold. Startup samples without engine metrics are invalid for this joint coverage gate, not zero utilization. The smoke utilization figure is **not full-rental utilization**. Four active sequences prove batching occurred, not that it was efficient or cheaper than another service. No worker interruption was injected in this run.

Private owner-encrypted PostgreSQL evidence was exported before the CPU host shut down. Offline read-only COPY-snapshot reconciliation verified usage/capture totals and each wallet against its journal. This is a snapshot audit, not a rerun of the PostgreSQL audit CLI on a live server. Raw credentials, SQL, prompts and provider logs remain under ignored, protected local runtime storage; they are not published here.

## Startup, cost and termination

Provider creation: 06:15:58.088 UTC. Container bootstrap: 06:20:09 UTC. Worker environment ready: 06:20:34 UTC. Model download: 06:20:34.959–06:20:41.841 UTC. Engine launch: 06:20:42 UTC. Weights occupied 7.5552 GiB. The configured engine became healthy and registered before admission. Compilation and warm-up occurred during startup. Allocation, transfer and extraction boundaries are not all independently measurable from the available logs.

Termination was requested at 06:24:34 UTC, followed by an authenticated fresh `get_pod` returning 404 and an empty network-volume inventory. Both GitHub jobs finished after cancellation; the CPU host exported its encrypted final database first. Approximately 8.60 minutes elapsed from provider creation to termination request: **about $0.0861 at the quoted all-in rate**, an estimate pending posted billing and final provider billing boundaries. The billing API initially returned no posted records; that does not mean zero cost. Estimated fully loaded cost is roughly **$240 per million successful output tokens** for this tiny cold-start-dominated smoke run; it is not a production unit-cost estimate.

## Why the larger stages did not run

The hosted control plane lacks an existing authenticated remote mechanism for idle-boundary sequential/baseline/adaptive policy changes. This should have been identified before rental. Rather than add a new control feature while a GPU was billing, the experiment stopped after the smoke test. The repeated matched 100-request arms and gated 500-request interruption stage were **not run**. No adaptive improvement or real larger-load deadline attainment can be inferred. The A40 also differs from the previous L4, so this is not a controlled before/after performance comparison.

Before another rental, prepare and rehearse policy transitions and audit/export gates with no GPU, then obtain a fresh quote and independent cleanup approval. The operator's request to consider H100/B200 does not create another pod. The live Secure catalog at approximately 11:25 PM PDT quoted H100 NVL $3.19/hour, H100 SXM $3.99/hour and B200 $7.99/hour GPU-only; 80 GB disk would add the separately verified storage quote. H100 PCIe had no matching stock. These are catalog observations, not locked deployment offers. B200 compatibility with the pinned image remains unverified. Prefer an H100 comparison after the execution controls are ready; do not spend more merely to demonstrate hardware speed.
