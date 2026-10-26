"""Loopback-only, disposable mock Compose rehearsal; never calls a GPU provider."""

import json
import os
import time

import httpx

from packages.python_sdk import InferenceFlowClient
from scripts import github_staging_host as host
from scripts.experiment_commands import Mailbox
from datetime import datetime, timedelta, timezone
from scripts.gpu_experiment import workload


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Disposable GitHub runner required")
    host.RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=False)
    values, postgres = host.configuration({"OIDC_ISSUER": "https://rehearsal.invalid/",
        "OIDC_AUDIENCE": "offline-rehearsal", "OIDC_JWKS_URL": "https://rehearsal.invalid/jwks"})
    values.update(ESTIMATOR_CALIBRATED="false", SCHEDULER_V2_ENABLED="false")
    host.write_env(host.RUNTIME / "control.env", values)
    host.write_env(host.RUNTIME / "postgres.env", postgres)
    host.write_env(host.RUNTIME / "worker.env", {"ENVIRONMENT": "development", "EXECUTION_MODE": "mock",
        "MODEL_REVISION": "mock-v1", "CONTROL_PLANE_URL": "http://api:8080",
        "WORKER_BOOTSTRAP_TOKEN": values["WORKER_BOOTSTRAP_TOKEN"], "WORKER_CAPACITY": "4",
        "WORKER_ID": "policy-rehearsal", "PROVIDER_INSTANCE_ID": "mock-only"})
    origin = "http://127.0.0.1:18086"
    report = {"mode": "mock", "gpu_measurement": False, "stages": []}
    try:
        host.docker("up", "-d", "--build", "--wait", "postgres", "api", "scheduler", "worker")
        identity = os.environ["GITHUB_RUN_ID"]+"-"+os.environ["GITHUB_RUN_ATTEMPT"]
        seeded = json.loads(host.docker("exec", "-T", "-e", "HOSTED_DISPOSABLE_MOCK=true", "api",
            "python", "-m", "scripts.hosted_mock_pipeline", "seed", "--run-id", identity).stdout)
        with InferenceFlowClient(seeded["key"], origin) as client:
            mailbox = Mailbox(host.RUNTIME, origin, identity, clock=lambda: time.monotonic()*100)
            for index, policy in enumerate(("sequential", "baseline", "adaptive", "baseline")):
                mailbox.tick(fetch=lambda: {"run_id": identity, "sequence": index+1, "policy": policy,
                    "expires_at": (datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()})
                # Keep the original worker process alive across API/scheduler restarts.
                for _ in range(45):
                    with httpx.Client(base_url=origin, timeout=10, trust_env=False) as operator:
                        response = operator.get("/internal/scheduling/report",
                            headers={"Authorization": "Bearer "+values["METRICS_TOKEN"]})
                        response.raise_for_status()
                        workers = response.json()["workers"]
                    if len(workers) == 1 and workers[0]["telemetry_fresh"]:
                        break
                    time.sleep(2)
                else:
                    raise RuntimeError("Worker did not reconnect")
                job = client.create_job(workload(10, f"policy-{index}"), idempotency_key=f"rehearsal-{index}")
                job = client.wait_for_job(job["id"], timeout=120, poll_interval=1)
                if job["status"] != "succeeded":
                    raise RuntimeError("Mock stage failed")
                host.docker("exec", "-T", "api", "python", "-m", "scripts.hosted_mock_pipeline", "audit",
                    "--job-id", job["id"], "--output", "/tmp/policy-audit.json")
                report["stages"].append({"policy": policy, "successful_requests": 10,
                    "audit_passed": True, "worker_reconnected": True})
        report["passed"] = True
    finally:
        host.docker("down", "--volumes", "--timeout", "15")
    (host.ROOT / ".runtime/policy-rehearsal.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report))  # Only aggregate mock results; no secrets or raw evidence.


if __name__ == "__main__":
    main()
