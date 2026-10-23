"""Offline comparison of verified policy runs; no provider or inference calls."""
import argparse
import json
import hashlib
from pathlib import Path


def compare(directories, include_sequential=False):
    groups = {}
    for directory in directories:
        folder = Path(directory)
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        audit = json.loads((folder / "audit.json").read_text(encoding="utf-8"))
        if not audit["passed"] or audit["measurement_modes"] != ["vllm"]:
            raise ValueError("Passing real-mode timing/billing audit required")
        policy = summary["policy"]
        count = summary["accepted_requests"]
        policies = ("sequential", "baseline", "adaptive") if include_sequential else ("baseline", "adaptive")
        if count not in (10, 100, 1000) or policy not in policies:
            raise ValueError("Comparison requires selected policies and 10/100/1000 requests")
        if (count, policy) in groups:
            raise ValueError("Duplicate arm; use a separate report for replicate runs")
        cost_file = folder / "cost.json"
        cost = json.loads(cost_file.read_text(encoding="utf-8")) if cost_file.exists() else {}
        workload = json.loads((folder / "workload.json").read_text(encoding="utf-8"))
        payload_hash = hashlib.sha256(json.dumps([{k: v for k, v in row.items() if k != "custom_id"}
                                                  for row in workload], sort_keys=True).encode()).hexdigest()
        groups[count, policy] = {"directory": str(folder), "completion_seconds": audit["accepted_to_last_terminal_seconds"],
                                 "driver_wall_seconds_including_observation": summary["elapsed_seconds"],
                                 "payload_hash_without_custom_ids": payload_hash,
                                 "model_revision": summary["model"]["revision"],
                                 "worker_instances": sorted(str(w.get("provider_instance_id")) for w in summary["workers"]),
                                 "p95_request_seconds": audit["request_e2e_seconds_successful_only"]["p95"],
                                 "all_accepted_request_deadline_attainment": audit["all_accepted_requests_successful_within_60_minutes"],
                                 "successful_requests": audit["statuses"].get("succeeded", 0),
                                 "retry_attempts": audit["retried_attempts"],
                                 "customer_captured_micro_usd": audit["captured_micro_usd"],
                                 "provider_cost_per_million_tokens_usd": cost.get("provided_cost_per_million_total_tokens_usd"),
                                 "cost_kind": cost.get("cost_kind", "missing"),
                                 "cost_reference": cost.get("cost_reference"),
                                 "output_tokens_per_second": summary["output_tokens_per_second"]}
    rows = []
    for count in (10, 100, 1000):
        if (count, "baseline") not in groups or (count, "adaptive") not in groups:
            raise ValueError(f"Missing matched pair for {count}")
        base, adaptive = groups[count, "baseline"], groups[count, "adaptive"]
        for field in ("payload_hash_without_custom_ids", "model_revision", "worker_instances"):
            if base[field] != adaptive[field]:
                raise ValueError(f"Unmatched workload/model/worker: {field}")
        rows.append({"request_count": count, "baseline": base, "adaptive": adaptive,
                     "output_throughput_speedup": adaptive["output_tokens_per_second"] / base["output_tokens_per_second"]
                     if base["output_tokens_per_second"] else None,
                     "concurrency_efficiency": "Not computed across different time-varying adaptive caps"})
        if include_sequential:
            sequential = groups.get((count, "sequential"))
            if sequential is None:
                raise ValueError(f"Missing sequential arm for {count}")
            for field in ("payload_hash_without_custom_ids", "model_revision", "worker_instances"):
                if sequential[field] != base[field]:
                    raise ValueError(f"Unmatched sequential workload/model/worker: {field}")
            rows[-1]["sequential"] = sequential
            rows[-1]["fixed_concurrency_4_speedup"] = (
                base["output_tokens_per_second"] / sequential["output_tokens_per_second"]
                if sequential["output_tokens_per_second"] else None)
    return {"kind": "manually_approved_real_gpu_comparison", "rows": rows,
            "cautions": ["Audit does not prove GPU batching; correlate worker overlap and vLLM sequence metrics",
                         "No significance/SLA claim from one pair; review output quality and decoding lengths",
                         "Missing or allocated/estimated provider costs are not actual provider invoices"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directories", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--include-sequential", action="store_true")
    args = parser.parse_args()
    report = compare(args.directories, args.include_sequential)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print("Offline matched comparison written; no performance claim made without provided evidence")


if __name__ == "__main__":
    main()
