# Rented NVIDIA deployment
No GPU was rented during implementation. These commands are a deployment path requiring a GPU smoke test; throughput/VRAM fit are unmeasured. Obtain explicit expense approval before renting anything. Prefer manually attached capacity first; PROVISIONING_ENABLED stays false.

1. CPU control plane: deploy API/scheduler/PostgreSQL behind HTTPS, restrict DB access, install managed OIDC settings, configure independent session, credential-HMAC and versioned encryption keys, and rotate the worker bootstrap token (see the audit remediation guide). Set EXECUTION_MODE=vllm, MODEL_REVISION to a reviewed 40-character Qwen/Qwen3-4B commit SHA, PUBLIC_BETA_ENABLED=true only after license/rate review. The same tokenizer revision must be installed on the CPU API. Install `.[gpu]`.
2. On an approved 24–48 GB NVIDIA machine install NVIDIA container toolkit. Download reviewed revision; never use floating main for a deployment. Select and record a tested vLLM image digest before release. Reference compatibility image: `vllm/vllm-openai@sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33` (not validated on a GPU here).
3. Start the private model server:
```bash
export MODEL_REVISION=1cfa9a7208912126459214e8b04321603b3df60c
export EXECUTION_MODE=vllm
export PUBLIC_BETA_ENABLED=true
# Install the codebase on this host before deriving the identity-bound served alias.
export SERVED_MODEL_NAME=$(python -m packages.common.identity)
export VLLM_API_KEY=<random-local-engine-secret>
docker run --gpus all --rm --name inferenceflow-vllm \
  -p 127.0.0.1:8000:8000 --ipc=host \
  vllm/vllm-openai@sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33 \
  --model Qwen/Qwen3-4B --revision "$MODEL_REVISION" \
  --tokenizer-revision "$MODEL_REVISION" --served-model-name "$SERVED_MODEL_NAME" \
  --dtype bfloat16 --max-model-len 10240 --max-num-seqs 16 \
  --gpu-memory-utilization 0.85 --api-key "$VLLM_API_KEY" \
  --generation-config vllm --disable-log-requests --no-enable-prefix-caching
```
Check the selected image's `--help` before deployment; version-specific flags must be verified during the smoke test. Do not expose vLLM publicly; its API key does not authenticate all endpoints. Disable cross-tenant prefix caching.

4. Run worker from the codebase on GPU host (it needs no DB credentials):
```bash
pip install -e .
export EXECUTION_MODE=vllm
export MODEL_REVISION=1cfa9a7208912126459214e8b04321603b3df60c
export PUBLIC_BETA_ENABLED=true
export CONTROL_PLANE_URL=https://control.example.com
export WORKER_BOOTSTRAP_TOKEN=<scoped-bootstrap-secret>
export WORKER_ID=nvidia-1
export VLLM_URL=http://127.0.0.1:8000
python -m apps.worker.main
```
The worker checks the revision-derived served alias and generates a canary before registration; a failed canary stops startup. This validates configured deployment identity, not the trustworthiness of a malicious GPU host. It issues up to 16 concurrent calls; vLLM batches continuously. Credentials expire hourly; worker renewal/restart procedures are described in ops.

5. On a seeded/funded test tenant set INFERENCEFLOW_API_KEY, RUN_GPU_E2E=1; run `pytest tests/test_gpu.py -q`, then `python examples/batch.py`. Restart worker during 100-request load, confirm recovery and `cli reconcile` returns zero drift. Record actual GPU uptime and provider bill, then shut down rented pod at provider and confirm billing stopped.

Runpod adapter uses REST v2 (`https://api.runpod.io/v2`), checked against official create/list/delete/catalog docs. Creation uses durable intent and deterministic pod name; ambiguous responses require manual reconciliation. Dedicated provider account, one-GPU limit, supplied confirmed price, daily budget and session ceiling required. Tags are stored as IF_OWNER/IF_ENVIRONMENT/IF_CREATED_BY/IF_JOB_GROUP environment metadata because the published v2 create schema has no generic tags field. Run independent `python -m apps.scheduler.watchdog` on another CPU host with provider read/delete permission; it detects owned orphans and expires instances. Provider-side budget alerts remain necessary during control-plane outage.

Official references: https://docs.runpod.io/api-reference-v2/pods/create-a-pod ; https://docs.vllm.ai/en/stable/serving/online_serving/ ; https://huggingface.co/Qwen/Qwen3-4B .

Exact source artifacts resolved from official Hugging Face/Docker Registry APIs are recorded in `infra/model-lock.json`; resolution is not GPU validation.

## v0.3 first attachment and experiment controls

This section prepares an experiment; it does not authorize GPU spending or a public deployment. Obtain explicit approval for provider, machine, verified hourly/minimum/fee costs, total budget and duration first. Keep the control plane private/VPN-accessible. Use the pinned vLLM/worker commands above after confirming the chosen image's actual flags and hardware compatibility.

1. Keep `PROVISIONING_ENABLED=false`, `STRIPE_ENABLED=false`, `MAX_ACTIVE_GPUS=1` and `ESTIMATOR_CALIBRATED=false`. Set approved daily/session limits and independent provider alerts. Automatic capacity recommendations do not rent GPUs.
2. After approved manual rental, record actual provider identity, quote and start using `python -m packages.common.cli gpu-attach` as documented in [unit economics](economics/unit-economics.md). This command only records metadata. It never provisions a machine.
3. Apply migration 0006 on the control plane and restart API/scheduler/worker together. For the new scheduling experiment set `SCHEDULER_V2_ENABLED=true`, `DEFAULT_COMPLETION_TARGET_SECONDS=3600`. Start with `ADAPTIVE_DISPATCH_ENABLED=false` for a fixed-cap baseline; enable it only for a matched comparison.
4. On the GPU host, export `PROVIDER_INSTANCE_ID=YOUR_TRACKED_PROVIDER_ID`. Set `WORKER_MODEL_LOADING_SECONDS` to weight-loading duration measured from engine startup logs. The separate `GPU_STARTUP_SECONDS` and `MODEL_LOADING_SECONDS` are conservative planning assumptions, not observations. Run the worker command above. It needs worker/engine credentials and model identity, never DB/Stripe/provider secrets.
5. Verify readiness and exact registered identity; inspect `python -m packages.common.cli scheduling-report` on the control plane. At least 20 matching real observations are necessary for observed-throughput estimates, and manual calibration approval is still required. Unknown, stale or incomplete telemetry prevents adaptive expansion; KV >=90% pauses dispatch.
6. Execute `RUN_GPU_E2E=1 python -m pytest tests/test_gpu.py -q` only after configuring an approved real-mode control plane/tenant. Run `python examples/batch.py`, inspect actual output/token usage and restart recovery, then `python -m packages.common.cli reconcile`. The isolated GPU test settings must match the deployed real model identity; do not infer live validation from a skipped test.
7. Follow the [experiment plan](performance/benchmark-plan.md) for matched workload mixes, duration and acceptance gates. Stop at the provider and confirm billing has stopped before `gpu-record-stop`; import the actual invoice with coverage/reference. Check no orphan remains at the provider. Disable both new scheduling flags to restore baseline behavior without touching financial history.

A short smoke establishes attachment/recovery/accounting, not an hour-long SLA. A separately approved sustained load test and actual invoices are required to assess sub-hour reliability and economics. AMD, further providers and unattended autoscaling remain deferred.
