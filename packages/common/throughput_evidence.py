"""Join an explicitly reviewed invoice/telemetry/quality record to one benchmark hash."""
from pydantic import Field, FiniteFloat

from packages.common.throughput import Observation, Strict, digest


class Review(Strict):
    benchmark_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    identity_evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    invoice_evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    telemetry_evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    quality_evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    full_rental_cost_usd: FiniteFloat = Field(ge=0)
    telemetry_coverage: FiniteFloat = Field(ge=0, le=1)
    peak_memory_fraction: FiniteFloat = Field(gt=0, le=1)
    quality_score: FiniteFloat = Field(ge=0, le=1)


def attach(benchmark: dict, review: Review):
    if digest(benchmark) != review.benchmark_sha256:
        raise ValueError("Review belongs to a different benchmark")
    row = Observation.model_validate(benchmark["observation"])
    quality = min(row.quality_score, review.quality_score) if row.quality_score is not None else review.quality_score
    return Observation.model_validate({**row.model_dump(), "quality_score": quality,
        "cost_usd": review.full_rental_cost_usd, "cost_scope": "full_rental_invoiced",
        "telemetry_coverage": review.telemetry_coverage, "peak_memory_fraction": review.peak_memory_fraction,
        "evidence_sha256": digest({"benchmark": benchmark, "review": review.model_dump()})})
