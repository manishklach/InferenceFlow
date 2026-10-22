# Rented NVIDIA deployment
No GPU was rented during implementation. These commands are a deployment path requiring a GPU smoke test; throughput/VRAM fit are unmeasured. Obtain explicit expense approval before renting anything. Prefer manually attached capacity first; PROVISIONING_ENABLED stays false.

1. CPU control plane: deploy API/scheduler/PostgreSQL behind HTTPS, restrict DB access, install managed OIDC settings, rotate secret and worker bootstrap token. Set EXECUTION_MODE=vllm, MODEL_REVISION to a reviewed 40-character Qwen/Qwen3-4B commit SHA, PUBLIC_BETA_ENABLED=true only after license/rate review. The same tokenizer revision must be installed on the CPU API. Install `.[gpu]`.
2. On an approved 24–48 GB NVIDIA machine install NVIDIA container toolkit. Download reviewed revision; never use floating main for a deployment. Select and record a tested vLLM image digest before release. Reference compatibility image: `vllm/vllm-openai@sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33` (not validated on a GPU here).
3. Start the private model server:
```bash
export MODEL_REVISION=1cfa9a7208912126459214e8b04321603b3df60c
export VLLM_API_KEY=<random-local-engine-secret>
docker run --gpus all --rm --name inferenceflow-vllm \
  -p 127.0.0.1:8000:8000 --ipc=host \
  vllm/vllm-openai@sha256:6cf9808ca8810fc6c3fd0451c2e7784fb224590d81f7db338e7eaf3c02a33d33 \
  --model Qwen/Qwen3-4B --revision "$MODEL_REVISION" \
  --tokenizer-revision "$MODEL_REVISION" --served-model-name qwen3-4b \
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
The worker health-checks and generates a canary before registration. It issues up to 16 concurrent calls; vLLM batches continuously. Credentials expire hourly; worker renewal/restart procedures are described in ops.

5. On a seeded/funded test tenant set INFERENCEFLOW_API_KEY, RUN_GPU_E2E=1; run `pytest tests/test_gpu.py -q`, then `python examples/batch.py`. Restart worker during 100-request load, confirm recovery and `cli reconcile` returns zero drift. Record actual GPU uptime and provider bill, then shut down rented pod at provider and confirm billing stopped.

Runpod adapter uses REST v2 (`https://api.runpod.io/v2`), checked against official create/list/delete/catalog docs. Creation uses durable intent and deterministic pod name; ambiguous responses require manual reconciliation. Dedicated provider account, one-GPU limit, supplied confirmed price, daily budget and session ceiling required. Tags are stored as IF_OWNER/IF_ENVIRONMENT/IF_CREATED_BY/IF_JOB_GROUP environment metadata because the published v2 create schema has no generic tags field. Run independent `python -m apps.scheduler.watchdog` on another CPU host with provider read/delete permission; it detects owned orphans and expires instances. Provider-side budget alerts remain necessary during control-plane outage.

Official references: https://docs.runpod.io/api-reference-v2/pods/create-a-pod ; https://docs.vllm.ai/en/stable/serving/online_serving/ ; https://huggingface.co/Qwen/Qwen3-4B .

Exact source artifacts resolved from official Hugging Face/Docker Registry APIs are recorded in `infra/model-lock.json`; resolution is not GPU validation.
