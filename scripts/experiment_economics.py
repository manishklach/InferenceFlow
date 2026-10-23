"""Offline economics from explicit experiment evidence. Never reads wallets or calls providers."""

import argparse
import json
import math
from decimal import Decimal, ROUND_CEILING
from pathlib import Path


def report(data):
    required = [
        "input_tokens",
        "output_tokens",
        "successful_jobs",
        "accepted_jobs",
        "jobs_within_deadline",
        "paid_seconds",
        "startup_seconds",
        "cost_kind",
        "cost_reference",
        "compute_usd",
        "storage_usd",
        "ancillary_usd",
    ]
    if any(k not in data for k in required):
        raise ValueError("Explicit tokens, timings, cost components and provenance required")
    for k in ["input_tokens", "output_tokens", "successful_jobs", "accepted_jobs", "jobs_within_deadline"]:
        if type(data[k]) is not int or data[k] < 0:
            raise ValueError("Nonnegative integer counts required")
    if not data["jobs_within_deadline"] <= data["successful_jobs"] <= data["accepted_jobs"]:
        raise ValueError("Inconsistent completion counts")
    for k in ["paid_seconds", "startup_seconds"]:
        if not math.isfinite(data[k]) or data[k] < 0:
            raise ValueError("Finite nonnegative timing required")
    if data["startup_seconds"] > data["paid_seconds"]:
        raise ValueError("Startup exceeds paid coverage")
    if data["cost_kind"] not in ("estimate", "actual_invoice") or not data["cost_reference"]:
        raise ValueError("Explicit estimate/invoice provenance required")
    costs = [Decimal(str(data[k])) for k in ["compute_usd", "storage_usd", "ancillary_usd"]]
    if any(not x.is_finite() or x < 0 for x in costs):
        raise ValueError("Finite nonnegative costs required; unknown is not zero")
    total = sum(costs)

    def per(n):
        return str(total * 1000000 / n) if n else None

    samples = data.get("hardware_intervals", [])
    observed = idle = weighted = 0.0
    for row in samples:
        seconds, util = row["seconds"], row["gpu_utilization_fraction"]
        if not math.isfinite(seconds) or not math.isfinite(util) or seconds < 0 or not 0 <= util <= 1:
            raise ValueError("Invalid hardware interval")
        observed += seconds
        weighted += seconds * util
        if util == 0:
            idle += seconds
    if observed > data["paid_seconds"]:
        raise ValueError("Hardware intervals exceed paid coverage; overlapping/duplicate samples forbidden")
    result = {
        **{k: data[k] for k in required},
        "total_usd": str(total),
        "input_normalized_cost_per_million_usd": per(data["input_tokens"]),
        "output_normalized_cost_per_million_usd": per(data["output_tokens"]),
        "blended_cost_per_million_usd": per(data["input_tokens"] + data["output_tokens"]),
        "cost_per_completed_job_usd": str(total / data["successful_jobs"]) if data["successful_jobs"] else None,
        "deadline_attainment_all_accepted": data["jobs_within_deadline"] / data["accepted_jobs"]
        if data["accepted_jobs"]
        else None,
        "observed_gpu_seconds": observed,
        "unobserved_gpu_seconds": data["paid_seconds"] - observed,
        "sampled_zero_utilization_seconds": idle if samples else None,
        "effective_utilization_over_observed_fraction": weighted / observed if observed else None,
        "warning": "Input/output normalized costs each allocate the WHOLE bill: do not add them. Hardware idle is sampled, not kernel timing.",
    }
    hosted = data.get("hosted_alternative")
    if hosted:
        if not hosted.get("equivalent_model_and_workload") or not hosted.get("source"):
            raise ValueError("Hosted comparison requires explicit equivalence and source")
        prices = [Decimal(str(hosted[k])) for k in ["input_usd_per_million", "output_usd_per_million"]]
        if any(not x.is_finite() or x < 0 for x in prices):
            raise ValueError("Invalid hosted price")
        alternative = (prices[0] * data["input_tokens"] + prices[1] * data["output_tokens"]) / 1000000
        result["hosted_cost_usd"] = str(alternative)
        result["cost_advantage_fraction"] = str(1 - total / alternative) if alternative else None
        result["hosted_source"] = hosted["source"]
    return result


def sensitivity(hourly_usd, useful_tokens_per_second, workload_tokens, utilization, startup_seconds, retry_fraction):
    values = [hourly_usd, useful_tokens_per_second, workload_tokens, utilization, startup_seconds, retry_fraction]
    if (
        any(not math.isfinite(float(v)) for v in values)
        or hourly_usd < 0
        or useful_tokens_per_second <= 0
        or workload_tokens <= 0
        or not 0 < utilization <= 1
        or startup_seconds < 0
        or not 0 <= retry_fraction < 1
    ):
        raise ValueError("Invalid sensitivity assumptions")
    seconds = startup_seconds + workload_tokens / (useful_tokens_per_second * utilization * (1 - retry_fraction))
    cost = Decimal(str(hourly_usd)) * Decimal(str(seconds)) / 3600
    return {
        "kind": "hypothetical_sensitivity_not_gpu_measurement",
        "paid_seconds": seconds,
        "cost_micro_usd": int((cost * 1000000).to_integral_value(rounding=ROUND_CEILING)),
        "blended_cost_per_million_usd": str(cost * 1000000 / Decimal(str(workload_tokens))),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = report(json.loads(Path(args.input).read_text(encoding="utf-8")))
    with Path(args.output).open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print("Offline economics written; cost provenance retained, no customer accounting changed")


if __name__ == "__main__":
    main()
