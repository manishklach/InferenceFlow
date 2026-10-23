"""Deterministic, offline discrete-time scheduling experiment; no GPU/provider API."""
import argparse
import json
import random
from pathlib import Path
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from decimal import Decimal, ROUND_FLOOR
from fractions import Fraction
from packages.common.scheduling import DeadlineEstimator, DispatchPolicy, AdaptiveDispatch
from packages.common.performance import percentiles
from packages.common.config import settings
from packages.common.economics import quoted_cost

SCENARIOS = ("low", "bursty", "sustained", "mixed", "outage", "capacity_change")
# Integer micro-service units avoid platform/libm drift in remaining-work boundaries.
SLOT_PROGRESS = {n: int((Decimal(min(n, 8)) ** Decimal(".65") * 1000000 /
                         (1 + Decimal(max(0, n - 8)) * Decimal(".08")) / n).to_integral_value(rounding=ROUND_FLOOR))
                 for n in range(1, 17)}


def workload(seed, scenario, count):
    rng = random.Random(seed)
    items = []
    for i in range(count):
        arrival = i * (12 if scenario == "low" else 2)
        if scenario == "bursty":
            arrival = (i // 80) * 300
        inp = rng.choice([64, 256, 1024, 4096])
        out = rng.choice([16, 64, 256, 1024])
        items.append({"id": i, "tenant": i % 8, "tier": "standard" if i % 3 else "economy",
                      "arrival": arrival, "deadline": arrival + (rng.choice([120, 300, 3600]) if scenario == "mixed" else 3600),
                      "input": inp, "output": out, "remaining": inp * 2000 + out * 12500,
                      "attempts": 0, "eligible": arrival, "started": None, "ended": None, "status": "pending"})
    return items


def simulate(seed=42, scenario="mixed", variant="baseline", count=240):
    items = workload(seed, scenario, count)
    served = []
    active = {}
    workers = {}
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    est = DeadlineEstimator()
    busy_slot_seconds, rented_seconds, failed_attempts, retries = 0, 0, 0, 0
    rented_by_gpu = {}
    for tick in range(max(r["arrival"] for r in items) + 7201):
        desired = 2 if scenario == "capacity_change" and 240 <= tick < 480 else 1
        cold = tick < 120  # Includes synthetic startup and model loading.
        outage = scenario == "outage" and 180 <= tick < 270
        available_ids = set(range(desired)) if not cold and not outage else set()
        if scenario == "capacity_change" and tick < 360:
            available_ids.discard(1)  # New capacity needs the same 120s cold start.
        rented_seconds += desired
        for wid in range(desired):
            rented_by_gpu[wid] = rented_by_gpu.get(wid, 0) + 1
        for wid in list(active):
            if wid not in available_ids:
                workers.pop(wid, None)
                for r in active.pop(wid):
                    failed_attempts += 1
                    r["remaining"] = r["input"] * 2000 + r["output"] * 12500
                    r["status"] = "queued" if r["attempts"] < 3 else "failed"
                    r["eligible"] = tick + 2 ** r["attempts"]
                    if r["status"] == "failed":
                        r["ended"] = tick
        for r in items:
            if r["status"] == "pending" and tick >= r["arrival"]:
                r["status"] = "queued"
            if r["status"] == "queued" and tick >= r["deadline"]:
                r["status"], r["ended"] = "expired", tick
        served = [(t, tenant) for t, tenant in served if t > tick - 300]
        for wid in sorted(available_ids):
            running = active.setdefault(wid, [])
            w = workers.setdefault(wid, SimpleNamespace(capacity=16, adaptive_limit=2, adaptive_changed_at=None,
                                                         telemetry_at=None, telemetry=None))
            n = len(running)
            w.telemetry = json.dumps({"kv_cache_usage": min(.99, n * .055), "engine_running": n,
                                      "engine_waiting": 0, "gpu_utilization": min(.99, n / 10)})
            w.telemetry_at = stamp + timedelta(seconds=tick)
            limit = 16
            if variant == "adaptive":
                limit = AdaptiveDispatch.update(w, w.telemetry_at, any(r["status"] == "queued" for r in items))
            while len(running) < limit:
                candidates = [r for r in items if r["status"] == "queued" and r["eligible"] <= tick]
                if not candidates:
                    break

                def score(r):
                    age = tick - r["arrival"]
                    served_count = sum(tenant == r["tenant"] for t, tenant in served)
                    if variant == "baseline":
                        return served_count / (4 if r["tier"] == "standard" or age >= 300 else 1) - age / 60, r["deadline"], r["id"]
                    return DispatchPolicy.score(served_count, r["tier"], age, r["deadline"] - tick,
                                                est.duration(r["input"], r["output"]), r["id"])

                r = min(candidates, key=score)
                retries += r["attempts"] > 0
                r["attempts"] += 1
                r["status"] = "running"
                if r["started"] is None:
                    r["started"] = tick
                served.append((tick, r["tenant"]))
                running.append(r)
            n = len(running)
            busy_slot_seconds += n
            if n:
                # Hypothetical saturation curve, identical in all variants, NOT a vLLM model.
                for r in list(running):
                    r["remaining"] -= SLOT_PROGRESS[n]
                    if r["remaining"] <= 0:
                        r["status"], r["ended"] = "succeeded", tick + 1
                        running.remove(r)
        if all(r["status"] in ("succeeded", "failed", "expired") for r in items):
            break
    done = [r for r in items if r["status"] == "succeeded"]
    tokens = sum(r["input"] + r["output"] for r in done)
    cost = sum(quoted_cost(seconds, 1000000, 60) for seconds in rented_by_gpu.values())
    tenant_rates = [Fraction(sum(r["status"] == "succeeded" for r in items if r["tenant"] == tenant),
                            max(1, sum(r["tenant"] == tenant for r in items))) for tenant in range(8)]
    fairness = sum(tenant_rates) ** 2 / (8 * sum(r * r for r in tenant_rates)) if sum(tenant_rates) else None
    return {"scenario": scenario, "variant": variant, "seed": seed, "requests": count,
            "successful": len(done), "expired": sum(r["status"] == "expired" for r in items),
            "failed": sum(r["status"] == "failed" for r in items), "failed_attempts": failed_attempts,
            "retried_executions": retries, "throughput_requests_per_second": len(done) / max(1, tick + 1),
            "queue_latency_seconds": percentiles([r["started"] - r["arrival"] for r in items if r["started"] is not None]),
            "completion_seconds": percentiles([r["ended"] - r["arrival"] for r in done]),
            "deadline_attainment_success_only": sum(r["ended"] <= r["deadline"] for r in done) / len(done) if done else None,
            "accepted_success_within_target_fraction": sum(r["ended"] <= r["deadline"] for r in done) / count,
            "tenant_completion_fairness_jain": float(fairness) if fairness is not None else None,
            "gpu_utilization_slot_proxy": busy_slot_seconds / max(1, 16 * rented_seconds),
            "estimated_gpu_cost_micro_usd": cost,
            "estimated_cost_per_million_total_tokens_micro_usd": cost * 1000000 / tokens if tokens else None}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--count", type=int, default=240)
    p.add_argument("--output", default=".runtime/benchmark-v03.json")
    args = p.parse_args()
    if not 8 <= args.count <= 5000:
        p.error("--count must be 8..5000")
    c = settings()
    # All variant comparisons use the same conservative controller configuration.
    c.adaptive_dispatch_enabled = True
    c.adaptive_initial_slots = 2
    c.adaptive_cooldown_seconds = 30
    c.telemetry_stale_seconds = 45
    c.estimator_input_tokens_per_second = 100
    c.estimator_output_tokens_per_second = 20
    c.estimator_uncertainty_margin = 1.5
    result = {"kind": "simulation_not_real_gpu", "seed": args.seed,
              "assumptions": {"prefill_tokens_per_second": 500, "decode_tokens_per_second": 80,
                              "hourly_quote_micro_usd": 1000000, "cold_start_seconds": 120,
                              "engine": "hypothetical saturation curve; no vLLM or provider contacted"},
              "results": [simulate(args.seed, scenario, variant, args.count) for scenario in SCENARIOS
                          for variant in ("baseline", "deadline", "adaptive")]}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(result, indent=2) + "\n").encode("utf-8"))
    print(f"Wrote {path}: {len(result['results'])} deterministic simulation runs; not GPU measurements.")


if __name__ == "__main__":
    main()
