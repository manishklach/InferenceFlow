"""Explainable request-level scheduling. No provider calls or token batching here."""
import json
import math
from dataclasses import dataclass, asdict
from datetime import timedelta
from sqlalchemy import select
from packages.common.config import settings
from packages.common.db import Job, Work, Worker, ExecutionAttempt, Instance, now

ACTIVE = {"queued", "leased", "running", "billing_pending"}


def identity(repo, revision, tokenizer_revision, mode):
    return json.dumps([repo, revision, tokenizer_revision, mode], separators=(",", ":"))


def current_identity():
    c = settings()
    return identity(c.model_repo, c.model_revision, c.model_revision, c.execution_mode)


def worker_identity(worker):
    return identity(worker.repo, worker.revision, worker.tokenizer_revision, worker.execution_mode)


def telemetry(worker, stamp):
    try:
        data = json.loads(worker.telemetry or "{}")
    except (ValueError, TypeError):
        return {}, False
    fresh = worker.telemetry_at is not None and 0 <= (stamp - worker.telemetry_at).total_seconds() <= settings().telemetry_stale_seconds
    if not isinstance(data, dict):
        return {}, False
    for key, value in data.items():
        if key == "active":
            continue
        if not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
            return {}, False
        if key in {"kv_cache_usage", "gpu_utilization", "recent_error_rate"} and value > 1:
            return {}, False
    if data.get("engine_running", 0) > worker.capacity or data.get("engine_waiting", 0) > worker.capacity * 4:
        fresh = False
    return data, fresh


def available_limit(worker, stamp):
    data, fresh = telemetry(worker, stamp)
    # A previously observed critical memory condition is not cleared by telemetry loss.
    if data.get("kv_cache_usage", 0) >= .9:
        return 0
    if not settings().adaptive_dispatch_enabled:
        return worker.capacity
    if not fresh or not all(k in data for k in ("kv_cache_usage", "engine_running", "engine_waiting")):
        return min(worker.capacity, settings().adaptive_initial_slots)
    return min(worker.capacity, max(1, worker.adaptive_limit))


class AdaptiveDispatch:
    @staticmethod
    def update(worker, stamp, demand):
        c = settings()
        data, fresh = telemetry(worker, stamp)
        safe = min(c.adaptive_initial_slots, worker.capacity)
        if not fresh or not all(k in data for k in ("kv_cache_usage", "engine_running", "engine_waiting")):
            worker.adaptive_limit = safe
            return safe
        limit = min(worker.capacity, max(1, worker.adaptive_limit))
        cooled = worker.adaptive_changed_at is None or (stamp - worker.adaptive_changed_at).total_seconds() >= c.adaptive_cooldown_seconds
        new_sample = worker.adaptive_changed_at is None or worker.telemetry_at > worker.adaptive_changed_at
        overloaded = (data["kv_cache_usage"] >= .8 or data["engine_waiting"] > max(2, limit)
                      or data.get("recent_error_rate", 0) > .1 or data.get("latency_ratio", 1) > 1.5)
        if overloaded and cooled and new_sample:
            limit = max(1, limit // 2)
            worker.adaptive_changed_at = stamp
        elif cooled and new_sample and demand and data["kv_cache_usage"] < .65 and data["engine_waiting"] == 0 and data.get("gpu_utilization", 0) < .9:
            limit = min(worker.capacity, limit + 1)
            worker.adaptive_changed_at = stamp
        worker.adaptive_limit = limit
        return available_limit(worker, stamp)


@dataclass
class Prediction:
    estimated_seconds: float | None
    target_seconds: float
    at_risk: bool
    calibrated: bool
    source: str
    warm_slots: int
    backlog_requests: int
    reasons: list[str]
    deadline_is_guaranteed: bool = False


class DeadlineEstimator:
    def __init__(self, input_rate=None, output_rate=None, calibrated=False, source="uncalibrated_defaults"):
        c = settings()
        self.input_rate = input_rate or c.estimator_input_tokens_per_second
        self.output_rate = output_rate or c.estimator_output_tokens_per_second
        self.calibrated = calibrated
        self.source = source

    def duration(self, input_tokens, output_tokens):
        return (input_tokens / self.input_rate + output_tokens / self.output_rate) * settings().estimator_uncertainty_margin

    def predict(self, work, backlog, slots, target_seconds, max_parallel=None):
        own = [self.duration(i, o) for i, o in work]
        queued = sum(self.duration(i, o) for i, o in backlog)
        parallel = min(slots, max_parallel or slots)
        seconds = max(max(own, default=0), sum(own) / parallel) + queued / slots if slots > 0 and parallel > 0 else None
        reasons = []
        if not self.calibrated:
            reasons.append("uncalibrated_throughput")
        if not slots:
            reasons.append("no_usable_warm_capacity")
        if seconds is not None and seconds > target_seconds:
            reasons.append("estimated_target_miss")
        return Prediction(seconds, target_seconds, seconds is None or seconds > target_seconds, self.calibrated,
                          self.source, slots, len(backlog), reasons)


class DispatchPolicy:
    @staticmethod
    def score(served, tier, age, slack, duration, ordinal):
        weight = 4 if tier == "standard" or age >= 300 else 1
        # Bounded urgency cannot permanently dominate served counters/aging.
        urgency = 2 * max(0, min(1, 1 - slack / max(duration, 1)))
        return served / weight - min(age / 60, 3) - urgency, slack, ordinal


def context(s, stamp=None):
    stamp = stamp or now()
    c = settings()
    workers = [w for w in s.scalars(select(Worker).where(Worker.heartbeat > stamp - timedelta(seconds=90), Worker.expires_at > stamp))
               if worker_identity(w) == current_identity()]
    attempts = list(s.scalars(select(ExecutionAttempt).where(
        ExecutionAttempt.identity == current_identity(), ExecutionAttempt.outcome == "succeeded",
        ExecutionAttempt.ended_at > stamp - timedelta(hours=24),
        ExecutionAttempt.worker_id.in_([w.id for w in workers])
    ).order_by(ExecutionAttempt.ended_at.desc()).limit(1000)))
    duration = sum(max(0, (a.ended_at - a.started_at).total_seconds()) for a in attempts)
    measured = len(attempts) >= c.estimator_min_samples and duration > 0
    estimator = DeadlineEstimator(
        sum(a.input_tokens for a in attempts) / duration if measured else None,
        sum(a.output_tokens for a in attempts) / duration if measured else None,
        measured and c.estimator_calibrated and c.execution_mode == "vllm",
        ("real_gpu_observations" if c.execution_mode == "vllm" else "mock_observations") if measured else "uncalibrated_defaults",
    )
    rows = list(s.execute(select(Work, Job).join(Job).where(Work.status.in_(ACTIVE))))
    # Old incompatible model artifacts do not consume the current model's queue estimate.
    from packages.common.db import ModelPrice, ModelVersion
    versions = {p.id: v for p, v in s.execute(select(ModelPrice, ModelVersion).join(ModelVersion))}
    rows = [(r, j) for r, j in rows if r.price_id in versions and identity(
        versions[r.price_id].repo, versions[r.price_id].revision,
        versions[r.price_id].tokenizer_revision, versions[r.price_id].execution_mode) == current_identity()]
    return estimator, workers, rows


def admission(s, prepared, seconds):
    est, workers, rows = context(s)
    prediction = est.predict([(n, data["max_output_tokens"]) for data, n, reserve in prepared],
                             [(r.prompt_tokens, r.max_output) for r, j in rows],
                             sum(available_limit(w, now()) for w in workers), seconds, settings().max_inflight)
    return {**asdict(prediction), "outcome": "best_effort", "predicted_at": now().isoformat(),
            "execution_mode": settings().execution_mode,
            "startup_and_model_loading_seconds": settings().gpu_startup_seconds + settings().model_loading_seconds}


class CapacityPlanner:
    @staticmethod
    def recommend(demand_seconds, seconds_left, warm_gpus, tracked_gpus, daily_spend, idle_instances=()):
        c = settings()
        overhead = c.gpu_startup_seconds + c.model_loading_seconds
        usable = max(0, seconds_left - overhead)
        required = math.ceil(demand_seconds / (usable * 16)) if usable else (warm_gpus + 1 if demand_seconds else 0)
        desired = max(warm_gpus, required) if demand_seconds else 0
        requested = max(0, desired - tracked_gpus)
        session_seconds = c.max_gpu_session_minutes * 60
        billable = math.ceil(session_seconds / c.provider_billing_increment_seconds) * c.provider_billing_increment_seconds
        quote = math.ceil(billable * c.planning_hourly_micro_usd / 3600)
        budget_slots = max(0, (c.max_daily_gpu_spend_usd * 1000000 - daily_spend) // quote) if quote else c.max_active_gpus
        allowed = max(0, min(requested, c.max_active_gpus - tracked_gpus, budget_slots))
        blocked = []
        if requested > c.max_active_gpus - tracked_gpus:
            blocked.append("gpu_count_cap")
        if requested > budget_slots:
            blocked.append("daily_spend_cap")
        if demand_seconds and seconds_left <= overhead:
            blocked.append("cold_capacity_arrives_too_late")
            allowed = 0
        return {"mode": "recommendation_only", "provisioning_enabled": c.provisioning_enabled,
                "operator_approval_required": True, "actual_warm_gpus": warm_gpus,
                "tracked_or_warm_gpus": tracked_gpus, "required_gpus_estimate": required,
                "recommended_start_count": allowed, "blocked_by": blocked,
                "estimated_session_cost_micro_usd_per_gpu": quote,
                "recommended_stop_instance_ids": list(idle_instances) if not demand_seconds else [],
                "estimate_calibrated": False}


def capacity_report(s, stamp=None):
    from packages.common.economics import quoted_cost
    stamp = stamp or now()
    est, workers, rows = context(s, stamp)
    demand = sum(est.duration(r.prompt_tokens, r.max_output) for r, j in rows)
    left = min(((j.target - stamp).total_seconds() for r, j in rows), default=settings().default_completion_target_seconds)
    instances = list(s.scalars(select(Instance)))
    live = [i for i in instances if not i.terminated]
    tracked = len(live) + sum(not w.provider_instance_id or w.provider_instance_id not in {i.id for i in live} for w in workers)
    day = stamp.replace(hour=0, minute=0, second=0, microsecond=0)
    spend = sum(quoted_cost(max(0, ((i.terminated_at or stamp) - max(i.created_at, day)).total_seconds()),
                            i.hourly_micro_usd, settings().provider_billing_increment_seconds) for i in instances)
    idle = [i.id for i in live if (stamp - i.last_busy).total_seconds() >= settings().idle_shutdown_seconds
            and not any(r.worker_id == w.id for r, j in rows for w in workers if w.provider_instance_id == i.id)]
    result = CapacityPlanner.recommend(demand, left, len(workers), tracked, spend, idle)
    result["estimate_calibrated"] = est.calibrated
    result["capacity_measurement_mode"] = settings().execution_mode
    result["warm_worker_count"] = len(workers)
    result["actual_warm_gpus"] = sum(w.execution_mode == "vllm" for w in workers)
    result["throughput_source"] = est.source
    result["backlog_slot_seconds"] = demand
    return result
