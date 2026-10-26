# Availability-driven A40 substitution — approval required

The previously approved L4 Secure US-MO-2 experiment has **not created a Pod**. After the pause, fresh RunPod reads first showed only European L4 stock, then no L4 Secure availability anywhere. RTX 4090 Community remains unavailable. The earlier L4-region question is superseded by this newer stock read; it is not approval for another GPU.

The resumed real-mode control host is run 40239096286. HTTPS origin `https://upgrades-closure-carrier-choir.trycloudflare.com` returned vLLM-mode readiness; authenticated models matched the pinned model/tokenizer SHA, operator configuration matched baseline, and no workers were registered. The owner approved its exact callback, Auth0 saved it successfully, owner login returned status ok, and authenticated owner wallet balance remained zero. The separate synthetic experiment tenant and current encrypted handoff were verified.

## Proposed substitution

- Exactly one **NVIDIA A40 48 GB**, RunPod **Secure Cloud, CA-MTL-1**. Fresh `get_gpu_type` read reports HIGH stock there and in EU-SE-1; US-MO-2 is not proposed for this GPU.
- Deployment form line items for one A40 with 80 GB temporary container disk: **$0.59/GPU-hour + $0.011/disk-hour = $0.601/hour**. UI total rounds to $0.60. No persistent storage or public ports. The displayed generic template is not used: creation would use the existing pinned vLLM digest and reviewed launcher instead.
- Preserve the **$2 internal guard allocation within the original $10 combined budget**, target stop at 90 minutes, independent watchdog cutoff at 110 minutes from arming. Thirty–sixty minutes projects to $0.3005–$0.601, 90 minutes to $0.9015. These are projections, not a provider-enforced cap or real measurements.
- Preserve Qwen3-4B/tokenizer SHA `1cfa9a7208912126459214e8b04321603b3df60c`, vLLM 0.8.5 image digest `sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33`, BF16, context 10,240, max four sequences, memory utilization 0.85, thinking/prefix caching disabled.

NVIDIA lists A40 as Ampere, 48 GB, compute capability 8.6 with BF16 support: [datasheet](https://images.nvidia.com/content/Solutions/data-center/a40/nvidia-a40-datasheet.pdf), [compute capability](https://developer.nvidia.com/cuda/gpus). vLLM 0.8.5 requires compute capability at least 7.0: [versioned requirements](https://docs.vllm.ai/en/v0.8.5/getting_started/installation/gpu.html). The model previously fit on 24 GB L4, so 48 GB provides capacity headroom; this is a compatibility/fit inference, **not an A40 validation result**. Boot/model identity, live canary and first-ten coverage gates still apply. Do not claim measured A40 performance before those tests run.

This changes both GPU architecture and location, so results cannot isolate an improvement over the earlier L4 experiment to software changes. The within-run baseline/adaptive comparisons remain on the same new hardware and use identical workload bytes with reversed order. Keep full-lifetime startup/idle/failed-attempt costs and report the hardware/location confound explicitly. Use synthetic workloads only.

## Approval and cleanup

The private unapproved candidate has a fresh unique identity and hashes; no credential-bearing payload is committed. Require explicit approval of this GPU/location substitution, then fresh stock/price/balance/remaining-host-time checks. Dispatch a fresh exact-identity cleanup plan and require the owner-reviewed GitHub runner's authenticated armed heartbeat **before creating one Pod**. The earlier completed watchdog is not protection. Prior live deletion proof remains historical evidence; provider/GitHub outages remain risks.

The existing [one-Pod approval/run plan](third-gpu-approval.md) supplies the unchanged storage/network boundaries, ten-request smoke, four clean 100-request comparisons, gated 500-request interruption arm (at most 910 requests total), accounting/export checks and termination verification. No replacement Pod is authorized after a critical failure; no public beta, live Stripe, automatic provisioning or billing-rate changes are proposed. This document is not creation authorization until the owner explicitly approves the A40 substitution.
