#!/bin/bash
# REVIEW ONLY: this runs INSIDE a paid Pod after explicit authorization.
# No Docker-in-Docker, inbound vLLM port, database credential or provider key needed.
set -euo pipefail
: "${CONTROL_PLANE_URL:?Set the approved reachable private HTTPS control plane}"
: "${WORKER_BOOTSTRAP_TOKEN:?Set a separate experiment bootstrap credential}"
[[ "$CONTROL_PLANE_URL" == https://* ]] || exit 2
[[ "${WORKER_BOOTSTRAP_TOKEN}" != REPLACE_* ]] || exit 2
export EXECUTION_MODE=vllm PUBLIC_BETA_ENABLED=true
export MODEL_REPO=Qwen/Qwen3-4B
export MODEL_REVISION=1cfa9a7208912126459214e8b04321603b3df60c
export VLLM_URL=http://127.0.0.1:8000 VLLM_USE_V1=1
export HF_HOME=/opt/hf-cache PYTHONUNBUFFERED=1
export WORKER_ID="first-gpu-${RUNPOD_POD_ID:?Run inside Runpod}"
export PROVIDER_INSTANCE_ID="$RUNPOD_POD_ID"
export VLLM_API_KEY
VLLM_API_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
cd /opt/inferenceflow
worker_python=/opt/inferenceflow-worker/bin/python
export SERVED_MODEL_NAME
SERVED_MODEL_NAME=$($worker_python -m packages.common.identity)
engine_pid= worker_pid= telemetry_pid=
cleanup() {
  for child in "$worker_pid" "$telemetry_pid" "$engine_pid"; do
    if [[ -n "$child" ]]; then kill "$child" 2>/dev/null || true; fi
  done
}
trap cleanup EXIT
trap 'exit 143' TERM INT
started=$SECONDS
python3 -m vllm.entrypoints.openai.api_server \
  --host 127.0.0.1 --port 8000 \
  --model "$MODEL_REPO" --revision "$MODEL_REVISION" \
  --tokenizer-revision "$MODEL_REVISION" --served-model-name "$SERVED_MODEL_NAME" \
  --dtype bfloat16 --max-model-len 10240 --max-num-seqs 16 \
  --gpu-memory-utilization 0.85 --api-key "$VLLM_API_KEY" \
  --generation-config vllm --disable-log-requests --no-enable-prefix-caching &
engine_pid=$!
until curl --silent --fail --max-time 5 http://127.0.0.1:8000/health >/dev/null; do
  kill -0 "$engine_pid" 2>/dev/null || exit 3
  if (( SECONDS - started > 900 )); then echo 'Engine readiness timeout; TERMINATE POD at provider'; exit 4; fi
  sleep 5
done
# Startup-to-health includes downloads and initialization. It is not weight-load
# time; keep the loading observation unknown until measured from engine logs.
echo "engine_start_to_health_seconds=$((SECONDS - started))"
export WORKER_MODEL_LOADING_SECONDS=0
# Hardware sampling is independent of the worker's 15-second heartbeat.
nvidia-smi --query-gpu=timestamp,uuid,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw \
  --format=csv -l 5 &
telemetry_pid=$!
$worker_python -m apps.worker.main &
worker_pid=$!
wait -n "$engine_pid" "$worker_pid"
echo 'Engine/worker exited; export evidence and TERMINATE POD at provider'
exit 5
