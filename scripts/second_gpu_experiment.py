"""Offline second-experiment preparation and compact telemetry coverage gate."""
import argparse
import csv
import hashlib
import io
import json
import math
from datetime import datetime
from pathlib import Path
from scripts.gpu_experiment import workload


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=False)
    files = {}
    for name, count, prefix in (("smoke-10", 10, "smoke"), ("comparison-100", 100, "matched"),
                                ("comparison-1000", 1000, "matched"),
                                ("interruption-100", 100, "gpu-test-interruption")):
        content = (json.dumps(workload(count, prefix), sort_keys=True, indent=2)+"\n").encode()
        (folder/(name+".json")).write_bytes(content)
        files[name] = {"count": count, "sha256": hashlib.sha256(content).hexdigest()}
    plan = {"kind": "preparation_only_no_resources", "workloads": files,
            "matched_100_policies": ["sequential", "baseline", "adaptive"],
            "paid_execution_authorized": False, "required_gates": ["fresh_quote_and_approval", "independent_armed_cleanup",
                "live_worker_canary_challenge", "smoke_10_and_coverage", "matched_100_and_audits",
                "interruption_and_billing", "remaining_time_and_budget_before_1000"],
            "maximum_original_budget_usd": 10, "inference_guard_budget_usd": 8,
            "public_beta": False, "stripe": False, "automatic_provisioning": False}
    (folder/"plan.json").write_text(json.dumps(plan, indent=2)+"\n", encoding="utf-8")
    return plan


def parse_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Explicit timezone required")
    return parsed.timestamp()


def coverage(samples, start, end):
    if end <= start:
        raise ValueError("Positive measured window required")
    valid = {}
    invalid = 0
    for row in samples:
        try:
            if row.get("schema_version") != 1 or row.get("event") != "engine_sample":
                raise ValueError("Wrong compact schema")
            timestamp = parse_time(row["observed_at"])
            metrics = row["engine_metrics"]
            required = ["vllm:num_requests_running", "vllm:num_requests_waiting",
                        "vllm:prompt_tokens_total", "vllm:generation_tokens_total"]
            if not all(math.isfinite(metrics[name]) and metrics[name] >= 0 for name in required):
                raise ValueError("Missing/invalid counters")
            hardware = list(csv.DictReader(io.StringIO(row["nvidia_smi_csv"])))
            utils = [float({k.strip(): v.strip() for k,v in gpu.items()}["utilization.gpu [%]"].split()[0]) for gpu in hardware]
            if not utils or not all(math.isfinite(v) and 0 <= v <= 100 for v in utils):
                raise ValueError("Missing/invalid hardware")
            valid[timestamp] = max(utils)
        except (KeyError, ValueError, TypeError, AttributeError):
            invalid += 1
    ordered = sorted(valid)
    covered = weighted = 0.0
    for index, timestamp in enumerate(ordered):
        next_sample = ordered[index+1] if index+1 < len(ordered) else timestamp+1.5
        seconds = max(0, min(end, next_sample, timestamp+1.5)-max(start, timestamp))
        covered += seconds
        weighted += seconds*valid[timestamp]
    fraction = covered/(end-start)
    return {"passed": fraction >= .9, "required_coverage_fraction": .9, "coverage_fraction": fraction,
            "covered_seconds": covered, "unknown_seconds": max(0, end-start-covered),
            "valid_unique_samples": len(ordered), "invalid_samples": invalid,
            "gpu_utilization_percent_covered_intervals_only": weighted/covered if covered else None,
            "method": "Zero-order hold capped at 1.5 seconds per sample; duplicates deduplicated. Uncovered intervals are unknown, never zero. This gate covers only the specified smoke window, not the entire rental."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--output", required=True)
    p = sub.add_parser("coverage")
    p.add_argument("--samples", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(Path(args.output))
        print("Prepared identical workloads and gates; no network call or provisioning")
    else:
        samples = [json.loads(line) for line in Path(args.samples).read_text(encoding="utf-8").splitlines() if line]
        result = coverage(samples, parse_time(args.start), parse_time(args.end))
        with Path(args.output).open("x", encoding="utf-8") as out:
            json.dump(result, out, indent=2)
        if not result["passed"]:
            raise SystemExit("Coverage failed; do not increase load")


if __name__ == "__main__":
    main()
