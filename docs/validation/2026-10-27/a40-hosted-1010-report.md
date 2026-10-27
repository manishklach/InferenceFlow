# Complete hosted A40 experiment: 1,010 real requests

October 27, 2026. **1,010/1,010 requests succeeded, 1,010 receipts verified, zero wallet drift, and the independent watchdog terminated the pod. Adaptive did not outperform baseline concurrency.** GO for supervised private execution/audit demonstrations; NO-GO for a cheapest-inference claim, adaptive savings claim, public beta, live payments or automatic provisioning.

## Evidence and reproducibility

[CPU/driver run 40485130409](https://github.com/manishklach/InferenceFlow/actions/runs/40485130409), source `b0f419789e191c5db3413d37a1f351ec94a6a9e0`, completed every planned stage. [Independent watchdog 40485215398](https://github.com/manishklach/InferenceFlow/actions/runs/40485215398) authenticated, bound the exact resource and confirmed termination. The owner-encrypted final artifact was downloaded and decrypted locally. Raw prompts/results, receipts, provider logs and SQL remain private; this report and its [aggregate JSON](a40-hosted-1010-metrics.json) publish measurements only. The artifact's remote retention is one day; owner-local evidence is retained separately.

Hardware: one NVIDIA A40 48 GB, RunPod Secure CA-MTL-1, pod `aal5d2kold5svl`; temporary 80 GB disk, no public ports, SSH, Jupyter or persistent/network storage. vLLM was loopback-only with outbound authenticated worker HTTPS. Model/tokenizer: Qwen/Qwen3-4B revision `1cfa9a7208912126459214e8b04321603b3df60c`; vLLM 0.8.5 image digest `sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33`. BF16, context 10,240, four sequences, memory target 0.85, thinking and prefix cache off.

Five matched 100-request arms used exactly the same workload SHA-256 `1c2cd763e6c3a2d7587de5586342808daa3714a5a023538632f6414ca803a3f5`: sequential, baseline-a, adaptive-a, adaptive-b, baseline-b. The workload mixes 80% short and 20% medium synthetic logistics summaries, temperature 0, top-p 1, and output limits 128/256. Then a separately gated 500-request workload exercised interruption. The total 1,010 is 10 smoke + five 100 arms + 500 interruption requests; it is not a single 1,000-request job or 1,000 requests per policy.

Every admission required a fresh engine challenge. Each completed stage passed SQL settlement/timing audit and receipt/output verification. All flags remained private-experiment only: public beta, Stripe and provisioning false; estimator calibration false. Sequential tenant cap was one; other arms capped at four. The driver, telemetry, transitions and audits ran on GitHub, independently of the workstation after initial pod creation.

## Measured execution

Times below start at API receipt, include admission/queueing, and end at the last request completion. Request percentiles use per-request SQL timestamps, not client polling or cumulative dashboard quantiles. Token throughput uses successful customer tokens divided by the stage's server span.

| Stage | Requests | Server span, s | Request p50 / p95 / p99, s | Input / output tokens/s | Covered GPU utilization | Peak active sequences |
| --- | ---: | ---: | --- | --- | ---: | ---: |
| smoke | 10 | 5.94 | 4.83 / 5.94 / 5.94 | 609.0 / 57.6 | 18.6% | 4 |
| sequential | 100 | 126.49 | 65.34 / 118.38 / 124.53 | 286.7 / 27.4 | 44.7% | 1 |
| baseline-a | 100 | 44.99 | 23.62 / 42.94 / 44.06 | 806.2 / 76.4 | 65.0% | 4 |
| adaptive-a | 100 | 56.60 | 29.13 / 52.82 / 54.72 | 640.8 / 61.6 | 49.4% | 4 |
| adaptive-b | 100 | 50.02 | 26.50 / 47.94 / 48.99 | 725.2 / 68.9 | 44.4% | 4 |
| baseline-b | 100 | 48.62 | 27.15 / 46.91 / 48.59 | 746.0 / 70.5 | 48.2% | 4 |
| interruption | 500 | 270.87 | 149.23 / 255.71 / 263.88 | 671.1 / 64.6 | 39.9% | 4 |

All 1,010 completed before their measured 3,600-second submission deadline: **100% observed attainment for this workload**, not a general SLA or estimator prediction. Successful usage was **366,758 input and 35,095 output tokens**. The whole rented-lifetime output rate was approximately **27.22 successful output tokens/s**, including startup, idle time, orchestration and interrupted work.

The registered worker hard cap and actual vLLM active-sequence peak were four. This establishes real overlapping vLLM execution; it does not measure GPU kernel efficiency. Pooled baseline output throughput was **73.34 tokens/s**, sequential **27.44**: **2.67× scaling**, or **66.8% of ideal four-slot linear scaling**. This ratio is a defined scaling metric, not theoretical GPU occupancy. Sampled active-sequence means ranged from about 1.1 to 1.6 in the concurrent arms; one-second sampling is coarse for subsecond generations.

## Scheduling comparison and dispatch delay

Baseline mean server span: **46.80 seconds**; adaptive: **53.31 seconds**, **13.9% longer**. Pooled adaptive output throughput was **65.01 tokens/s**; normalized warm rental cost per successful output token was approximately **12.8% higher** than baseline at the same quote. Output lengths differed slightly despite identical inputs and temperature 0. Two repetitions per concurrent policy on one pod are preliminary evidence, not statistical proof across workloads or providers.

For baseline-a, first-dispatch p95 components were admission **1.116 s**, scheduler-not-before **0 s**, queue until scheduler observation **0.736 s**, scheduler capacity/policy wait **40.181 s**, lease assignment **0.000322 s**, lease-to-worker-poll **0.286 s**, and worker receipt-to-engine-start **0.00588 s**. Engine-call p95 was **0.910 s**. The large queue component is consistent with 100 requests sharing four slots; it is not a 40-second single-request engine call. These are component percentiles and must not be added as if they described one request. Full distributions and known-value counts are in the JSON.

No separate application microbatch buffer was added. vLLM continuous batching plus bounded dispatch executed this workload. Model affinity and heterogeneous-provider economics were not stressed: this was one model and one GPU. Investigate slot occupancy, dispatch/poll overhead, controller warmup/reset behavior and calibration before another adaptive-savings experiment; do not infer a causal controller defect from these two samples alone.

## Cold start and utilization coverage

Creation: **10:05:45.546 UTC**. Container bootstrap marker: **10:10:01.878**, about 256.3 seconds later; allocation/image pull cannot be cleanly separated from these markers. Worker environment ready: **10:10:27.194**. Model download **10:10:27.712–10:10:34.571**, approximately **6.86 seconds**. Engine launch **10:10:34.768** to health ready **10:12:50.116**, approximately **135.35 seconds**; compilation/profile/cache/graph work is nested inside this interval. First customer admission began about **451.13 seconds** after pod creation, including the initial policy transition and live challenge. The context allocation initialized successfully; actual synthetic prompts did not stress four full-length 10,240-token requests.

Every stage had **100% joint engine/hardware coverage** under the capped-hold method, including smoke's required >=90% gate. Across the complete rented lifetime, joint coverage was only **64.2%** and hardware-only coverage **75.0%**. Hardware utilization averaged **31.4% over covered intervals**; about **322.6 seconds** lacked hardware observations, mainly before container sampling and after evidence export. Unknown intervals remain unknown, never zero. Do not describe 31.4% as a fully observed whole-rental average.

vLLM counters increased monotonically from zero to **368,516 prompt and 35,292 generation tokens**. These include readiness canaries and retried work and therefore exceed settled customer usage; they are not billing denominators. Full-rental cost calculations use only successful customer output tokens.

## Interruption, receipts and billing

At **10:22:00.868 UTC**, the controlled worker interruption fired after engine generation and before finalization, exit 75. The launcher restarted/re-registered the worker while preserving vLLM. The interruption arm completed **500/500**, with **504 execution attempts: 500 succeeded and four lease-lost attempts**. Across the entire run: **1,014 attempts, 1,010 usage records, 1,010 capture records and 1,010 unique capture sources**.

All **1,010 customer receipts** passed digest, output-hash, model-mode, usage and captured-amount checks against returned results and the separate SQL audit. Usage charges and journal captures both totaled **47,797 micro-USD**, with **zero wallet drift**. Those are isolated synthetic test-credit charges, not commercial revenue or RunPod costs. Receipt hashes are unsigned operator records, not independent attestation or proof of zero retention. Exactly-once settlement was observed under this controlled interruption; physical generation occurred at least once and some work was repeated.

## Rental economics and comparison limits

The displayed quote was **$0.59/hour GPU + $0.011/hour temporary disk = $0.601/hour**; conservative guard $0.61/hour. Independent termination was confirmed at **10:27:14.783 UTC**, bounding rented lifetime at **21.49 minutes**. The watchdog observed control-job completion and initiated cleanup; the operator subsequently confirmed provider 404. No pods or network volumes remained. Displayed credit afterward was **$7.94**, above the $5 floor.

**The itemized provider bill is pending.** At the displayed all-in rate, the verified lifetime upper bound estimates **$0.21523**, or **$6.13 per million successful output tokens** for the complete validation experiment. The guard-rate estimate is **$0.21845**, or about **$6.22/M output**. These are estimates, not posted invoice figures. The experiment includes sequential work, repeated comparisons, startup, policy transitions, idle time, failed attempts and cleanup; it is not the steady-state cost of a baseline-only deployment. Production control-plane, engineering and support costs have not been priced.

Warm active-window estimates are baseline **$2.28/M successful output** and adaptive **$2.57/M**, using the same quote and measured token counts. They exclude startup/idle/shutdown and must not be presented as fully loaded cost.

For a same-workload baseline-only *modeled* deployment, observed warm cost is roughly **$0.0781 per 1,000 requests** and observed startup/shutdown overhead about **$0.0837**. With linear warm-throughput extrapolation, break-even is `fixed_cost / (comparable_hosted_cost_per_request - warm_GPU_cost_per_request)`. A denominator <=0 has no finite break-even. Illustrative **hypothetical equivalent-provider** prices—not market quotes—give:

| Hypothetical equivalent hosted price / 1,000 requests | Modeled break-even requests |
| --- | ---: |
| $0.05 | None under this configuration |
| $0.10 | Approximately 3,831 |
| $0.15 | Approximately 1,166 |
| $0.20 | Approximately 688 |

These extrapolations are not measured runs at those volumes or a promise of 60-minute attainment. Idle time and production operating costs raise the thresholds.

Primary pricing/catalog review on October 27: [Together pricing](https://www.together.ai/pricing) and [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/), with [Bedrock's model catalog](https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards.html). An equivalent **pinned Qwen3-4B configuration was not verified** on those pages. Together lists different Qwen/Llama models; Bedrock lists larger Qwen configurations and regional/tier-specific prices. Different weights, revisions, tokenizers, quality, context and batch policies make those offerings **non-equivalent**. No hosted-provider calls were purchased, no quality comparison was run, and no competitive savings percentage is justified.

## Before/after and decision

| Area | Before | Evidence now |
| --- | --- | --- |
| Hosted plan | H100 stopped after smoke/sequential; prior A40 blocked on collector contract | All seven stages complete on GitHub |
| Real receipt validation | Mock coverage only | 1,010 real receipts verified |
| Recovery | Prior L4 controlled recovery existed | Hosted 500-request interruption, four extra attempts, no duplicate settlement |
| Batching | Earlier small smoke evidence | Four active sequences and repeated matched 100 arms |
| Economics | Adaptive advantage unproven | Adaptive slower here; fully loaded competitive advantage still unproven |
| Cleanup | Separate protected watchdog | Automatic control-completion teardown and verified absence |

**GO:** supervised private execution/receipt demonstrations with baseline concurrency and bounded budgets. **NO-GO:** cheapest-batch positioning, adaptive savings claims, public beta, Stripe live payments or automatic capacity provisioning. This run validates auditable execution and recovery for the tested workload, not production readiness or a durable moat by itself.

Next, analyze dispatch/slot utilization and calibrate offline using this retained evidence before spending on another performance run. Prioritize discovery in one narrow auditable workflow—freight-document reconciliation is the most directly aligned hypothesis for the synthetic logistics workload, but no customer need or extraction quality has been established. Use the existing [three segment hypotheses/interview guide](../../research/auditable-extraction-discovery.md); do not build extraction features until buyer interviews and a labeled evaluation justify them. The standing $5 credit floor remains in force, and no further GPU is left running.
