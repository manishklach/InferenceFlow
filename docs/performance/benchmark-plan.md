# Reproducible scheduling and GPU validation

## Offline experiment

~~~bash
pip install -e '.[dev]'
python -m scripts.benchmark_scheduler --seed 42 --count 240 --output .runtime/benchmark-v03.json
python -m pytest -q
python -m ruff check .
python -m mypy apps packages
~~~

The simulation itself needs neither PostgreSQL nor a GPU; it creates no database sessions and contacts no external service. The regression suite needs an isolated PostgreSQL database ending `_test`. It must not run against customer data.

Six seeded scenarios cover low volume, bursts, sustained traffic, mixed deadlines/lengths across eight tenants, a 90-second worker outage/restart with retries, initial 120-second GPU cold start, and temporary additional capacity with its own 120-second startup and removal. All use identical workloads and hypothetical engine/cost assumptions across baseline, deadline and adaptive variants. Baseline reproduces the v0.2 scoring formula; v2/controller call the production pure functions. This is not a GPU emulator or an end-to-end PostgreSQL load benchmark.

The engine curve scales aggregate work with concurrency up to eight slots, then imposes an assumed penalty. This assumption intentionally creates a useful saturation experiment; it is not fitted to vLLM. Document or replace the curve before extrapolating. Provider quotes are hypothetical $1/hour, billed in 60-second increments per GPU. Paid uptime includes startup, idle and outage time. No customer rates are changed by experiments.

Simulation settings are pinned inside the harness rather than inherited from a developer's `.env`. Remaining work uses integer micro-service units, Jain fairness uses exact rational arithmetic, and JSON is canonical UTF-8/LF. This avoids OS newline and Python floating-summation differences when comparing the committed artifact across Windows/Python 3.11 and Linux/Python 3.12. Production telemetry and estimator behavior remain independently configured.

Reports include throughput, queue and successful completion p50/p95/p99, deadline attainment among successes, successful-within-target fraction among **all accepted work**, expired/failed counts, retries, normalized tenant completion-rate Jain fairness, slot-occupancy proxy, and estimated total-token CPM. Never use successful-only latency to hide failures. Slot occupancy is not GPU hardware utilization, and Jain completion fairness does not measure instantaneous latency fairness.

See [the generated comparison](simulation-results.md) and [raw seed-42 JSON](simulation-v0.3-seed42.json). Re-run twice with the same seed and compare JSON byte-for-byte. Acceptance for this harness is deterministic output, no paid/external calls, complete terminal accounting and explicit assumptions—not an arbitrary improvement percentage. V2 may regress a metric; report it.

## Local platform test

Use the README Docker/native quickstart with `SCHEDULER_V2_ENABLED=true`, `ADAPTIVE_DISPATCH_ENABLED=true`, mock mode and seeded funds. Verify returned admission metadata, target, lifecycle, results and zero ledger drift. Empty mock GPU telemetry keeps adaptive dispatch at its conservative two-slot fallback, rather than pretending to measure a GPU. View your tenant's dashboard metrics; use the separately authenticated operator panel or `python -m packages.common.cli scheduling-report` for capacity/economics.

## First real NVIDIA experiment (approval required; not executed here)

1. Obtain written operator approval specifying provider, machine, price, maximum total expense and time. Confirm model license/rates and hardware/image compatibility. Use one approved 24–48GB NVIDIA host as the existing deployment guide's starting hypothesis, not a validated fit claim. Record exact model/tokenizer SHA, engine image digest, GPU type/driver, context/KV settings, quantization and decoding.
2. Keep `PROVISIONING_ENABLED=false`, `STRIPE_ENABLED=false`, `MAX_ACTIVE_GPUS=1`, `ESTIMATOR_CALIBRATED=false`. For a small proposed experiment, use an independently approved $5 ceiling and 30-minute session cap **only if the confirmed quote, minimum charge and fees fit**. Install provider-side budget alerts and an independent shutdown path. Do not rely on the platform budget alone. No automatic GPU creation is required.
3. Follow [the exact attachment runbook](../gpu-deploy.md) for loopback-only vLLM, readiness canary, pinned identity and outbound worker. Use a private/VPN-accessible HTTPS control plane; these instructions do not authorize a public deployment. Record actual start in `gpu-attach`, provider ID on worker, and observed load time as `WORKER_MODEL_LOADING_SECONDS`. Set realistic startup/load planning assumptions separately.
4. Run the opt-in GPU smoke and 100-request batch. Inspect exact usage, output quality, attempt history and wallet reconciliation. Stop on any identity, stale-lease, usage or accounting defect. Start with fixed concurrency (adaptive off), then compare 1, 2, 4, 8 and 16 only where VRAM and engine configuration support them. Capture missing/stale telemetry behavior too.
5. Use matched short classification, medium extraction and long summarization mixes. Measure prefill/decode separately, concurrent GPU throughput, p50/p95/p99 end-to-end completion, all-accepted success within target, failed/retried work, queue age, NVIDIA/KV utilization, startup/idle uptime and actual bill. Replay the same arrival seeds and tenant mixes for baseline, v2 fixed and v2 adaptive. Restart the worker once during load and verify bounded recovery and zero duplicate captures.
6. The first 30-minute smoke does **not** validate an hour-long completion objective. If safe and useful, obtain a separate approval/budget for a sufficiently long sustained-load run across the full target window and at least one restart. Include low, 30%, 60% and 80% demand occupancy and a representative burst. Calibrate only after enough matched observations and hold-out workload validation.
7. Proposed validation gates: zero ledger drift/duplicate capture, no cross-tenant reads, all accepted requests reach terminal states under normal recovery, at least 99% successful within the requested target **for the explicitly bounded eligible workload**, and no untracked paid instances. Report confidence intervals and all exclusions. These are experiment gates, not a public SLA. A cost advantage requires comparable output quality, identical model/configuration and actual invoices; no advantage threshold has been achieved here.
8. Stop at the provider, confirm billing stopped, record shutdown, import the cumulative invoice with coverage/reference, and publish a complete report including idle/failed costs and regressions. Follow [unit economics](../economics/unit-economics.md). Do not leave a GPU running after a failed control-plane test.

## Deferred

Automatic provisioning/scaling, heterogeneous multi-provider routing, AMD/ROCm, learned estimators, a provider invoice API importer, per-phase GPU profiling, token-weighted fair queuing, enterprise SLA enforcement and public rollout remain deferred. This release makes those experiments observable; it does not establish their outcome.
