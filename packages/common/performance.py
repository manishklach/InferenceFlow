"""Tenant-scoped lifecycle measures and credential-protected operator reports."""
import json
import math
from collections import defaultdict
from typing import Any
from datetime import timedelta
from sqlalchemy import select, or_
from packages.common.db import Job, Work, ExecutionAttempt, Worker, now
from packages.common.scheduling import context, available_limit, capacity_report
from packages.common.economics import economics_report


def percentiles(values):
    values = sorted(values)
    return {f"p{p}": values[max(0, math.ceil(p / 100 * len(values)) - 1)] if values else None for p in (50, 95, 99)}


def performance_report(s, tenant=None, stamp=None):
    stamp = stamp or now()
    groups = defaultdict(list)
    # Include every request of older active jobs so partial terminal rows cannot masquerade as full jobs.
    active_query = select(Job.id).join(Work).where(Work.status.in_({"queued", "leased", "running", "billing_pending"}))
    if tenant:
        active_query = active_query.where(Job.tenant_id == tenant)
    active_job_ids = list(s.scalars(active_query.distinct()))
    query = select(Work, Job).join(Job).where(or_(Job.created_at >= stamp - timedelta(hours=24), Job.id.in_(active_job_ids)))
    if tenant:
        query = query.where(Job.tenant_id == tenant)
    for r, j in s.execute(query):
        groups[j.id].append((r, j))
    completed, attained, under_hour, misses, failed, pending, risk = 0, 0, 0, 0, 0, 0, 0
    latencies, waits, dispatches = [], [], []
    predictions: dict[str, Any] = {"samples": 0, "predicted_risk_actual_miss": 0, "predicted_risk_actual_hit": 0,
                   "predicted_safe_actual_miss": 0, "predicted_safe_actual_hit": 0,
                   "mean_absolute_error_seconds": None}
    errors = []
    est, workers, active = context(s, stamp)
    slots = sum(available_limit(w, stamp) for w in workers)
    for pairs in groups.values():
        j = pairs[0][1]
        rows = [r for r, j in pairs]
        for r in rows:
            if r.first_dispatched_at:
                dispatches.append(max(0, (r.first_dispatched_at - j.created_at).total_seconds()))
            if r.started_at:
                waits.append(max(0, (r.started_at - j.created_at).total_seconds()))
        if all(r.status in {"succeeded", "failed", "canceled", "expired"} for r in rows):
            if all(r.status == "succeeded" for r in rows):
                ended = max(r.completed_at for r in rows)
                latency = max(0, (ended - j.created_at).total_seconds())
                latencies.append(latency)
                completed += 1
                hit = ended <= j.target
                attained += hit
                under_hour += latency <= 3600
                misses += not hit
                if j.admission:
                    p = json.loads(j.admission)
                    if p.get("estimated_seconds") is not None:
                        predictions["samples"] += 1
                        key = "predicted_" + ("risk" if p["at_risk"] else "safe") + "_actual_" + ("hit" if hit else "miss")
                        predictions[key] += 1
                        errors.append(abs(p["estimated_seconds"] - latency))
            else:
                failed += 1
        else:
            pending += 1
            own = [(r.prompt_tokens, r.max_output) for r in rows if r.status not in {"succeeded", "failed", "canceled", "expired"}]
            backlog = [(r.prompt_tokens, r.max_output) for r, job in active if job.id != j.id]
            risk += est.predict(own, backlog, slots, (j.target - stamp).total_seconds()).at_risk
    if errors:
        predictions["mean_absolute_error_seconds"] = sum(errors) / len(errors)
    oldest = min((j.created_at for pairs in groups.values() for r, j in pairs if r.status == "queued"), default=None)
    attempts_q = select(ExecutionAttempt).join(Work, ExecutionAttempt.request_id == Work.id).where(ExecutionAttempt.ended_at >= stamp - timedelta(hours=24))
    if tenant:
        attempts_q = attempts_q.where(Work.tenant_id == tenant)
    attempts = list(s.scalars(attempts_q))
    return {"scope": "tenant" if tenant else "operator", "window": "jobs_accepted_last_24_hours_plus_older_active_jobs",
            "measurement_modes": sorted({a.mode for a in attempts}), "estimator_source": est.source,
            "estimates_calibrated": est.calibrated, "deadline_is_guaranteed": False,
            "queue_backlog_requests": sum(r.status == "queued" for pairs in groups.values() for r, j in pairs),
            "oldest_queued_seconds": (stamp - oldest).total_seconds() if oldest else 0,
            "pending_jobs": pending, "estimated_deadline_risk_jobs": risk,
            "successful_jobs": completed, "successful_within_requested_target": attained,
            "successful_within_60_minutes": under_hour, "successful_deadline_misses": misses,
            "unsuccessful_terminal_jobs": failed,
            "deadline_attainment": attained / completed if completed else None,
            "sub_hour_attainment": under_hour / completed if completed else None,
            "end_to_end_seconds": percentiles(latencies), "queue_wait_seconds": percentiles(waits),
            "submission_to_dispatch_seconds": percentiles(dispatches),
            "worker_execution_seconds": percentiles([(a.ended_at - a.started_at).total_seconds() for a in attempts]),
            "tokens_per_second_wall_clock_24h": sum(a.input_tokens + a.output_tokens for a in attempts) / 86400,
            "prediction_accuracy": predictions,
            "failed_attempts": sum(a.outcome != "succeeded" for a in attempts),
            "retry_attempts": sum(a.epoch > 1 for a in attempts)}


def operations_report(s):
    stamp = now()
    worker_rows = []
    from packages.common.scheduling import telemetry
    for w in s.scalars(select(Worker)):
        data, fresh = telemetry(w, stamp)
        worker_rows.append({"id": w.id, "mode": w.execution_mode, "telemetry_fresh": fresh,
                            "gpu_utilization": data.get("gpu_utilization") if fresh else None,
                            "kv_cache_usage": data.get("kv_cache_usage") if fresh else None,
                            "engine_running": data.get("engine_running") if fresh else None,
                            "engine_waiting": data.get("engine_waiting") if fresh else None,
                            "dispatch_limit": available_limit(w, stamp), "hard_limit": w.capacity})
    return {"performance": performance_report(s, stamp=stamp), "capacity": capacity_report(s, stamp),
            "economics": economics_report(s, stamp), "workers": worker_rows}
