"""Offline workload-aware provider ranking. Never provisions or changes active providers."""

from dataclasses import dataclass
import math
from packages.common.provider_discovery import Offer, compare_offers


@dataclass(frozen=True)
class WorkloadProfile:
    offer: Offer
    compatible: bool | None
    input_tokens_per_second: float | None
    output_tokens_per_second: float | None
    startup_seconds: float | None
    reliability: float | None
    performance_reference: str
    performance_is_real: bool = False


def compare_workload(profiles, input_tokens, output_tokens, deadline_seconds, stamp=None):
    if input_tokens < 0 or output_tokens < 0 or not math.isfinite(deadline_seconds) or deadline_seconds <= 0:
        raise ValueError("Nonnegative token counts and positive finite deadline required")
    ranked, excluded = [], []
    for p in profiles:
        quote = compare_offers([p.offer], stamp)
        reason = None
        if not quote["ranked"]:
            reason = quote["excluded"][0]["reason"]
        elif p.compatible is not True:
            reason = "model_compatibility_unverified"
        elif not p.performance_reference or any(
            x is None or not math.isfinite(x) or x <= 0
            for x in [p.input_tokens_per_second, p.output_tokens_per_second, p.reliability]
        ):
            reason = "missing_or_invalid_performance"
        elif (
            p.reliability > 1
            or p.startup_seconds is None
            or not math.isfinite(p.startup_seconds)
            or p.startup_seconds < 0
        ):
            reason = "invalid_startup_or_reliability"
        if reason:
            excluded.append({"provider": p.offer.provider, "offer_id": p.offer.offer_id, "reason": reason})
            continue
        # Conservative serial prefill+decode estimate; retry allowance uses reliability,
        # not a guarantee of meeting a deadline or independent real failure events.
        seconds = (
            p.startup_seconds
            + (input_tokens / p.input_tokens_per_second + output_tokens / p.output_tokens_per_second) / p.reliability
        )
        if seconds > deadline_seconds:
            excluded.append(
                {"provider": p.offer.provider, "offer_id": p.offer.offer_id, "reason": "estimated_deadline_miss"}
            )
            continue
        increment = p.offer.billing_increment_seconds
        billed = math.ceil(seconds / increment) * increment
        cost = math.ceil(billed * quote["ranked"][0]["total_micro_usd_per_hour"] / 3600)
        ranked.append(
            {
                "provider": p.offer.provider,
                "offer_id": p.offer.offer_id,
                "estimated_completion_seconds": seconds,
                "estimated_cost_micro_usd": cost,
                "deadline_slack_seconds": deadline_seconds - seconds,
                "performance_reference": p.performance_reference,
                "performance_is_real": p.performance_is_real,
            }
        )
    ranked.sort(
        key=lambda row: (
            row["estimated_cost_micro_usd"],
            row["estimated_completion_seconds"],
            row["provider"],
            row["offer_id"],
        )
    )
    return {
        "mode": "simulation_only",
        "ranked": ranked,
        "excluded": excluded,
        "automatic_provisioning": False,
        "automatic_failover": False,
        "note": "Profiles are operator assumptions; measured throughput must match model, GPU, decoding and workload.",
    }
