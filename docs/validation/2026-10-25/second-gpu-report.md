# Second real GPU experiment — measured results

## Posted billing addendum

A subsequent October 25 RunPod `list_pod_billing` read for exact pod `2p58yft8rurow1` returned one daily record: GPU **$0.21122360602021217**, disk **$0.002777777728624642**, CPU **$0**, total **$0.21400138374883682**. [Raw provider billing response](second-gpu-evidence/posted-billing.json). This supersedes the pending-bill status below while preserving the original estimate and report provenance. Dividing the posted total by 14,135 successful output tokens gives **$15.13982 per million output tokens**, including the entire rental's GPU/disk charges. It excludes any separate control-plane costs and is not a quality-adjusted commercial margin. A fresh Pod inventory was empty; the console showed $9.67 balance. Account balance is rounded and is not a substitute for itemized billing reconciliation.

## Original experiment report

October 25, 2026, 05:55–06:16 PDT. **410 accepted requests succeeded; the 1,000-request stage was not admitted. The GPU is terminated. NO-GO for commercial launch, adaptive-savings claims or 1,000-request validation.** Small-run execution, real batching, controlled worker recovery and customer accounting have useful positive evidence.

## Configuration and provenance

One RunPod Secure Cloud NVIDIA L4 24 GB in US-MO-2, pod `2p58yft8rurow1`; 80 GB ephemeral disk, no public ports, no SSH/Jupyter/global network or network volume. GPU quote $0.59/hour plus disk $0.011/hour. vLLM listened only on loopback and the worker connected outbound to authenticated staging HTTPS. Public beta, Stripe and automatic provisioning remained disabled. Customer wallet/rate/settlement algorithms were unchanged; charges used existing synthetic test credits, not real payments.

Model/tokenizer: Qwen/Qwen3-4B revision `1cfa9a7208912126459214e8b04321603b3df60c`. vLLM 0.8.5 image digest `sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33`. BF16, 10,240 context, maximum four resident sequences, memory utilization 0.85, thinking/prefix caching disabled. Startup loaded 7.5552 GiB of model weights, and four active sequences were observed. This validates the tested short/medium workloads, not four simultaneous maximum-context requests.

Control source was merged PR14 plus the experiment-loader fix in PR15. The GPU used the reviewed literal source overlays and immutable base checkout; payload hashes are retained privately. All three clean 100-request arms used the same workload SHA256 `1c2cd763e6c3a2d7587de5586342808daa3714a5a023538632f6414ca803a3f5`. Order was sequential → baseline → adaptive. No randomized repeats or quality-equivalence assessment were performed; even temperature-zero outputs varied slightly in length.

[Machine-readable report](second-gpu-evidence/report.json) and per-stage JSON include timing decomposition, observed settings, telemetry coverage and billing audits. Raw provider logs and synthetic request/results remain in ignored private runtime evidence; no credentials are published.

## Measured requests and batching

| Arm | Success | Acceptance → last result | Request p50 / p95 / p99, s | Input / output tokens | Successful output tokens/s* | Covered GPU utilization |
|---|---:|---:|---|---:|---:|---:|
| Smoke baseline | 10/10 | 9.524 s | 6.165 / 9.524 / 9.524 | 3,618 / 346 | 36.33 | 32.12% |
| Sequential | 100/100 | 236.222 s | 121.760 / 225.071 / 234.152 | 36,270 / 3,455 | 14.63 | 54.43% |
| Baseline concurrent | 100/100 | 68.944 s | 35.418 / 65.825 / 68.030 | 36,270 / 3,445 | 49.97 | 74.98% |
| Adaptive concurrent | 100/100 | 80.643 s | 47.194 / 78.257 / 80.422 | 36,270 / 3,457 | 42.87 | 64.86% |
| Controlled interruption, adaptive | 100/100 | 87.022 s | 46.784 / 82.792 / 85.936 | 36,270 / 3,432 | 39.44 | 73.93% |

*Denominator is each arm's actual acceptance-to-final-result interval, including its queue waits. It differs from the runner's elapsed time, which additionally includes canary, HTTP observation and export overhead. Input throughput is available from input tokens divided by the same interval. Full-rental throughput is only ~115.35 successful input and ~10.96 output tokens/s.

All 410 accepted requests completed within their actual 60-minute target. This is an observed result on these samples, not an SLA or a 1,000-request result. There were no unsuccessful terminal requests in admitted stages. API policy restarts between clean arms preserved the worker/engine, validating the bounded transient-control-plane recovery path on real hardware.

Worker HTTP overlap and engine active-sequence telemetry both reached four in concurrent arms; sequential reached one active engine sequence. Every admitted stage had 100% valid engine+hardware coverage over its acceptance-to-terminal window, satisfying the first-10 ≥90% gate. The initial broad provider export was truncated before the smoke window; a targeted fetch recovered it before progressing. Missing pre-engine metrics are explicit, not zero. Provider logs are subject to retention/truncation, so raw disk telemetry is not presumed exported after termination.

Baseline concurrent was 3.43× faster by completion time than sequential. Adaptive took **16.97% longer** than baseline (80.643/68.944−1), with lower observed output throughput and utilization. Adaptive's cap was two at the beginning of that arm; it later reached four. This run does not establish that the policy itself caused the entire difference: order, warmup and one replicate limit attribution. There is no adaptive economic advantage demonstrated. Active sequences and prefill-inclusive iteration-token counters are retained; they are not a decode-only batching-efficiency percentage.

## Recovery and exactly-once customer billing

The opt-in fault fired after the fifth matching engine success and before finalization. The worker exited with code 75 and restarted once, preserving vLLM. Four lost leases were retried. The fault arm ended with 100 successful usage records and 100 unique capture sources, not 104 charges. All stages together: **410 unique usage records, 410 unique capture sources, 19,351 micro-USD of synthetic captures**. Reconciliation immediately after the fault arm returned `{"drift":[]}`. Inference may repeat physically; only customer settlement is exactly once under the tested recovery.

The next policy switch exposed a separate **local staging-supervisor failure**: its `docker compose ps` command returned nonzero, propagated an unhandled `CalledProcessError`, and the supervisor's `finally` stopped the control-plane containers and tunnel. The CLI stderr was not retained by that wrapper, so the underlying Docker failure is unproven. The concurrently running migration then failed resolving the stopped PostgreSQL hostname. Do not confuse this later local-host outage with another vLLM or billing failure.

The 1,000 loader failed on HTTPS 530 while retrieving models, before any submission intent/API job creation. It admitted **zero** requests. Further load stopped and independent cleanup was invoked. We did not restart hosting, rent a replacement GPU or try to spend the remaining budget. Next experiment requires durable supervision or bounded Docker-read retries with retained diagnostic stderr, a local fault test and renewed staging/watchdog/quote approval.

## Cold start, lifetime and costs

Provider creation was 12:55:11.738 UTC; independent termination confirmation was 13:16:40.885666 UTC. Full rented lifetime upper bound: **1,289.148 seconds (21.49 minutes)**. Including startup, canaries, idle gaps, retries, unsuccessful setup and teardown, the quoted-rate estimate is **$0.215216**, or **$15.23/M successful output tokens** across 14,135 output tokens. These are not provider-invoice figures. The two initial pre-submission loader checks accepted no requests but their rented time still counts.

| Cold-start component | Observed duration |
|---|---:|
| Create request → first provider pull observation | 1.962 s, observed boundary rather than precise physical allocation |
| Provider image pull | 135.000 s |
| Container worker bootstrap | 26.691 s |
| Pinned model acquisition/cache check | 25.625 s |
| Engine initialization, inclusive | 150.504 s |
| Model weight loading, inside initialization | 1.830 s |
| Compilation, derived from engine report | 53.810 s |
| Compilation report → health readiness | 30.108 s |
| Provider creation → engine health | 342.125 s |

Do not sum inclusive initialization with its children. Full hardware coverage is 1,015.650 seconds (78.78%); 273.498 seconds remain unknown. Time-weighted GPU utilization on covered intervals is 33.06%. **Full-lifetime effective utilization is unknown**, not 33.06%. Stage coverage was complete, but allocation and final log-retention gaps prevent a whole-rental utilization claim.

The first two fresh billing reads after termination returned no record for this pod; that means **pending**, not free. The RunPod console subsequently showed **$9.67 remaining**. Approximate remaining original $10 credit using prior posted spend $0.117450 plus this quote estimate is $9.667334, before delayed adjustments/tax. Refresh the posted bill for actual itemized charges. Original budget was $10; independent guard allocation $8, all-in ceiling $0.65/hour and 110-minute deadline remained below threshold. No provider-enforced account cap was assumed.

The independent GitHub [watchdog finalizer](https://github.com/manishklach/InferenceFlow/actions/runs/40194830746) succeeded at 13:16:40 UTC. Fresh RunPod GET returned 404; complete pod and network-volume inventories were empty. No persistent storage was created. Workflow cancellation was intentional and is not a cleanup failure.

## Economics and hosted comparisons

The baseline's active-window GPU+disk allocation is ~$0.01151 per 100 requests, versus $0.004718 of synthetic customer captures at existing test rates. Even ignoring startup/idle/control-plane overhead, that is ~2.44× the test-rate receipts. At the observed warm service rate (~5,222 requests/hour), test-rate receipts would be ~$0.246/hour versus $0.601/hour rental. **More volume alone cannot close this steady-state deficit at these test prices and workload**, unless throughput, hardware cost or selling price changes. This extrapolation is not a measured sustained hourly result.

For a hosted input/output price pair Pi/Po per million, comparable workload value is `(input_tokens*Pi + output_tokens*Po)/1e6`. Rental breakeven requires that value exceed full GPU lifetime cost plus control-plane/support costs. If warm serving cost already exceeds the comparable API charge per request, there is no finite volume breakeven under unchanged assumptions. No quality-matched equivalent Qwen3-4B hosted endpoint was verified in the sources below, so there is **no apples-to-apples hosted savings or breakeven-volume claim**.

- [Together pricing](https://www.together.ai/pricing), checked October 25: listed Llama 3 8B Instruct Lite at $0.14/M input and $0.14/M output. That is a different model, tokenizer, quality and serving configuration. Qwen3-4B was not found in the reviewed pricing table. No paid hosted request was sent.
- [AWS Bedrock pricing](https://aws.amazon.com/bedrock/pricing/), checked October 25: Qwen3 32B in Sydney listed $0.1545/M input and $0.6180/M output standard, $0.0773/$0.3090 batch. These differ in model size, location and service terms; the reviewed table did not establish the pinned 4B configuration. No AWS infrastructure or paid call was created.

## Before/after and decision

The first attempt's baseline 100 completed in 71.294 s; this baseline took 68.944 s (~3.3% shorter), with slightly different output lengths and one run each. The earlier adaptive arm failed after a 502; this time all clean arms and the controlled worker interruption completed with one charge per successful request. Full-rental estimated output cost improved from first posted $28.87/M to second estimated $15.23/M, but different volumes, idle time and bill provenance prevent attributing that change to scheduling.

**GO:** small-run engineering evidence for private inference, measured concurrency/continuous batching, live canary admission, worker recovery and ledger reconciliation. **NO-GO:** public beta, production reliability, a cheapest/adaptive-savings claim and the 1,000-request milestone. Resolve staging-supervision diagnostics, finish an independently approved large matched run, reconcile the posted bill and validate quality-matched economics before revisiting the decision. No new extraction features are authorized or built; [the three customer hypotheses/interview guide](../../research/auditable-extraction-discovery.md) remain discovery work.

The root repository still has no LICENSE. A permissive license with an explicit patent grant (Apache-2.0) is a candidate for a developer-platform strategy; a stronger copyleft strategy has different adoption/service implications. This is a decision for the owner with appropriate legal review, not a moat established by this experiment. **No license has been selected or applied.**
