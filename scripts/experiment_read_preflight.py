"""Authenticate the approved experiment reader without modifying provider resources."""

import json
import os
import re
import httpx

from scripts.experiment_telemetry import PodReader
from scripts.experiment_http import get, failure_receipt


def probe_absent_pod(reader, pod_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,100}", pod_id):
        raise ValueError("Invalid previously terminated pod identity")
    results = {}
    for name, path in (("pod_detail_status", "/pods/"+pod_id), ("pod_logs_status", "/pods/"+pod_id+"/logs")):
        try:
            with reader.client.stream("GET", path) as response:
                response.raise_for_status()
                raise RuntimeError("Probe expected an already terminated pod; no changes made")
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 404:
                raise
            results[name] = 404
    return {**results, "live_log_stream_verified": False}


def probe_github(run_id):
    if not re.fullmatch(r"[1-9][0-9]*", run_id):
        raise ValueError("Invalid public GitHub run identity")
    with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as public:
        response = get(public, "https://api.github.com/repos/manishklach/InferenceFlow/actions/runs/"+run_id)
        if str(response.json().get("id")) != run_id:
            raise RuntimeError("Wrong public run identity")
    return {"anonymous_github_status": response.status_code}


def main():
    reader = None
    probes = {}
    try:
        reader = PodReader(os.environ.get("RUNPOD_EXPERIMENT_READ_KEY", ""))
        reader.authenticate()
        if os.environ.get("EXPERIMENT_PROBE_ABSENT_POD_ID"):
            probes.update(probe_absent_pod(reader, os.environ["EXPERIMENT_PROBE_ABSENT_POD_ID"]))
        if os.environ.get("EXPERIMENT_PROBE_GITHUB_RUN_ID"):
            probes.update(probe_github(os.environ["EXPERIMENT_PROBE_GITHUB_RUN_ID"]))
    except Exception as error:
        # Never print provider response bodies, headers or credential values.
        print(json.dumps({"failed": failure_receipt(error), "provider_mutations": False}))
        raise SystemExit("Experiment read preflight failed") from None
    finally:
        if reader is not None:
            reader.close()
    print(json.dumps({"authenticated_pod_read": True, "provider_mutations": False,
                      "log_stream_permission_tested": False, "gpu_created": False, **probes}))


if __name__ == "__main__":
    main()
