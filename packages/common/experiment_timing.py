"""First-dispatch decomposition. Missing timestamps are unknown, never zero."""


def components(job, row, first_attempt):
    accepted, received = job.accepted_at, job.received_at
    eligible = max(accepted, row.initial_eligible_at) if accepted and row.initial_eligible_at else None
    points = [received, accepted, eligible, row.eligibility_observed_at,
              row.lease_decision_at, row.first_dispatched_at, first_attempt.started_at if first_attempt else None]
    names = ["admission", "scheduler_not_before", "queue_until_scheduler_observation",
             "scheduler_capacity_and_policy_wait", "lease_assignment", "lease_to_worker_poll"]
    result = {}
    for name, start, end in zip(names, points, points[1:]):
        result[name] = (end-start).total_seconds() if start and end and end >= start else None
    result["worker_poll_receipt_to_execution_start"] = first_attempt.worker_start_delay_seconds if first_attempt else None
    result["worker_engine_call"] = first_attempt.worker_engine_seconds if first_attempt else None
    return result
