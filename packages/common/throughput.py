"""Offline qualification and advisory dispatch. No DB, provider or worker mutations."""
from collections import Counter
from statistics import median
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator
from packages.common.receipt_format import canonical_sha256


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Identity(Strict):
    model: str = Field(min_length=1, max_length=200)
    revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    tokenizer_revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    engine: str = Field(pattern=r"^(vllm|deepinfer|mock)$")
    engine_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    runtime_config_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    precision: str = Field(min_length=1, max_length=40)
    gpu: str = Field(min_length=1, max_length=100)
    gpu_count: int = Field(ge=1, le=256)
    topology: str = Field(min_length=1, max_length=200)
    context_limit: int = Field(ge=1, le=2_097_152)
    prompt_min: int = Field(ge=1)
    prompt_max: int = Field(ge=1)
    output_max: int = Field(ge=1)

    @model_validator(mode="after")
    def bounds(self):
        if self.prompt_min > self.prompt_max or self.prompt_max+self.output_max > self.context_limit:
            raise ValueError("Workload bucket exceeds pinned context")
        return self


class Tuning(Strict):
    concurrency: int = Field(ge=1, le=128)
    resident_token_budget: int = Field(ge=1, le=268_435_456)
    max_batched_tokens: int = Field(ge=1, le=2_097_152)
    draft_tokens: int = Field(ge=0, le=5)


class Observation(Strict):
    identity: Identity
    tuning: Tuning
    run_id: str = Field(min_length=1, max_length=200)
    pair_id: str = Field(min_length=1, max_length=200)
    workload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_mode: str = Field(pattern=r"^(real|mock)$")
    scope: str = Field(pattern=r"^(direct_engine|queue_pipeline)$")
    total_requests: int = Field(ge=1, le=100_000)
    successful_requests: int = Field(ge=0)
    successful_output_tokens: int = Field(ge=0)
    elapsed_seconds: FiniteFloat = Field(gt=0)
    p95_seconds: FiniteFloat = Field(ge=0)
    quality_score: FiniteFloat | None = Field(default=None, ge=0, le=1)
    final_token_counts_known: bool = False
    cost_usd: FiniteFloat | None = Field(default=None, ge=0)
    cost_scope: str = Field(default="unknown", pattern=r"^(unknown|warm_estimate|full_rental_invoiced)$")
    telemetry_coverage: FiniteFloat = Field(ge=0, le=1)
    peak_memory_fraction: FiniteFloat | None = Field(default=None, ge=0, le=1)
    oom_count: int = Field(default=0, ge=0)
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def counts(self):
        if self.successful_requests > self.total_requests:
            raise ValueError("Success count exceeds admissions")
        if not self.successful_requests and self.successful_output_tokens:
            raise ValueError("Failed work cannot contribute successful tokens")
        return self

    @property
    def tps(self):
        return self.successful_output_tokens/self.elapsed_seconds

    @property
    def cost_per_million(self):
        if self.cost_usd is None or not self.successful_output_tokens or not self.final_token_counts_known:
            return None
        return self.cost_usd*1_000_000/self.successful_output_tokens


class Qualification(Strict):
    minimum_pairs: int = Field(default=3, ge=3)
    minimum_requests: int = Field(default=100, ge=10)
    minimum_seconds: FiniteFloat = Field(default=30.0, ge=1)
    minimum_gain: FiniteFloat = Field(default=0.20, ge=0)
    maximum_p95_ratio: FiniteFloat = Field(default=1.10, ge=1)
    minimum_quality: FiniteFloat = Field(default=0.95, ge=0, le=1)
    minimum_coverage: FiniteFloat = Field(default=0.90, ge=0, le=1)
    maximum_memory: FiniteFloat = Field(default=0.85, gt=0, lt=1)
    validity_seconds: int = Field(default=604800, ge=1, le=604800)


def digest(value: BaseModel | dict):
    data = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return canonical_sha256(data)


class Profile(Strict):
    identity: Identity
    tuning: Tuning
    baseline: Tuning
    workload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    scope: str = Field(pattern=r"^(direct_engine|queue_pipeline)$")
    created_at_epoch: FiniteFloat = Field(ge=0)
    expires_at_epoch: FiniteFloat = Field(ge=0)
    minimum_paired_gain: FiniteFloat = Field(ge=0)
    p95_seconds: FiniteFloat = Field(ge=0)
    evidence_hashes: list[Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]] = Field(min_length=6)
    profile_sha256: str = Field(default="", pattern=r"^([a-f0-9]{64})?$")

    @model_validator(mode="after")
    def validity(self):
        if (not 0 < self.expires_at_epoch-self.created_at_epoch <= 604800
                or len(set(self.evidence_hashes)) != len(self.evidence_hashes)):
            raise ValueError("Unique paired evidence and expiry within seven days required")
        return self

    def integrity_valid(self):
        return (self.expires_at_epoch > self.created_at_epoch
                and self.profile_sha256 == digest(self.model_dump(exclude={"profile_sha256"})))


def evidence_errors(row: Observation, policy: Qualification):
    errors = []
    if row.execution_mode != "real" or row.identity.engine == "mock":
        errors.append("mock_evidence")
    if row.successful_requests != row.total_requests or row.oom_count:
        errors.append("failed_or_incomplete_requests")
    if row.total_requests < policy.minimum_requests or row.elapsed_seconds < policy.minimum_seconds:
        errors.append("insufficient_sustained_load")
    if not row.final_token_counts_known or row.successful_output_tokens <= 0:
        errors.append("unknown_successful_final_tokens")
    if row.quality_score is None or row.quality_score < policy.minimum_quality:
        errors.append("quality_not_validated")
    if row.cost_scope != "full_rental_invoiced" or row.cost_usd is None:
        errors.append("fully_loaded_invoice_missing")
    if row.telemetry_coverage < policy.minimum_coverage:
        errors.append("insufficient_telemetry")
    if row.peak_memory_fraction is None or row.peak_memory_fraction > policy.maximum_memory:
        errors.append("memory_headroom_not_validated")
    return errors


def qualify(rows: list[Observation], baseline: Tuning, *, now: float,
            policy: Qualification | None = None):
    """Reject bad repeats rather than cherry-picking successful trials. Unsigned evidence."""
    policy = policy or Qualification()
    if not rows:
        raise ValueError("Observations required")
    identities = {digest(row.identity) for row in rows}
    workloads = {(row.workload_sha256, row.scope) for row in rows}
    if len(identities) != 1 or len(workloads) != 1:
        raise ValueError("Do not compare different artifacts, workloads, hardware or measurement scopes")
    if len({row.run_id for row in rows}) != len(rows):
        raise ValueError("Duplicate run evidence")
    if len({row.evidence_sha256 for row in rows}) != len(rows):
        raise ValueError("Duplicate per-trial evidence")
    base = [row for row in rows if row.tuning == baseline]
    base_errors = sorted({error for row in base for error in evidence_errors(row, policy)})
    if len(base) < policy.minimum_pairs:
        base_errors.append("insufficient_baseline_repeats")
    if any(n != 1 for n in Counter(row.pair_id for row in base).values()):
        base_errors.append("duplicate_baseline_pair")
    groups: dict[str, list[Observation]] = {}
    for row in rows:
        if row.tuning != baseline:
            groups.setdefault(digest(row.tuning), []).append(row)
    candidates = []
    profiles = []
    for key, trials in sorted(groups.items()):
        errors = set(base_errors)
        errors.update(error for row in trials for error in evidence_errors(row, policy))
        pairs = Counter(row.pair_id for row in trials)
        if len(trials) < policy.minimum_pairs or set(pairs) != {row.pair_id for row in base}:
            errors.add("unmatched_or_insufficient_pairs")
        if any(n != 1 for n in pairs.values()):
            errors.add("duplicate_candidate_pair")
        gains = []
        for trial in trials:
            reference = next((row for row in base if row.pair_id == trial.pair_id), None)
            if (reference is None or reference.tps <= 0 or not reference.final_token_counts_known
                    or not trial.final_token_counts_known):
                continue
            gain = trial.tps/reference.tps-1
            gains.append(gain)
            if trial.total_requests != reference.total_requests:
                errors.add("request_count_mismatch")
            if gain+1e-12 < policy.minimum_gain:
                errors.add("throughput_gain_below_target")
            if trial.p95_seconds > reference.p95_seconds*policy.maximum_p95_ratio:
                errors.add("p95_regression")
            if (trial.quality_score is not None and reference.quality_score is not None
                    and trial.quality_score < reference.quality_score):
                errors.add("quality_regression")
            cost, base_cost = trial.cost_per_million, reference.cost_per_million
            if cost is not None and base_cost is not None and cost > base_cost:
                errors.add("fully_loaded_cost_regression")
        candidates.append({"tuning_id": key, "tuning": trials[0].tuning.model_dump(),
                           "eligible": not errors, "reasons": sorted(errors),
                           "minimum_paired_gain": min(gains) if gains else None,
                           "median_successful_output_tps": median(row.tps for row in trials)
                           if all(row.final_token_counts_known for row in trials) else None})
        if not errors:
            profile = Profile(identity=rows[0].identity, tuning=trials[0].tuning, baseline=baseline,
                workload_sha256=rows[0].workload_sha256, scope=rows[0].scope,
                created_at_epoch=now, expires_at_epoch=now+policy.validity_seconds,
                minimum_paired_gain=min(gains), p95_seconds=max(row.p95_seconds for row in trials),
                evidence_hashes=sorted(digest(row) for row in base+trials))
            profile = profile.model_copy(update={"profile_sha256": digest(profile.model_dump(exclude={"profile_sha256"}))})
            profiles.append((median(row.tps for row in trials), key, profile))
    selected = sorted(profiles, key=lambda item: (-item[0], item[1]))
    return {"live_scheduler_enabled": False, "baseline_reasons": base_errors, "candidates": candidates,
            "profile": selected[0][2].model_dump() if selected else None,
            "evidence_trust": "Operator-supplied unsigned evidence; hashes are not independent attestation."}


class Snapshot(Strict):
    observed_at_epoch: FiniteFloat = Field(ge=0)
    active_requests: int = Field(ge=0)
    resident_tokens: int = Field(ge=0)
    memory_fraction: FiniteFloat = Field(ge=0, le=1)
    error_rate: FiniteFloat = Field(ge=0, le=1)
    p95_seconds: FiniteFloat = Field(ge=0)


class Pending(Strict):
    request_id: str = Field(min_length=1, max_length=200)
    tenant_id: str = Field(min_length=1, max_length=200)
    prompt_tokens: int = Field(ge=1)
    output_limit: int = Field(ge=1)
    deadline_epoch: FiniteFloat = Field(ge=0)


def recommend(identity: Identity, baseline: Tuning, snapshot: Snapshot | None,
              queue: list[Pending], *, now: float, hard_limit: int,
              tenant_remaining: dict[str, int], profile: Profile | None = None,
              engine_tuning: Tuning | None = None, use_profile: bool = False):
    """Pure replay only. Preserve caller's fair ordering; never lease or alter engine flags."""
    if type(hard_limit) is not int or not 1 <= hard_limit <= 128 or any(
            type(v) is not int or v < 0 for v in tenant_remaining.values()):
        raise ValueError("Validated hard cap and tenant headroom required")
    if len({item.request_id for item in queue}) != len(queue):
        raise ValueError("Duplicate queued request")
    tuning, reason, paused = baseline, "baseline", False
    fresh = snapshot is not None and 0 <= now-snapshot.observed_at_epoch <= 10
    if snapshot is not None and snapshot.memory_fraction >= .90:
        reason, paused = "critical_memory_even_if_stale", True
    elif use_profile:
        if profile is None or not profile.integrity_valid():
            reason = "missing_or_corrupt_profile"
        elif profile.identity != identity or profile.baseline != baseline:
            reason = "identity_or_baseline_mismatch"
        elif not profile.created_at_epoch <= now < profile.expires_at_epoch:
            reason = "profile_expired_or_future"
        elif not fresh:
            reason = "telemetry_stale_or_missing"
        elif snapshot is not None and (snapshot.error_rate > .01 or snapshot.memory_fraction > .85
                                       or snapshot.p95_seconds > profile.p95_seconds*1.10):
            reason = "health_regression"
        elif engine_tuning is None or (engine_tuning.max_batched_tokens, engine_tuning.draft_tokens) != (
                profile.tuning.max_batched_tokens, profile.tuning.draft_tokens):
            reason = "engine_reconfiguration_required"
        else:
            tuning, reason = profile.tuning, "qualified_profile"
    # Stale active/resident counts cannot establish safe available token capacity.
    if not fresh:
        paused = True
        if reason == "baseline":
            reason = "telemetry_stale_or_missing"
    if engine_tuning is None or (engine_tuning.max_batched_tokens, engine_tuning.draft_tokens) != (
            tuning.max_batched_tokens, tuning.draft_tokens):
        paused = True
        reason += ":engine_reconfiguration_required"
    active = snapshot.active_requests if snapshot is not None else 0
    resident = snapshot.resident_tokens if snapshot is not None else 0
    available = max(0, min(hard_limit, tuning.concurrency)-active) if not paused else 0
    tokens = max(0, tuning.resident_token_budget-resident)
    remaining = dict(tenant_remaining)
    admitted, deferred, deadline_risk = [], [], []
    for index, item in enumerate(queue):
        if item.deadline_epoch <= now:
            deferred.append({"request_id": item.request_id, "reason": "expired"})
            continue
        if not identity.prompt_min <= item.prompt_tokens <= identity.prompt_max or item.output_limit > identity.output_max:
            deferred.append({"request_id": item.request_id, "reason": "outside_profile_bucket"})
            continue
        if remaining.get(item.tenant_id, 0) <= 0:
            deferred.append({"request_id": item.request_id, "reason": "tenant_cap"})
            continue
        required = item.prompt_tokens+item.output_limit
        if not available or required > tokens:
            deferred.append({"request_id": item.request_id, "reason": "capacity_or_resident_token_budget"})
            # Do not reorder shorter jobs around the fair queue head to manufacture TPS.
            deferred.extend({"request_id": later.request_id, "reason": "unexamined_after_capacity"}
                            for later in queue[index+1:])
            break
        admitted.append(item.request_id)
        if reason == "qualified_profile" and profile is not None and now+profile.p95_seconds > item.deadline_epoch:
            deadline_risk.append(item.request_id)
        available -= 1
        tokens -= required
        remaining[item.tenant_id] -= 1
    return {"advisory_only": True, "live_scheduler_enabled": False, "reason": reason,
            "tuning": tuning.model_dump(), "admit": admitted, "deferred": deferred,
            "deadline_risk": deadline_risk,
            "remaining_resident_token_budget": tokens, "deadline_guaranteed": False}
