"""Explicitly gated real-GPU load/telemetry tools. Import/prepare never calls an API."""
import argparse
import hashlib
import json
import math
import os
import subprocess
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit


TERMINAL = {"succeeded", "failed", "partially_succeeded", "canceled", "expired"}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def append(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps({"observed_at": stamp(), **data}) + "\n")


def workload(count, run_id):
    """Unique synthetic content; real tokenizer lengths are measured by the API."""
    if count not in (10, 100, 1000):
        raise ValueError("Choose 10, 100 or 1000 requests")
    rows = []
    for index in range(count):
        medium = index % 5 == 0
        rows.append({"custom_id": f"{run_id}-{index:04d}",
                     "messages": [{"role": "user", "content":
                         f"Record {index}. Summarize the following synthetic logistics notes in two sentences. "
                         + ("The shipment arrived safely. The depot checked inventory and recorded delivery. "
                            * (64 if medium else 16))}],
                     "max_output_tokens": 256 if medium else 128, "temperature": 0, "top_p": 1})
    return rows


def batches(rows):
    return [rows[index:index + 100] for index in range(0, len(rows), 100)]


def percentile(values, p):
    return sorted(values)[max(0, math.ceil(p * len(values)) - 1)] if values else None


def poll_interval(job_count):
    # One read per job plus performance per cycle; target <=60 reads/minute,
    # leaving headroom under the API's existing 120 requests/minute tenant cap.
    return max(5, job_count + 1)


def summarize(jobs, results, elapsed, cost_usd=None):
    good = [r for r in results if r["status"] == "succeeded"]
    input_tokens = sum(r["usage"]["input_tokens"] for r in good)
    output_tokens = sum(r["usage"]["output_tokens"] for r in good)
    durations = []
    under_hour_jobs = under_hour_requests = 0
    for job in jobs:
        if job.get("completed_at") and job.get("created_at"):
            duration = (datetime.fromisoformat(job["completed_at"].replace("Z", "+00:00"))
                        - datetime.fromisoformat(job["created_at"].replace("Z", "+00:00"))).total_seconds()
            if job["status"] == "succeeded":
                durations.append(duration)
                if duration <= 3600:
                    under_hour_jobs += 1
                    under_hour_requests += job["total"]
    accepted = sum(j["total"] for j in jobs)
    tokens = input_tokens + output_tokens
    return {"accepted_jobs": len(jobs), "accepted_requests": accepted,
            "successful_requests": len(good), "unsuccessful_or_unfinished_requests": accepted - len(good),
            "all_accepted_jobs_successful_within_hour": under_hour_jobs / len(jobs) if jobs else None,
            # Whole-job completion provides a conservative request-level lower bound.
            "all_accepted_requests_successful_within_hour_lower_bound": under_hour_requests / accepted if accepted else None,
            "successful_job_seconds": {f"p{p}": percentile(durations, p / 100) for p in (50, 95, 99)},
            "elapsed_seconds": elapsed, "input_tokens": input_tokens, "output_tokens": output_tokens,
            "requests_per_second": len(good) / elapsed if elapsed > 0 else None,
            "input_tokens_per_second": input_tokens / elapsed if elapsed > 0 else None,
            "output_tokens_per_second": output_tokens / elapsed if elapsed > 0 else None,
            "provided_cost_usd": str(cost_usd) if cost_usd is not None else None,
            "provided_cost_per_million_total_tokens_usd":
                str(Decimal(str(cost_usd)) * 1000000 / tokens) if cost_usd is not None and tokens else None,
            "cost_provenance": "operator-supplied; verify invoice coverage, not customer charges",
            "request_timing_limit": "Results API omits per-request timestamps; use read-only DB export for exact request attainment."}


def require_execute(args):
    if not args.execute:
        raise SystemExit("No execution authorized: add --execute only AFTER explicit provisioning/test approval")


def live_readiness(client, metric_key, worker_id, timeout=35):
    """A new engine canary/poll response, not a cached telemetry snapshot."""
    headers = {"Authorization": "Bearer " + metric_key}
    response = client.client.post("/internal/experiments/readiness", headers=headers, json={"worker_id": worker_id})
    response.raise_for_status()
    challenge = response.json()["challenge"]
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        response = client.client.get("/internal/experiments/readiness/" + challenge, headers=headers)
        response.raise_for_status()
        if response.json().get("ready") is True:
            return challenge
        time.sleep(.25)
    raise RuntimeError("Fresh worker/engine readiness was not proven; no workload submitted")


def live_run(args):
    require_execute(args)
    from packages.python_sdk import InferenceFlowClient

    origin = os.environ.get("CONTROL_PLANE_URL", "")
    if urlsplit(origin).scheme != "https" or not urlsplit(origin).hostname:
        raise SystemExit("An approved HTTPS CONTROL_PLANE_URL is required")
    key = os.environ.get("INFERENCEFLOW_API_KEY", "")
    if not key:
        raise SystemExit("Set INFERENCEFLOW_API_KEY securely")
    directory = Path(args.output)
    directory.mkdir(parents=True, exist_ok=False)
    workload_file = getattr(args, "workload_file", None)
    rows = json.loads(Path(workload_file).read_text(encoding="utf-8")) if workload_file else workload(args.count, args.run_id)
    if len(rows) != args.count or len({row["custom_id"] for row in rows}) != len(rows):
        raise ValueError("Workload count and unique custom IDs must match the selected stage")
    # Payloads are synthetic. Persist IDs before submission for ambiguous-response recovery.
    (directory / "workload.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    started = time.monotonic()
    deadline = started + args.timeout
    jobs, results = [], []
    with InferenceFlowClient(key, origin) as client:
        models = client.get_models()
        if models["models"][0]["execution_mode"] != "vllm":
            raise SystemExit("Refusing a mock or unknown execution mode")
        model = models["models"][0]
        expected_revision = "1cfa9a7208912126459214e8b04321603b3df60c"
        if model.get("revision") != expected_revision or model.get("tokenizer_revision") != expected_revision:
            raise SystemExit("Refusing an unpinned/mismatched model or tokenizer")
        policy = getattr(args, "policy", "baseline")
        metric_key = os.environ.get("METRICS_TOKEN", "")
        if not metric_key:
            raise SystemExit("METRICS_TOKEN required to verify actual scheduling policy before load")
        response = client.client.get("/internal/scheduling/report", headers={"Authorization": "Bearer " + metric_key})
        response.raise_for_status()
        operator = response.json()
        expected_flags = {"sequential": (False, False), "baseline": (False, False),
                          "deadline_fixed": (True, False), "adaptive": (True, True)}[policy]
        config = operator.get("configuration", {})
        if (config.get("scheduler_v2_enabled"), config.get("adaptive_dispatch_enabled")) != expected_flags:
            raise SystemExit("Actual server flags do not match the selected experiment policy")
        if config.get("provisioning_enabled") is not False or config.get("execution_mode") != "vllm":
            raise SystemExit("Experiment requires real mode and disabled provisioning")
        if config.get("public_beta_enabled") is not False or config.get("stripe_enabled") is not False:
            raise SystemExit("Experiment requires disabled public beta and Stripe")
        expected_cap = 1 if policy == "sequential" else 4
        if config.get("max_inflight") != expected_cap or config.get("estimator_calibrated") is not False:
            raise SystemExit("Experiment requires matching tenant concurrency cap and uncalibrated estimator")
        inventory = operator.get("workers", [])
        if (len(inventory) != 1 or inventory[0].get("mode") != "vllm" or inventory[0].get("hard_limit") != 4
                or not inventory[0].get("provider_instance_id") or not inventory[0].get("telemetry_fresh")):
            raise SystemExit("Exactly one real-mode experiment worker with a four-slot hard cap required")
        append(directory / "observations.jsonl", {"event": "verified_policy", "policy": policy, "report": operator})
        append(directory / "observations.jsonl", {"event": "before", "models": models, "wallet": client.get_wallet()})
        for index, batch in enumerate(batches(rows)):
            if time.monotonic() >= deadline:
                break
            idem = f"gpu-experiment-{args.run_id}-{index}"
            proof = live_readiness(client, metric_key, inventory[0]["id"])
            append(directory / "observations.jsonl", {"event": "submission_intent", "idempotency_key": idem})
            # SDK retries preserve the same key. On ambiguity abort; never invent a new key.
            job = client.create_job(batch, idempotency_key=idem, deadline_seconds=3600,
                                    experiment_readiness=proof,
                                    admission_policy="best_effort")
            jobs.append(job)
            append(directory / "observations.jsonl", {"event": "accepted", "job": job})
        complete = False
        while not complete and time.monotonic() < deadline:
            jobs = [client.get_job(j["id"]) for j in jobs]
            append(directory / "observations.jsonl", {"event": "poll", "jobs": jobs,
                                                     "performance": client.get_performance()})
            if any("usage_mismatch" in j.get("error_summary", []) for j in jobs):
                raise RuntimeError("Usage mismatch: stop admissions, reconcile and terminate at provider")
            complete = all(j["status"] in TERMINAL for j in jobs)
            if not complete:
                time.sleep(min(poll_interval(len(jobs)), max(0, deadline - time.monotonic())))
        for job in jobs:
            cursor = 0
            while cursor is not None:
                page = client.get_results(job["id"], cursor=cursor)
                results.extend(page["items"])
                cursor = page["next_cursor"]
        append(directory / "observations.jsonl", {"event": "after", "wallet": client.get_wallet()})
        # Read-only journal snapshot; this tool never seeds or changes wallet/rates.
        cursor = 0
        while cursor is not None:
            response = client.client.get("/v1/wallet/transactions", params={"cursor": cursor, "limit": 100})
            response.raise_for_status()
            page = response.json()
            append(directory / "observations.jsonl", {"event": "journal_page", "data": page})
            cursor = page["next_cursor"]
    report = {**summarize(jobs, results, time.monotonic() - started, args.cost_usd),
              "workload_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
              "policy": policy, "server_configuration": config, "model": model, "workers": inventory}
    for name, data in (("jobs", jobs), ("results", results), ("summary", report)):
        (directory / (name + ".json")).write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if len(results) != args.count or any(r["status"] != "succeeded" for r in results):
        raise SystemExit("Stage incomplete/failed. Evidence saved; stop admissions and follow cleanup runbook.")
    if [r["custom_id"] for r in results] != [r["custom_id"] for r in rows]:
        raise SystemExit("Missing, duplicate or unordered custom IDs")
    if any(not r.get("output_text") or r["output_text"].startswith("MOCK") for r in results):
        raise SystemExit("Real output validation failed")
    if any(r["usage"]["input_tokens"] <= 0 or r["usage"]["output_tokens"] <= 0 for r in results):
        raise SystemExit("Missing or nonpositive usage")


def compact_engine_sample(record):
    """Keep provider stdout below its 16 KiB fragment size; raw data stays on disk."""
    from prometheus_client.parser import text_string_to_metric_families

    output = {key: record[key] for key in ("observed_at", "event", "metrics_error", "hardware_error") if key in record}
    output["schema_version"] = 1
    names = {"vllm:num_requests_running", "vllm:num_requests_waiting", "vllm:prompt_tokens_total",
             "vllm:generation_tokens_total", "vllm:iteration_tokens_total_count", "vllm:iteration_tokens_total_sum",
             "vllm:gpu_cache_usage_perc", "vllm:kv_cache_usage_perc", "vllm:request_success_total"}
    if "prometheus" in record:
        metrics = {}
        try:
            for family in text_string_to_metric_families(record["prometheus"]):
                for sample in family.samples:
                    if sample.name in names and math.isfinite(sample.value):
                        metrics[sample.name] = metrics.get(sample.name, 0) + sample.value
            output["engine_metrics"] = metrics
        except ValueError:
            output["metrics_error"] = "invalid_prometheus"
    if "nvidia_smi_csv" in record:
        if len(json.dumps(record["nvidia_smi_csv"]).encode("utf-8")) <= 4096:
            output["nvidia_smi_csv"] = record["nvidia_smi_csv"]
        else:
            output["hardware_error"] = "sample_too_large"
    return output


def collect(args):
    require_execute(args)
    import httpx
    # Engine metrics stay on Pod loopback. No listener/public endpoint is created.
    path = Path(args.output)
    end = time.monotonic() + args.seconds
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=3, trust_env=False) as client:
        while time.monotonic() < end:
            record = {"event": "engine_sample"}
            try:
                response = client.get("/metrics")
                response.raise_for_status()
                # Keep raw counters/histograms for later deltas and metric-version differences.
                record["prometheus"] = response.text
            except Exception as exc:
                record["metrics_error"] = type(exc).__name__
            try:
                sample = subprocess.run(["nvidia-smi", "--query-gpu=timestamp,uuid,name,utilization.gpu,"
                                         "utilization.memory,memory.used,memory.total,power.draw",
                                         "--format=csv"], capture_output=True, text=True, timeout=3, check=True)
                record["nvidia_smi_csv"] = sample.stdout
            except Exception as exc:
                record["hardware_error"] = type(exc).__name__
            record["observed_at"] = stamp()
            append(path, record)
            # Also export to provider container logs if the process exits before disk export.
            print(json.dumps(compact_engine_sample(record)), flush=True)
            time.sleep(args.interval)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="Write synthetic workload only; no network or spend")
    run = sub.add_parser("run", help="Execute only after explicit approval; never provisions GPUs")
    run.add_argument("--workload-file", help="Prepared identical synthetic workload shared across comparison arms")
    for command in (prepare, run):
        command.add_argument("--count", type=int, choices=[10, 100, 1000], required=True)
        command.add_argument("--run-id", required=True)
        command.add_argument("--output", required=True)
    run.add_argument("--execute", action="store_true")
    run.add_argument("--policy", choices=["sequential", "baseline", "deadline_fixed", "adaptive"], required=True)
    run.add_argument("--timeout", type=int, default=3600, choices=range(1, 3601))
    run.add_argument("--cost-usd", type=Decimal, help="Optional cost with matching coverage; not wallet capture")
    metrics = sub.add_parser("collect", help="Pod-private metrics collection; no cloud API")
    metrics.add_argument("--execute", action="store_true")
    metrics.add_argument("--output", required=True)
    metrics.add_argument("--seconds", type=int, default=7200, choices=range(1, 7201))
    metrics.add_argument("--interval", type=int, default=5, choices=range(1, 61))
    report = sub.add_parser("report", help="Offline CPM from saved results and one cumulative provider cost")
    report.add_argument("--directories", nargs="+", required=True)
    report.add_argument("--cost-usd", type=Decimal, required=True)
    report.add_argument("--cost-reference", required=True, help="Invoice/reference with exact coverage")
    report.add_argument("--cost-kind", choices=["estimate", "actual_invoice"], required=True)
    report.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as output:
            json.dump({"kind": "synthetic_workload_no_execution", "requests": workload(args.count, args.run_id)}, output, indent=2)
        print("Prepared workload; no API called")
    elif args.command == "run":
        live_run(args)
    elif args.command == "collect":
        collect(args)
    else:
        if args.cost_usd < 0:
            raise SystemExit("Cost must be nonnegative")
        jobs, results, elapsed = [], [], 0
        seen = set()
        for name in args.directories:
            folder = Path(name)
            batch = json.loads((folder / "jobs.json").read_text(encoding="utf-8"))
            for job in batch:
                if job["id"] in seen:
                    raise SystemExit("Duplicate job coverage; refuse double-counted results")
                seen.add(job["id"])
            jobs.extend(batch)
            results.extend(json.loads((folder / "results.json").read_text(encoding="utf-8")))
            elapsed += json.loads((folder / "summary.json").read_text(encoding="utf-8"))["elapsed_seconds"]
        data = {**summarize(jobs, results, elapsed, args.cost_usd),
                "cost_kind": args.cost_kind, "cost_reference": args.cost_reference,
                "coverage": args.directories, "throughput_window": "sum of measured stage wall times; excludes cold/idle time"}
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
        print("Offline cost report written; no provider, inference or wallet API called")


if __name__ == "__main__":
    main()
