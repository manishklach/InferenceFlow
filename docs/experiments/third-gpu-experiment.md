# Third GPU experiment: matched comparisons and 500-request validation

Preparation only. No GPU is created by these changes. Public beta, live Stripe and automatic provisioning remain disabled; wallet algorithms and customer prices are unchanged. The owner approved Apache-2.0 on October 25, 2026; the root LICENSE and package metadata now record it.

## Current evidence and blockers

The second experiment completed 410 requests including worker interruption with zero ledger drift. Adaptive was slower in one fixed-order comparison. No savings claim follows. The posted second-pod bill is now $0.21400138374883682 including disk; see the [billing addendum](../validation/2026-10-25/second-gpu-report.md#posted-billing-addendum).

Fresh October 25 reads of RunPod's GPU catalog with one-Pod availability and CUDA floor 12.8 returned:

| GPU | Community | Secure | Secure stock |
|---|---|---|---|
| RTX 4090 24 GB | $0.34/hour, NONE | $0.89/hour | HIGH; US-IL-1 and European locations |
| L4 24 GB | unsupported, NONE | $0.59/hour | LOW; US-MO-2 and European locations |
| L40S 48 GB | $0.79/hour, NONE | $1.09/hour | LOW; US-TX-4 and OC-AU-1 |
| RTX A5000 24 GB | $0.16/hour, NONE | $0.27/hour | LOW; CA-MTL-1 and EU-SE-1 |

Prefer L4 Secure US-MO-2 to preserve the previously tested hardware/configuration and reduce cross-experiment confounds. A5000 Secure is a cheaper candidate but has not been validated with this pinned serving configuration; it requires a separate fit/performance decision. Catalog prices are not reservations or a final all-in deployment quote. Re-read immediately before approval.

RunPod console showed **$9.67 balance** and the Pod inventory was empty during preparation. The catalog exposes no balance field; this is a console observation, not a computed balance. Official [storage pricing](https://docs.runpod.io/pods/pricing) lists temporary container disk at $0.10/GB/month. For 80 GB, an illustrative 730-hour conversion is $0.010959/hour; the previous deployment quoted $0.011/hour. Use the actual final deployment quote for cleanup safeguards, not this conversion. At a confirmed $0.601 all-in hourly rate, 30/60/120 minutes would be $0.3005/$0.601/$1.202 before any tax or separate control-plane charges. These are projections, not posted bills or a guaranteed cost cap.

**Not ready to rent yet:** this computer's Docker daemon is currently unavailable, staging HTTPS is not freshly verified, and no independent always-on control-plane host has been deployed. The earlier independent GitHub cleanup job is finished, not armed. An approved GitHub cleanup secret is not proof of a newly armed watchdog. Do not bypass these gates because credits are available.

## Supervision repair and deployment boundary

The failed ignored supervisor used `subprocess.run(check=True)` for each Compose status read and immediately entered teardown on one CLI error. The underlying Docker stderr was lost. The tracked `scripts.staging_supervisor` now:

- Retries only failed/timed-out Docker reads, at most three attempts, ten seconds per command and one/two-second backoff.
- Retains stderr in private diagnostic files, without echoing it to public logs.
- Treats successfully observed missing services as failure, rather than masking an outage as a transport retry.
- Checks stop/deadline before another retry; retains a heartbeat only after a successful health read.
- Allows explicitly marked policy maintenance for at most 180 seconds, always requiring PostgreSQL. An expired marker restores the full required set.
- Stops the exact Compose project at deadline, operator stop, or exhausted retries, retaining stop diagnostics. It never deletes database volumes or creates/deletes GPUs.

The existing mock rehearsal uses the same retry helper. The previous ignored real supervisor has also been patched locally to use it; future deployment must use reviewed tracked code rather than relying on ignored scripts.

On an existing, privately configured Docker host, run:

```bash
python -m scripts.staging_supervisor --compose-file /private/staging/compose.yml --diagnostics /private/staging/third-diagnostics --minutes 120 --start
```

This command starts existing configured services; it does not create hosting or a tunnel. The directory must be operator-only (0700 on Linux; operator/SYSTEM ACL on Windows). Never upload its stderr files, environment, database, or credentials as public evidence. Create `STOP` in the diagnostic directory for an early stop. A clean deadline stops services but retains the database volume for audit. Review `stopped.json`; a nonzero stop status requires operator intervention. For idle-boundary policy switches, place `{"expires_at_epoch": <at most 180 seconds from now>}` in `maintenance.json`, remove it when healthy, and require a fresh live worker challenge before submitting again.

The same command can run on an independently hosted Linux machine under its service manager. It is **not** independent hosting merely because it is portable. Before rental, deploy and fault-test the chosen host, verify its HTTPS/OIDC callback and PostgreSQL, verify worker authentication, and demonstrate that disconnecting this PC does not stop the control plane. Hosting and credential transfer require separate approval; no staging credentials have been copied to GitHub or another provider by this preparation.

## Workloads and execution order

```bash
python -m scripts.second_gpu_experiment prepare --validation-count 500 --output .runtime/third-experiment-NEW
```

This creates deterministic, hashed smoke-10, comparison-100, comparison-500, interruption-100 and interruption-500 workloads. No network calls or jobs are submitted. The loader now explicitly accepts 500. Reuse the **same comparison-100 file bytes** for all four clean arms, with distinct run IDs:

1. Smoke 10; require complete usage/billing reconciliation and at least 90% compact engine/hardware telemetry coverage.
2. Baseline 100, adaptive 100, then adaptive 100, baseline 100. Record warm-up, policy-switch downtime, fixed order and all run IDs. Hard worker/engine cap four; baseline flags false/false, adaptive true/true. Keep the estimator explicitly uncalibrated. Reconfirm policy and live readiness before each arm. Two repeats are directional evidence, not strong statistical proof.
3. Only if prior arms pass and cost/time reserve permits, run **one 500-request controlled-interruption validation** using the selected configuration and `interruption-500.json`. The reviewed worker exits once after five engine successes before finalization. Verify restart, expired leases, retry attempts, eventual terminal outcomes, unique usage/captures and released reservations. Do not use this fault arm as a clean throughput comparison. Select baseline if adaptive has no repeatable advantage; never cherry-pick a single best run.
4. There is no 1,000-request requirement for this experiment. Expected maximum submissions are 910 (10 + four clean 100 arms + one 500 arm), not 500 total. That distinction must appear in approval and cost reporting.

Example submission commands after separate rental approval and verified infrastructure:

```bash
python -m scripts.gpu_experiment run --execute --policy baseline --count 10 --run-id third-smoke --workload-file .runtime/third-experiment-NEW/smoke-10.json --output .runtime/third-smoke
# Repeat this clean arm with policy/order baseline, adaptive, adaptive, baseline;
# apply the corresponding idle-safe control-plane settings before each command.
python -m scripts.gpu_experiment run --execute --policy baseline --count 100 --run-id third-baseline-1 --workload-file .runtime/third-experiment-NEW/comparison-100.json --output .runtime/third-baseline-1
python -m scripts.gpu_experiment run --execute --policy baseline --count 500 --run-id gpu-test-interruption-third-500 --workload-file .runtime/third-experiment-NEW/interruption-500.json --output .runtime/third-interruption-500
python -m scripts.audit_gpu_run --run-directory .runtime/third-interruption-500 --output .runtime/third-audit.json
python -m packages.common.cli reconcile
```

Use the existing pinned Qwen3-4B/tokenizer revision, vLLM 0.8.5 digest, BF16, context 10,240, four sequences, memory fraction 0.85, thinking/prefix caching off. Bind vLLM only to Pod loopback; expose no public ports and attach no persistent/network volume. Four simultaneous maximum-context requests remain unvalidated.

## Approval and cleanup gates

Before asking for GPU creation approval, establish a healthy independent HTTPS control plane, fresh console balance, actual GPU+disk quote, remaining original $10 budget including prior experiments, current cleanup credential preflight, reviewed exact experiment cleanup plan, and operator-approved GitHub watchdog with a fresh armed heartbeat. The two-hour GPU limit and early stop threshold must include startup/idle/retries. The guard's reserve is not a RunPod-enforced cap. Stop early on critical errors, telemetry gaps, stale readiness, or ledger drift. Do not increase rates, enable auto-provisioning, change wallet code, or deploy an unapproved host.

After execution, export private evidence before triggering the independent exact-Pod finalizer. Verify fresh Pod GET 404, empty matching Pod/storage inventory, no persistent paid storage, and posted provider billing. The prior live termination proof supports the mechanism, but does not establish that a future job is armed or that provider outages are harmless.

## Decision and measurement rules

Measure full rental from creation through verified termination; successful input/output tokens; p50/p95/p99 latency; admission/dispatch components; actual 60-minute attainment; all retries and unsuccessful work; overlapping worker requests; engine active/waiting sequences; time-weighted utilization with unknown intervals explicit; and unique usage/captures/reservation releases.

Calculate posted GPU+disk+any control-plane costs per million **successful output tokens**, including startup/idle/failures. Also report usable-output cost using a predeclared short/medium task rubric with recorded pass/fail decisions; token counts alone do not validate quality. Compare clean baseline/adaptive runs within this experiment separately from full-lifetime economics. Hosted prices are comparable only with equivalent models/settings/quality and batch terms; no equivalent Qwen3-4B hosted baseline is verified yet. No paid hosted requests are authorized.

GO for the bounded 500-request engineering claim requires every admitted request accounted for, observed deadline results, successful controlled recovery, and zero duplicate charges or ledger drift. Savings GO additionally requires repeatable quality-equivalent cost improvement over fixed concurrency and a fair market alternative, including operating costs. Neither outcome establishes production readiness. Publish failures and confounds; keep public beta and savings claims NO-GO unless evidence supports changing them.
