# v0.3 implementation and validation report

## Completed

Opt-in DeadlineEstimator, bounded fairness/urgency DispatchPolicy and recommendation-only CapacityPlanner extend the durable PostgreSQL scheduler. Explicit best-effort or strict admission records predictions without changing wallet accounting. Adaptive slots consume timestamped engine/GPU/error/latency observations with hard limits, cooldowns and conservative telemetry-loss behavior.

Migration 0006 adds operational observations and GPU cost profiles. Quotes and provider invoices remain separate; invoice coverage, successful input/output volumes, attributable captured revenue, total/output CPM and estimated margin are reportable. Manual attach, invoice and shutdown-record commands only update internal metadata. Worker attempt fences, generation recovery, tenant isolation, immutable rates and exactly-once settlement remain.

The dashboard and SDK expose tenant performance; separately authenticated operators can inspect capacity/economics. New Prometheus metrics identify measurement modes. The static Sites showcase is unchanged and was not redeployed. No GPUs, paid capacity, external payments or public application deployment were activated.

## Tests and evidence

| Check | Result |
|---|---|
| Before-change PostgreSQL baseline | 56 passed, one opt-in GPU test skipped |
| Final PostgreSQL suite | **78 passed, one opt-in GPU test skipped** |
| New scheduling/economics suite | 22 passed |
| Existing platform tests with v2 enabled | 31 passed |
| Ruff / mypy | Passed, 32 source modules typed |
| Normal + isolated QA Next.js builds | Passed, including TypeScript and operator route |
| Docker Compose configuration | Passed; full new container stack not rerun (local daemon unavailable) |
| Six workloads × three policies | 18 actual offline simulation runs, reproduced byte-for-byte |
| Browser QA | Synthetic tenant completed three mock requests; tenant performance and operator panel verified; no browser errors |

One upstream Starlette/AnyIO deprecation warning remains. Regression tests cover admission atomicity, legacy idempotency hashes, deadlines/expiration boundaries, weighted fairness/aging and small-tenant access, adaptive hysteresis/caps, invalid/stale/future telemetry, capacity/budget/kill switches, quote/invoice arithmetic, metadata preservation, zero wallet drift, concurrent submissions, worker outage/restart and billing. Existing tests continue to cover duplicate finalize, tenant isolation, refunds, leases and other MVP invariants.

Screenshots are unmodified captures from the synthetic local `_test` database; the temporary QA services were stopped and its credential is no longer served. No keys or customer content are pictured. [Full dashboard](media/v03/scheduling-full.png) · [mobile overview](media/v03/scheduling-mobile.png).

## Baseline versus new scheduling

The [complete comparison](performance/simulation-results.md) and [raw JSON](performance/simulation-v0.3-seed42.json) report every scenario and metric. These are synthetic workload/engine results, not GPU measurements. For mixed deadlines at seed 42, 240 accepted requests:

| Policy | Succeeded | Successful p95 | All accepted successfully within target |
|---|---:|---:|---:|
| Baseline | 195 | 357s | 72.5% |
| Deadline | 198 | 364s | 68.8% |
| Deadline + adaptive | 212 | 311s | 82.5% |

Deadline priority alone regresses attainment here; adaptive behavior benefits from this simulator's assumed concurrency saturation curve. It does not establish a real hardware advantage. All low-volume variants have the same 24s p95. Refer to raw p50/p95/p99, queue/fairness/utilization/cost/retry fields for tradeoffs and denominators.

## Run locally

1. Follow the root README's `.env.example` and Docker/native PostgreSQL quickstart; apply migration 0006 with `alembic upgrade head`.
2. Keep mock execution, `PROVISIONING_ENABLED=false`, `STRIPE_ENABLED=false`, `ESTIMATOR_CALIBRATED=false`. Set `SCHEDULER_V2_ENABLED=true`, optionally `ADAPTIVE_DISPATCH_ENABLED=true`, and `DEFAULT_COMPLETION_TARGET_SECONDS=3600`. Start API, scheduler, callback process, mock worker and dashboard; seed development funds using the existing CLI.
3. Submit through API/SDK/dashboard. Inspect returned `admission`, terminal results, tenant performance and `python -m packages.common.cli reconcile`. Operator reports use `python -m packages.common.cli scheduling-report` or a separately configured metrics bearer credential.
4. Run `python -m scripts.benchmark_scheduler --seed 42 --count 240 --output .runtime/benchmark-v03.json` without GPU/database services. Run `python -m pytest -q`, `python -m ruff check .`, `python -m mypy apps packages` against isolated PostgreSQL. Build dashboard with `npm ci` and `npm run build` in `apps/dashboard`.

Next.js API rewrites are resolved at **build time**. When validating a dashboard against an alternate local API, set `API_PROXY_URL` consistently during both build and start, and use a separate `NEXT_DIST_DIR`. Do not commit generated QA build/type artifacts. The default Docker/native 8080 path remains unchanged.

## First NVIDIA attachment, cost controls and readiness

Follow [the exact attachment guide](gpu-deploy.md#v03-first-attachment-and-experiment-controls), [experiment plan](performance/benchmark-plan.md#first-real-nvidia-experiment-approval-required-not-executed-here), and [cost/invoice runbook](economics/unit-economics.md). Obtain explicit provider/device/price/duration/total-expense approval first; verify a pinned image/model fits the approved hardware. Keep automatic provisioning off, one-GPU cap, provider-side alerts and independent shutdown. The proposed first smoke is at most 30 minutes under a separately approved cap fitting the actual quote/minimum/fees; it cannot validate an hour-long SLA.

Register the actual provider ID/quote/start internally, bind the outbound worker to that ID, measure model loading separately, run the opt-in GPU smoke and restart test, reconcile wallets, stop at the provider, confirm billing stopped, then import the actual covered invoice. Further sustained target-window experiments require their own approval. No expense approval has been assumed for this implementation.

The code is ready for a **controlled first real-GPU validation**, with conservative defaults and visible unknowns. Real GPU throughput, model fit, estimator calibration, hour-long attainment, external provider/Stripe/OIDC behavior and cost advantages remain unproved. Keep both new scheduling flags off for existing workloads until reviewing simulation regressions and validating representative hardware/workloads. Rollback disables those flags without undoing financial history or migration 0006.

Intentionally deferred: automatic provisioning/scaling, multi-model/hardware/provider optimization, AMD/ROCm, learned prediction, token-weighted fairness, invoice API ingestion, precise GPU kernel/prefill/decode profiling, formal SLA and public rollout. V0.3 release notes are prepared; merge and publication await human review.

## File manifest

The branch changes the following files (application code, migration, tests, CI, documentation and safe mock evidence only):

- [.dockerignore](../.dockerignore)
- [.env.example](../.env.example)
- [.github/workflows/test.yml](../.github/workflows/test.yml)
- [.gitignore](../.gitignore)
- [CHANGELOG.md](../CHANGELOG.md)
- [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md)
- [README.md](../README.md)
- [apps/api/main.py](../apps/api/main.py)
- [apps/dashboard/.dockerignore](../apps/dashboard/.dockerignore)
- [apps/dashboard/app/operations/report/route.ts](../apps/dashboard/app/operations/report/route.ts)
- [apps/dashboard/app/page.tsx](../apps/dashboard/app/page.tsx)
- [apps/dashboard/app/performance.tsx](../apps/dashboard/app/performance.tsx)
- [apps/dashboard/package-lock.json](../apps/dashboard/package-lock.json)
- [apps/dashboard/package.json](../apps/dashboard/package.json)
- [apps/worker/engines.py](../apps/worker/engines.py)
- [apps/worker/main.py](../apps/worker/main.py)
- [docs-openapi.json](../docs-openapi.json)
- [docs/api.md](../docs/api.md)
- [docs/architecture/scheduler-v2.md](../docs/architecture/scheduler-v2.md)
- [docs/architecture/scheduler-v2.mmd](../docs/architecture/scheduler-v2.mmd)
- [docs/blog/why-we-built-inferenceflow.md](../docs/blog/why-we-built-inferenceflow.md)
- [docs/economics/unit-economics.md](../docs/economics/unit-economics.md)
- [docs/gpu-deploy.md](../docs/gpu-deploy.md)
- [docs/implementation-v0.3.md](../docs/implementation-v0.3.md)
- [docs/media/v03/scheduling-full.png](../docs/media/v03/scheduling-full.png)
- [docs/media/v03/scheduling-mobile.png](../docs/media/v03/scheduling-mobile.png)
- [docs/performance/benchmark-plan.md](../docs/performance/benchmark-plan.md)
- [docs/performance/simulation-results.md](../docs/performance/simulation-results.md)
- [docs/performance/simulation-v0.3-seed42.json](../docs/performance/simulation-v0.3-seed42.json)
- [docs/product/60-minute-inference.md](../docs/product/60-minute-inference.md)
- [docs/releases/v0.3.0.md](../docs/releases/v0.3.0.md)
- [migrations/versions/0006_scheduler_v2.py](../migrations/versions/0006_scheduler_v2.py)
- [packages/common/cli.py](../packages/common/cli.py)
- [packages/common/config.py](../packages/common/config.py)
- [packages/common/db.py](../packages/common/db.py)
- [packages/common/economics.py](../packages/common/economics.py)
- [packages/common/metrics.py](../packages/common/metrics.py)
- [packages/common/performance.py](../packages/common/performance.py)
- [packages/common/providers.py](../packages/common/providers.py)
- [packages/common/scheduling.py](../packages/common/scheduling.py)
- [packages/common/schemas.py](../packages/common/schemas.py)
- [packages/common/service.py](../packages/common/service.py)
- [packages/python_sdk/client.py](../packages/python_sdk/client.py)
- [pyproject.toml](../pyproject.toml)
- [scripts/benchmark_scheduler.py](../scripts/benchmark_scheduler.py)
- [tests/test_scheduler_v2.py](../tests/test_scheduler_v2.py)
