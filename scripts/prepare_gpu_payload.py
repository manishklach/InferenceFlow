"""Build an inert Community Cloud experiment payload; never calls Runpod."""
import json
import hashlib
from pathlib import Path


def build_payload():
    root = Path(__file__).resolve().parents[1]
    folder = root / "infra/first-gpu"
    lock = json.loads((root / "infra/model-lock.json").read_text(encoding="utf-8"))
    launcher = (folder / "launch.sh").read_text(encoding="utf-8")
    overlays = ["apps/worker/engines.py", "apps/worker/main.py", "packages/common/config.py",
                "scripts/gpu_experiment.py", "scripts/experiment_worker.py"]
    hashes = {}
    overlay_commands = []
    for index, name in enumerate(overlays):
        source = (root / name).read_text(encoding="utf-8")
        hashes[name] = hashlib.sha256(source.encode("utf-8")).hexdigest()
        marker = f"INFERENCEFLOW_REVIEWED_SOURCE_{index}"
        overlay_commands.append(f"cat > {name} <<'{marker}'\n{source}\n{marker}\n")
    # Reviewed overlays are embedded literally and hashed; never fetch floating main.
    bootstrap = """set -euo pipefail
: "${CONTROL_PLANE_URL:?Approved reachable HTTPS control plane required}"
: "${WORKER_BOOTSTRAP_TOKEN:?Scoped experiment credential required}"
[[ "$CONTROL_PLANE_URL" == https://* && "$CONTROL_PLANE_URL" != *REPLACE_* ]] || exit 2
[[ "$WORKER_BOOTSTRAP_TOKEN" != REPLACE_* ]] || exit 2
python3 -c 'import importlib.metadata as m; assert m.version("vllm") == "0.8.5"'
mkdir -p /opt/inferenceflow
cd /opt/inferenceflow
git init -q
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin https://github.com/manishklach/InferenceFlow.git
else
  git remote add origin https://github.com/manishklach/InferenceFlow.git
fi
git fetch --depth 1 origin c62386b2b6347f2555375fbd448d14769d852646
# Reapply the reviewed overlays below on every start, including a retained disk.
# Only the known application checkout is reset; model cache/evidence stay intact.
git checkout --detach --force FETCH_HEAD
python3 -m venv /opt/inferenceflow-worker
/opt/inferenceflow-worker/bin/python -m pip install --no-cache-dir -r requirements.lock
/opt/inferenceflow-worker/bin/python -m pip install --no-deps -e .
""" + "\n".join(overlay_commands) + "\n" + launcher
    payload = {"name": "inferenceflow-first-gpu-review-required", "cloud": "COMMUNITY",
               "image": lock["vllm_image"],
               "gpu": {"id": "NVIDIA GeForce RTX 4090", "count": 1, "minCudaVersion": "12.8",
                       "minRamPerGpu": 32, "minVcpuCountPerGpu": 8},
               # No data center is invented: current Community availability is NONE.
               # Replace only after a fresh per-DC placement read and approval.
               "disk": 80, "ports": [], "entrypoint": ["/bin/bash", "-lc"], "cmd": [bootstrap],
               "env": {"CONTROL_PLANE_URL": "https://REPLACE_WITH_APPROVED_PRIVATE_CONTROL_PLANE",
                       "WORKER_BOOTSTRAP_TOKEN": "REPLACE_WITH_SCOPED_EXPERIMENT_SECRET",
                       "PROVISIONING_ENABLED": "false", "STRIPE_ENABLED": "false",
                       "EXPERIMENT_INTERRUPT_PREFIX": "",
                       "IF_SOURCE_HASHES": json.dumps(hashes, sort_keys=True),
                       "IF_OWNER": "inferenceflow", "IF_ENVIRONMENT": "experiment",
                       "IF_CREATED_BY": "operator-approval-required", "IF_JOB_GROUP": "first-real-gpu"}}
    return payload


def main():
    payload = build_payload()
    path = Path(__file__).resolve().parents[1] / "infra/first-gpu/runpod-pod.proposed.json"
    path.write_bytes((json.dumps(payload, indent=2) + "\n").encode("utf-8"))
    print("Prepared inert Community Cloud payload; no resource created. Availability/placement/approval remain required.")


if __name__ == "__main__":
    main()
