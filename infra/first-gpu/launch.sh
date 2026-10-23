#!/bin/bash
# REVIEW ONLY: this runs INSIDE a paid Pod after explicit authorization.
# No Docker-in-Docker, inbound vLLM port, database credential or provider key needed.
set -euo pipefail
: "${CONTROL_PLANE_URL:?Set the approved reachable private HTTPS control plane}"
: "${WORKER_BOOTSTRAP_TOKEN:?Set a separate experiment bootstrap credential}"
[[ "$CONTROL_PLANE_URL" == https://* ]] || exit 2
[[ "${WORKER_BOOTSTRAP_TOKEN}" != REPLACE_* ]] || exit 2
export ENVIRONMENT=staging EXECUTION_MODE=vllm PUBLIC_BETA_ENABLED=false REVIEWED_GPU_EXPERIMENT_ENABLED=true
export MODEL_REPO=Qwen/Qwen3-4B
export MODEL_REVISION=1cfa9a7208912126459214e8b04321603b3df60c
export VLLM_URL=http://127.0.0.1:8000 VLLM_USE_V1=1
export WORKER_CAPACITY=4
export WORKER_TRACE_PATH=/opt/experiment-evidence/worker-overlap.jsonl
export HF_HOME=/opt/hf-cache PYTHONUNBUFFERED=1
export VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1 HF_HUB_DISABLE_TELEMETRY=1
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
  --dtype bfloat16 --max-model-len 10240 --max-num-seqs 4 \
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
# Metrics/hardware samples go to both ephemeral disk and provider stdout logs.
# This collector does not contact Runpod or modify the customer ledger.
$worker_python -m scripts.gpu_experiment collect --execute \
  --output /opt/experiment-evidence/engine.jsonl --seconds 7200 --interval 1 &
telemetry_pid=$!
restarts=0
while kill -0 "$engine_pid" 2>/dev/null; do
  if [[ -n "${EXPERIMENT_INTERRUPT_PREFIX:-}" ]]; then
    $worker_python -m scripts.experiment_worker --enable-interruption \
      --prefix "$EXPERIMENT_INTERRUPT_PREFIX" --after 5 \
      --marker /opt/experiment-evidence/interruption-fired &
  else
    $worker_python -m apps.worker.main &
  fi
  worker_pid=$!
  status=0
  wait -n "$engine_pid" "$worker_pid" || status=$?
  if ! kill -0 "$engine_pid" 2>/dev/null; then break; fi
  if (( status == 75 && restarts == 0 )); then
    restarts=1
    echo 'Controlled experiment interruption; re-registering worker, preserving vLLM'
    sleep 2
  else
    break
  fi
done
echo 'Engine/worker exited; export evidence and TERMINATE POD at provider'
exit 5
