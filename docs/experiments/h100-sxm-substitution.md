# Approved H100 SXM substitution

October 26, 2026 PDT: the approved H100 NVL became unavailable before creation. The operator approved proceeding with the available SXM after the changed quote was presented. No NVL pod was created.

This replaces only the hardware, placement and cost allocation in the [full H100 experiment plan](h100-nvl-approval.md):

- Exactly one NVIDIA H100 SXM 80 GB (`NVIDIA H100 80GB HBM3`), RunPod Secure Cloud, CA-MTL-1; freshly observed LOW stock there.
- GPU $3.99/hour + displayed 80 GB temporary container disk $0.011/hour = **$4.001/hour**. Conservative guard rate **$4.01/hour**.
- **$6 internal allocation within the original total $10 budget**. Target 20–30 rented minutes, approximately $1.34–$2.01. Independent cutoff **45 minutes from watchdog arming**; a full 45-minute quoted lifetime is approximately $3.01 at the conservative rate. Allocation is not a spending target or a provider-enforced cap.
- Same pinned Qwen3-4B/tokenizer revision, vLLM image, BF16, 10,240 context, four-sequence hard cap, outbound worker, no public ports or persistent storage, and gated maximum 1,010-request test plan. Actual H100 startup/fit and performance remain unmeasured until the smoke test.
- Same independent GitHub cleanup key destination, exact random pod identity, historical live deletion proof, cancellation finalizer and fresh 404 verification. A fresh authenticated armed heartbeat and current host/stock/price/balance checks remain mandatory before the single create call. GitHub owner review is required to release the protected cleanup key.

No automatic fallback or second pod is approved. Public beta, Stripe and automatic provisioning remain off. The independent watchdog was dispatched as [run 40291400132](https://github.com/manishklach/InferenceFlow/actions/runs/40291400132) and was waiting for required owner review at preparation time; no GPU has been created at that point. The CPU host remains [40288126492](https://github.com/manishklach/InferenceFlow/actions/runs/40288126492).
