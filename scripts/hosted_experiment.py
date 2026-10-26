"""Opt-in hosted experiment execution. GET-only provider access; never provisions."""

from decimal import Decimal
import json
import os
import re
import subprocess
import sys
import time

import httpx

from scripts import github_staging_host as host
from scripts.experiment_plan import run_plan
from scripts.experiment_policy import switch
from scripts.experiment_telemetry import Collector, PodReader
from scripts.prearmed_cleanup import utc, validate_plan
from scripts.second_gpu_experiment import prepare, coverage, parse_time
from scripts.staging_supervisor import private_write


def validate_session(session):
    fields = {"experiment_id", "gpu_id", "data_center_id", "disk_gb", "all_in_hourly_usd",
              "budget_usd", "max_runtime_minutes"}
    if set(session) != fields or session["disk_gb"] != 80:
        raise ValueError("Exact reviewed session configuration required")
    if not isinstance(session["gpu_id"], str) or not re.fullmatch(r"[A-Z0-9-]+", session["data_center_id"]):
        raise ValueError("Invalid approved hardware/placement")
    validate_plan({"pod_name": "inferenceflow-experiment-"+session["experiment_id"],
        "experiment_id": session["experiment_id"], "all_in_hourly_usd": session["all_in_hourly_usd"],
        "fixed_cost_usd": "0", "budget_usd": session["budget_usd"],
        "max_runtime_minutes": session["max_runtime_minutes"], "cleanup_approved": True,
        "all_in_cost_confirmed": True})


def verify_pod(pod, session, identity):
    env = pod.get("env", {})
    if (pod.get("name") != "inferenceflow-experiment-"+session["experiment_id"]
            or env.get("IF_EXPERIMENT_ID") != session["experiment_id"]
            or env.get("IF_CONTROL_RUN_ID") != identity or env.get("IF_OWNER") != "inferenceflow"
            or env.get("IF_CREATED_BY") != "explicit-operator-approval"
            or pod.get("cloud") != "SECURE" or pod.get("dataCenterId") != session["data_center_id"]
            or pod.get("gpu", {}).get("id") != session["gpu_id"] or pod.get("gpu", {}).get("count") != 1
            or pod.get("disk") != 80 or pod.get("ports") or pod.get("mounts") or pod.get("globalNetworking")):
        raise RuntimeError("Worker pod does not match this approved session")
    cost = Decimal(str(pod.get("cost")))
    if not cost.is_finite() or cost < 0 or cost > Decimal(str(session["all_in_hourly_usd"])):
        raise RuntimeError("Provider price is invalid or over quote")
    created, cutoff = utc(pod["createdAt"]), utc(env["IF_TERMINATE_BY"])
    if created.timestamp() > time.time()+2:
        raise RuntimeError("Provider creation time is in the future")
    if not re.fullmatch(r"[0-9]+", env.get("IF_WATCHDOG_RUN_ID", "")):
        raise RuntimeError("Independent watchdog run identity required")
    if not re.fullmatch(r"[1-9][0-9]*", env.get("IF_WATCHDOG_RUN_ATTEMPT", "")):
        raise RuntimeError("Independent watchdog attempt required")
    if not 0 < (cutoff-created).total_seconds() <= session["max_runtime_minutes"]*60:
        raise RuntimeError("Missing or inconsistent independent cutoff")
    # End normal work after 30 rented minutes or two minutes before independent cutoff.
    stop_at = min(cutoff.timestamp()-120, created.timestamp()+1800)
    if stop_at <= time.time():
        raise RuntimeError("No safe execution time remains")
    return time.monotonic()+stop_at-time.time()


def watchdog_active(run_id, attempt):
    # Anonymous, fixed GitHub destination; provider/API credentials are never forwarded.
    with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as public:
        response = public.get("https://api.github.com/repos/manishklach/InferenceFlow/actions/runs/"+run_id)
        response.raise_for_status()
        data = response.json()
    if (str(data.get("id")) != run_id or data.get("head_branch") != "main"
            or str(data.get("run_attempt")) != attempt
            or data.get("name") != "GPU experiment independent watchdog" or data.get("status") != "in_progress"):
        raise RuntimeError("Independent cleanup job is not active")


def child_environment(connection):
    result = {k: v for k, v in os.environ.items() if k in
              {"PATH", "HOME", "LANG", "LC_ALL", "PYTHONPATH", "SYSTEMROOT", "TEMP", "TMP"}}
    result.update({k: connection[k] for k in ("CONTROL_PLANE_URL", "INFERENCEFLOW_API_KEY", "METRICS_TOKEN")})
    return result


def execute(identity, session, connection, directory):
    validate_session(session)
    if not re.fullmatch(r"[0-9]+-[0-9]+", identity):
        raise ValueError("GitHub run-attempt identity required")
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    reader = PodReader(os.environ.get("RUNPOD_EXPERIMENT_READ_KEY", ""))
    collector = None
    try:
        reader.authenticate()  # No paid operation; read authority must work before waiting.
        pod = None
        deadline = float("inf")
        next_pod_read = 0.0
        with httpx.Client(base_url=connection["CONTROL_PLANE_URL"], timeout=10, trust_env=False) as client:
            wait_until = time.monotonic()+3600
            while time.monotonic() < wait_until:
                if time.monotonic() >= next_pod_read:
                    observed = reader.pod(pod["id"]) if pod else reader.find(session["experiment_id"])
                    next_pod_read = time.monotonic()+10
                    if observed:
                        candidate_deadline = verify_pod(observed, session, identity)
                        deadline = min(deadline, candidate_deadline)
                        pod = observed
                        if collector is None:
                            private_write(directory / "session.json", json.dumps({"pod_id": pod["id"],
                                "created_at": pod["createdAt"], "gpu": session["gpu_id"],
                                "cutoff": pod["env"]["IF_TERMINATE_BY"]}))
                            watchdog_active(pod["env"]["IF_WATCHDOG_RUN_ID"], pod["env"]["IF_WATCHDOG_RUN_ATTEMPT"])
                            collector = Collector(reader, pod["id"], directory)
                            collector.thread.start()  # Capture startup, not only post-readiness samples.
                if pod and time.time()-utc(pod["createdAt"]).timestamp() >= 900:
                    raise RuntimeError("Cold start exceeded fifteen rented minutes")
                r = client.get("/internal/scheduling/report", headers={"Authorization": "Bearer "+connection["METRICS_TOKEN"]})
                r.raise_for_status()
                workers = [w for w in r.json()["workers"] if w.get("telemetry_fresh")]
                if len(workers) > 1:
                    raise RuntimeError("Multiple fresh workers; no admissions allowed")
                if workers:
                    worker = workers[0]
                    if worker.get("mode") != "vllm" or worker.get("hard_limit") != 4:
                        raise RuntimeError("Wrong worker execution mode or hard cap")
                    if pod and worker.get("provider_instance_id") == pod["id"]:
                        break
                    if pod:
                        raise RuntimeError("Worker belongs to a different pod")
                time.sleep(2)
            else:
                raise RuntimeError("Approved manually provisioned worker did not arrive")
        for _ in range(15):
            try:
                collector.healthy()
                break
            except RuntimeError:
                time.sleep(1)
        collector.healthy()
        prepare(directory / "workloads", validation_count=500)
        next_watchdog_check = [float("-inf")]

        def healthy():
            collector.healthy()
            if time.monotonic() >= next_watchdog_check[0]:
                watchdog_active(pod["env"]["IF_WATCHDOG_RUN_ID"], pod["env"]["IF_WATCHDOG_RUN_ATTEMPT"])
                next_watchdog_check[0] = time.monotonic()+60

        def transition(policy):
            switch(policy, host.RUNTIME, connection["CONTROL_PLANE_URL"])

        def stage_run(stage, seconds):
            name = "interruption-500" if stage.name == "interruption" else (
                "smoke-10" if stage.count == 10 else "comparison-100")
            output = directory / stage.name
            command = [sys.executable, "-m", "scripts.gpu_experiment", "run", "--execute", "--policy", stage.policy,
                "--count", str(stage.count), "--run-id", "hosted-"+identity+"-"+stage.name,
                "--workload-file", str(directory / "workloads" / (name+".json")),
                "--output", str(output), "--timeout", str(seconds)]
            with (directory / (stage.name+"-driver.log")).open("w", encoding="utf-8") as log:
                child = subprocess.Popen(command, env=child_environment(connection), cwd=host.ROOT,
                                         stdout=log, stderr=subprocess.STDOUT)
                until = time.monotonic()+seconds+5
                try:
                    while child.poll() is None:
                        healthy()
                        if time.monotonic() >= until:
                            raise RuntimeError("Stage driver deadline reached")
                        time.sleep(1)
                    if child.returncode:
                        raise RuntimeError("Stage driver failed")
                finally:
                    if child.poll() is None:
                        child.terminate()
                        try:
                            child.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            child.kill()
                            child.wait(timeout=5)
            return json.loads((output / "summary.json").read_text())

        def audit(stage, result):
            report = json.loads(host.docker("exec", "-T", "api", "python", "-m",
                "scripts.hosted_real_audit", "--identity", identity).stdout)
            private_write(directory / (stage.name+"-audit.json"), json.dumps(report))
            return report

        def smoke_coverage(stage, result):
            jobs = json.loads((directory / stage.name / "jobs.json").read_text())
            time.sleep(2)  # Capture the final bounded-hold sample at completion.
            report = coverage(collector.snapshot(), min(parse_time(j["created_at"]) for j in jobs),
                              max(parse_time(j["completed_at"]) for j in jobs))
            private_write(directory / "smoke-coverage.json", json.dumps(report))
            return report

        return run_plan(directory / "plan", deadline, transition=transition, execute=stage_run, audit=audit,
                        coverage=smoke_coverage, healthy=healthy)
    finally:
        # Cancel only IDs recorded as accepted by this isolated experiment driver.
        # Ambiguous submissions retain their original intent/idempotency evidence.
        ids = set()
        for observations in directory.glob("*/observations.jsonl"):
            for line in observations.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    if row.get("event") == "accepted":
                        ids.add(row["job"]["id"])
                except (ValueError, KeyError):
                    continue
        with httpx.Client(base_url=connection["CONTROL_PLANE_URL"], timeout=5, trust_env=False,
                          headers={"Authorization": "Bearer "+connection["INFERENCEFLOW_API_KEY"]}) as client:
            for job_id in ids:
                if re.fullmatch(r"job_[A-Za-z0-9_-]+", job_id):
                    try:
                        response = client.get("/v1/jobs/"+job_id)
                        response.raise_for_status()
                        if response.json()["status"] not in {"succeeded", "failed", "partially_succeeded", "canceled", "expired"}:
                            client.post("/v1/jobs/"+job_id+"/cancel").raise_for_status()
                    except httpx.HTTPError:
                        private_write(directory / "cancel-incomplete.json", json.dumps({"requires_reconciliation": True}))
        if collector:
            collector.close()
        reader.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute or os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise SystemExit("Explicit protected main-branch hosted execution required")
    from scripts.github_real_host import COMPOSE
    host.COMPOSE = COMPOSE
    try:
        execute(os.environ["GITHUB_RUN_ID"]+"-"+os.environ["GITHUB_RUN_ATTEMPT"],
            json.loads(os.environ["HOSTED_EXPERIMENT_SESSION"]),
            json.loads((host.RUNTIME / "runner-connection.json").read_text()), host.RUNTIME / "experiment")
    except BaseException as error:
        private_write(host.RUNTIME / "experiment-error.json", json.dumps({"error_type": type(error).__name__}))
        raise SystemExit("Hosted experiment failed; inspect encrypted evidence") from None


if __name__ == "__main__":
    main()
