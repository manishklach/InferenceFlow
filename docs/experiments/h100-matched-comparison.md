# H100 matched A40 comparison — bounded experiment

Prepared October 27, 2026 under the owner’s standing RunPod spending authority, preserving at least $5 credit. No GPU is created by this document or the hosted driver.

Outcome: NVL stock disappeared before creation. A separately configured H100 SXM ran ten real requests; the comparison stopped at its time gate. See the [measured follow-up and cleanup report](../validation/2026-10-27/h100-sxm-smoke-report.md). The NVL preparation below is historical and was not provisioned.

## Selection and budget

Fresh authenticated catalog reads list H100 NVL 94 GB, Secure US-KS-2, LOW stock, at $3.19/hour; H100 SXM $3.99/hour and H200 SXM $5.29/hour. Select one NVL if fresh stock and placement still pass. No automatic substitution/replacement. Checkout shows 80 GB temporary disk $0.011/hour, total quote $3.201/hour and per-millisecond billing. Use $3.21/hour guard, 25 minutes from watchdog arming, $2.20 allocation and a separate $0.30 pending-charge reserve. Displayed balance at preparation: $7.94; require a fresh balance before creation and projected remaining credit above $5. No provider-enforced budget is assumed.

At the guard rate, 25 minutes costs $1.3375; two additional minutes reserved for cleanup cost $0.107. This $1.4445 bound is below 70% of the $2.20 allocation. The independent watchdog retains its exact resource identity, 10-minute creation window, 70% early-stop rule, price-overrun check, hard deadline and finalizer. Existing plans still reserve whole hours. An explicit `billing_quantum_seconds: 1` opt-in rounds the quoted millisecond billing up to whole seconds; only use it when the all-in quote and provider billing interval have been freshly verified. It changes experiment cost estimation only, not customer wallets or settlement.

## Execution and fair comparison

Use the same pinned Qwen3-4B revision, tokenizer, vLLM 0.8.5 digest, BF16, 10,240 context, four worker slots and engine sequences, thinking/prefix cache off as the [completed A40 experiment](../validation/2026-10-27/a40-hosted-1010-report.md). Keep all public pod ports, SSH, Jupyter, mounts and global networking disabled. vLLM remains loopback-only; the worker connects outbound to the isolated HTTPS control plane. GPU gets only scoped worker credentials. Read and cleanup keys remain separate on GitHub.

Run the existing hosted plan: smoke 10, sequential 100, baseline/adaptive/adaptive/baseline 100, then gated interruption 500. The 100 arms must retain workload SHA-256 `1c2cd763e6c3a2d7587de5586342808daa3714a5a023538632f6414ca803a3f5`. A stage that lacks remaining time, joint smoke telemetry, successful requests, verified receipts or clean SQL settlement cannot admit its successor. The 500 stage may be skipped to honor the shorter budget. No claim of 1,010 completions before the evidence exists.

This experiment holds concurrency at four to isolate hardware. It does not test H100 saturation or higher concurrency. Those require a separately reviewed experiment configuration after this matched comparison, not an unrecorded mid-run capacity change.

Compare server receipt-to-completion p50/p95/p99, queue/dispatch components, successful tokens/s, active sequences and covered GPU utilization, retries, observed 60-minute attainment, complete rented lifetime and cost per million successful output tokens. Keep missing startup utilization unknown; distinguish quote estimates from posted provider charges. Different hardware/location may also change host CPU, networking, startup and token outputs; do not attribute all differences solely to GPU silicon.

## Readiness and independent cleanup

Start the existing main-only protected real-control-host workflow with the nonsecret exact session and encrypted handoff. Verify GET-only provider preflight, HTTPS readiness, denied anonymous wallet, zero-worker admission rejection without wallet mutation, pinned tokenizer and disabled public beta/Stripe/provisioning before rental. Arm the separately protected watchdog only after the host is ready, then verify authenticated fresh heartbeat and exact cutoff. Owner GitHub deployment reviews remain required; standing financial approval does not bypass them.

On successful completion or critical failure, the hosted control job exports only owner-encrypted evidence and shuts down. The independent watchdog observes control completion and terminates the bound pod, with hard cutoff as backup. Operator verifies provider 404 and empty owned-resource inventory; no persistent paid storage is created. Stop if the credit floor, cleanup authentication, stock, quote or control-plane readiness cannot be verified.

Preparation validation: focused guard/host contract tests cover legacy hourly behavior, explicit interval validation, upward rounding, two-minute cleanup reserve, early-stop thresholds and unchanged hard cutoff. Full CI must pass before this source is deployed. No live higher-GPU measurements are claimed here.
