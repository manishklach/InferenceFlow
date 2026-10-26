# H100 real inference result: partial experiment

**110/110 real requests succeeded, with 110 unique usage/capture records and zero wallet drift. The planned concurrent/adaptive comparisons and 500-request interruption test did not run. NO-GO for savings, larger-load recovery or public-beta claims.**

One approved H100 SXM 80 GB ran on RunPod Secure Cloud CA-MTL-1, pod `4fagriwqkl4x5p`. Qwen3-4B/tokenizer revision `1cfa9a7208912126459214e8b04321603b3df60c`, pinned vLLM 0.8.5 image, BF16, context 10,240, four sequence slots. No public ports or persistent volumes were configured. The worker connected outbound to the authenticated GitHub-hosted control plane; beta, Stripe and provisioning remained disabled.

| Stage | Successful requests | Accepted-to-last-terminal job time | Successful input / output tokens |
| --- | --- | --- | --- |
| Baseline smoke | 10/10 | 3.069015 seconds | 3,618 / 349 |
| Sequential | 100/100 | 106.291862 seconds | 36,270 / 3,478 |
| Matched concurrent/adaptive arms | Not admitted | Unmeasured | Unmeasured |
| Controlled-interruption 500 | Not admitted | Unmeasured | Unmeasured |

These are whole-job times, not request p95/p99. Total successful tokens: 39,888 input and 3,827 output. Both accepted jobs completed within 60 minutes. There were 110 execution attempts; no controlled worker fault/retry was exercised in this H100 run. Four overlapping worker HTTP requests were observed in the smoke stage. The short smoke window's sampled active-sequence gauge did not capture a positive value; H100 continuous-batching efficiency is not established by this run.

The first ten requests passed the joint compact engine/hardware coverage gate: 100% over their 3.069-second job window, with 21.34% time-weighted GPU utilization on those covered intervals. This is **not full-rental utilization**. Hardware identified NVIDIA H100 80GB HBM3 with approximately 81,559 MiB visible; weights loaded in 7.5552 GiB. Container bootstrap was recorded at 08:34:04 UTC, worker environment at 08:34:28, model download at 08:34:29–08:34:34, and engine launch at 08:34:35. API creation was 08:31:11.563 UTC. Image-pull/allocation boundaries and later telemetry are incomplete; unknown intervals are not treated as zero utilization.

## Accounting and actual posted cost

The owner-encrypted final PostgreSQL export was downloaded and decrypted only in protected local runtime storage. A read-only offline COPY-snapshot check found 110 succeeded requests, 110 attempts, 110 usage records, 110 unique captures, matching 5,203 micro-USD usage/capture totals and zero wallet-versus-journal drift. The live host's read-only cumulative stage audit 6 independently passed for all 110 requests. Test-tenant charges of **$0.005203 are synthetic settlement, not provider cost or revenue**.

The RunPod billing API subsequently posted **$1.3611973375082016 GPU + $0.002777777728624642 disk = $1.3639751152368262** for this pod's 08:00–09:00 UTC bucket. No CPU charge was returned. Based on the entire posted pod bill and only successful output tokens, cost was **$356.41 per million successful output tokens**. It includes the experiment's cold/idle overhead and is not a steady-state serving estimate. Public/free staging infrastructure does not establish production control-plane costs. No comparative economic advantage is demonstrated.

## Termination and missing stages

The independent watchdog [40291400132](https://github.com/manishklach/InferenceFlow/actions/runs/40291400132) armed at 08:28:48 UTC, bound at 08:31:21 and had a 09:13:48 UTC cutoff. It confirmed the pod absent at **08:52:06 UTC (1:52 AM PDT)**. A fresh authenticated provider read later also returned 404. The preceding watchdog samples showed no deadline, budget or quote-overrun trigger. **The available evidence does not establish what initiated termination; do not attribute it to the deadline or claim this was a live deadline-triggered DELETE proof.** Provider logs were unavailable after deletion.

The recorded operator execution stopped after sequential completion and a request to transition back to baseline. No subsequent comparison workload was admitted. The CPU host later completed its bounded lifetime, sealed final database/audit evidence and shut down successfully. This partial run must not be presented as a completed benchmark or silently resumed on a new billable pod. Existing saved telemetry ends before pod removal, so full-lifetime GPU utilization cannot be reconstructed.

Next: determine the termination initiator if provider/account audit evidence is available; move the bounded stage driver, telemetry collection and durable gate checkpoints into hosted execution so agent/workstation interruptions cannot leave idle gaps; rehearse without GPUs; then obtain a fresh one-pod quote and approval for the missing comparisons. Keep the independent cleanup job separate. No replacement GPU is authorized by this report.
