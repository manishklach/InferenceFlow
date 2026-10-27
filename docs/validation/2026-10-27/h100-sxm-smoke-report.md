# H100 SXM follow-up: real smoke passed, comparison incomplete

October 27, 2026. **10/10 real requests passed on one H100 SXM, with ten verified receipts and zero wallet drift.** The hosted driver then stopped at the time gate before sequential 100. This is a successful smoke validation and an incomplete comparison experiment, not a completed 100/500-request performance study. The pod is terminated; no paid resources remain.

## Provenance and configuration

[CPU/driver 40493606626](https://github.com/manishklach/InferenceFlow/actions/runs/40493606626) and [independent watchdog 40493690060](https://github.com/manishklach/InferenceFlow/actions/runs/40493690060) both concluded successfully. Source: `73969fb33d3a6e4fd23c4cbd3567f30a7d859f97`. The checkpoint records `status=incomplete`, `reason=insufficient_time`, `skipped=sequential`; workflow success indicates clean execution/export/shutdown, not completion of every planned stage. Raw SQL, outputs, receipts and provider logs were exported encrypted to the existing owner key and decrypted only locally. This report and [aggregate JSON](h100-sxm-smoke-metrics.json) publish no credentials or raw payloads.

One NVIDIA H100 SXM 80 GB, RunPod Secure CA-MTL-1, pod `iqxickl6fa3uix`; temporary 80 GB disk, no ports/mounts/SSH/Jupyter/global networking. Returned `gpu.memory=251` describes host RAM, not GPU VRAM; host vCPU count was 28. NVIDIA telemetry identified H100 80 GB hardware. vLLM remained loopback-only; the outbound worker used the approved scoped handoff. Provider read and independent cleanup credentials stayed on separate GitHub jobs.

Same Qwen/Qwen3-4B model/tokenizer revision `1cfa9a7208912126459214e8b04321603b3df60c` and vLLM 0.8.5 image digest `sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33` as the [complete A40 validation](a40-hosted-1010-report.md). BF16, context 10,240, four worker/engine slots, thinking/prefix cache off. Actual prompts did not stress four full-context requests. Public beta, Stripe, automated provisioning and estimator calibration remained disabled.

The prepared H100 NVL became unavailable at the final stock check. Its CPU/watchdog jobs were canceled before GPU creation. The owner then authorized any suitable high-end GPU within the credit floor. Fresh catalog reads listed H100 SXM stock in CA-MTL-1 and GPU price $3.99/hour; checkout showed $0.011/hour for temporary disk and per-millisecond billing. The replacement used a $4.01/hour guard, $2.20 allocation, $0.40 pending-charge reserve and a 20-minute cutoff from watchdog arming. No persistent storage or automatic replacement was created.

## Measured smoke results

| Measurement | Real result |
| --- | ---: |
| Successful requests / attempts | 10 / 10 |
| Verified receipts / usage records / unique captures | 10 / 10 / 10 |
| Successful input / output tokens | 3,618 / 345 |
| API receipt through last completion | 4.3668 seconds |
| Request p50 / p95 / p99 from API receipt | 3.4882 / 4.3668 / 4.3668 seconds |
| Successful output tokens per server second | 79.01 |
| Observed submission-to-60-minute attainment | 10/10 |
| Peak actual vLLM active sequences | 4 |
| Smoke joint engine/hardware coverage | 100% |
| GPU utilization over covered smoke intervals | 16.26% |
| Repeated execution attempts | 0 |
| Usage charges / journal captures, synthetic micro-USD | 473 / 473 |
| Wallet drift | 0 |

Receipt digest, output hash, model mode, token counts and capture amount were verified against results and a separate read-only SQL audit. These are unsigned operator receipts, not independent attestation or proof of no retention. Synthetic wallet charges are test-credit accounting, not RunPod spend or revenue. This pod did not execute interruption; that evidence remains in the A40 report.

The smoke input hash `4c66cda4205b39dee1cad61e7848c457c1aede65a322f27f83fb001ac879ac16` matches A40 smoke inputs. A40 smoke took 5.9414 seconds and produced 342 output tokens (57.56 output tokens/s), versus H100's 4.3668 seconds and 345 tokens (79.01/s). This single ten-request observation is not a sustained benchmark, saturation test or statistically established speedup. Host CPU/RAM and startup conditions differed. Higher concurrency was not tested, so H100 saturation and optimal utilization are unknown.

Quoted warm smoke-window cost is approximately $14.07/M successful output tokens for H100 versus $2.90/M for A40, excluding startup/idle/shutdown. These tiny-window estimates do not establish steady-state economics or support a cheaper-inference claim.

## Cold start, dispatch and coverage

Creation: **11:12:24.958 UTC**. Container bootstrap: **11:18:12.860**, approximately **347.90 seconds** later; allocation and image pull cannot be separated from these markers. Worker environment ready: **11:18:43.464**. Model download took **5.14 seconds**, **11:18:44.174-11:18:49.312**. Engine launch **11:18:49.499** to health **11:20:44.805** took **115.31 seconds**. Total creation-to-health: **499.85 seconds**. Model load reported 7.5552 GiB; torch.compile reported 31.71 seconds, nested within engine initialization rather than an additive phase.

Smoke p95 components: admission 1.213 seconds, queue until scheduler observation 0.634, scheduler capacity/policy wait 2.063, lease assignment 0.000111, lease-to-worker-poll 0.335, worker receipt-to-engine-start 0.00495 and engine call 0.364. Separate component percentiles must not be summed into a single request's latency. Full distributions are in the JSON.

Joint telemetry covers only **7.06% of the complete rental**, with approximately **568.22 seconds unknown** under capped-hold accounting. Hardware-only startup samples exist before engine metrics; joint coverage excludes them. Smoke coverage passed, but complete-lifetime utilization was not established. Unknown intervals are not zero; the smoke mean is not a whole-rental average. A recoverable provider-log ReadTimeout was retained in private diagnostics; it did not prevent the verified smoke window.

## Why the larger comparison did not run

The watchdog armed at **11:08:06.165 UTC**, while the CPU host still awaited review/build. Creation occurred about 4 minutes 19 seconds later. The cutoff remained **11:28:05.847**; reserving the final two minutes for shutdown made the driver deadline **11:26:05.847**. Cold start and smoke left less than sequential's **300-second timeout + 90-second transition/audit allowance**. The fail-closed gate skipped sequential and every following stage. No 100-request, adaptive, 500-request interruption or high-concurrency results exist from this pod.

This is an orchestration/time-allocation limitation, not evidence that H100 cannot execute 100 requests within budget. Do not purchase another run unchanged. First check feasibility offline using measured cold-start distributions and retained H100/A40 timings. Arm cleanup after CPU readiness, and prepare a minimum comparison plan whose conservative stage allowances fit the remaining bound. Test changed timeouts/plans before rental; do not alter limits mid-run or bypass owner protections.

## Cost, cleanup and decision

The independent watchdog observed control completion and initiated termination. Absence was confirmed **11:22:36.366739 UTC**; subsequent authenticated GET returned **404**, and pod/network-volume inventories were empty. This bounds rented lifetime at **611.41 seconds (10.19 minutes)**. The operator did not manually terminate this pod.

At the displayed **$4.001/hour all-in quote**, the rental upper estimate is **$0.67951**; at the **$4.01/hour guard**, **$0.68104**. The itemized query has no records yet: **posted bill pending, not zero cost**. Displayed remaining credit was **$7.46**, above the $5 floor; balance changes are not an itemized invoice.

Quote-estimated complete-rental cost per million successful output tokens is about **$1,969.60/M**, because this validation generated only 345 successful output tokens after cold startup. This is an experiment total, not a production price or steady-state rate. Comparing it directly with the A40 experiment's $6.13/M would be misleading: A40 completed 1,010 requests with different amortization. No Together/Bedrock advantage or sustained H100-vs-A40 economic ranking is established.

**GO:** private H100 execution/receipt compatibility demonstrations under tested bounds. **NO-GO:** declaring the hardware comparison complete, claiming H100 savings, public beta, live Stripe or automatic provisioning. The most complete scheduler/recovery evidence remains the 1,010-request A40 run. No paid resources remain and no automatic rerental is scheduled.
