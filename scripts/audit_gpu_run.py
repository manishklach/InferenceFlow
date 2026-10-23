"""Read-only per-request timing/billing audit on the trusted CPU control plane."""
import argparse
import json
from collections import Counter
from pathlib import Path
from sqlalchemy import select, text
from packages.common.db import Session, Job, Work, Usage, Ledger, ExecutionAttempt
from packages.common.service import reconcile
from packages.common.performance import percentiles


def audit_run(session, job_ids, require_vllm=True):
    if not job_ids or len(job_ids) != len(set(job_ids)):
        raise ValueError("Unique accepted job IDs required")
    jobs = list(session.scalars(select(Job).where(Job.id.in_(job_ids))))
    if len(jobs) != len(job_ids) or len({j.tenant_id for j in jobs}) != 1:
        raise ValueError("All jobs must exist and belong to one isolated experiment tenant")
    lookup = {j.id: j for j in jobs}
    rows = list(session.scalars(select(Work).where(Work.job_id.in_(job_ids))))
    ids = [r.id for r in rows]
    usage = {u.request_id: u for u in session.scalars(select(Usage).where(Usage.request_id.in_(ids)))}
    captures = {entry.source: entry for entry in session.scalars(select(Ledger).where(
        Ledger.tenant_id == jobs[0].tenant_id, Ledger.source.in_([rid + ":capture" for rid in ids])))}
    attempts = list(session.scalars(select(ExecutionAttempt).where(ExecutionAttempt.request_id.in_(ids))))
    errors, latencies, waits = [], [], []
    within = 0
    for row in rows:
        if row.status not in {"succeeded", "failed", "canceled", "expired"}:
            errors.append({"request_id": row.id, "reason": "not_terminal"})
        if row.reservation != row.captured + row.released:
            errors.append({"request_id": row.id, "reason": "outstanding_or_inconsistent_reservation"})
        capture = captures.get(row.id + ":capture")
        if capture is None or capture.kind != "capture" or capture.reserved_delta != -row.captured or capture.available_delta != 0:
            errors.append({"request_id": row.id, "reason": "capture_ledger_mismatch"})
        record = usage.get(row.id)
        if row.status == "succeeded":
            if (record is None or record.charge != row.captured or record.input_tokens != row.input_tokens
                    or record.output_tokens != row.output_tokens):
                errors.append({"request_id": row.id, "reason": "usage_charge_mismatch"})
            if row.completed_at:
                elapsed = (row.completed_at - lookup[row.job_id].created_at).total_seconds()
                latencies.append(elapsed)
                within += elapsed <= 3600
        if row.first_dispatched_at:
            waits.append((row.first_dispatched_at - lookup[row.job_id].created_at).total_seconds())
    modes = sorted({a.mode for a in attempts})
    if require_vllm and modes != ["vllm"]:
        errors.append({"reason": "non_real_or_missing_attempts"})
    drift = reconcile(session)
    if drift:
        errors.append({"reason": "wallet_reconciliation_drift", "count": len(drift)})
    completion_seconds = None
    if rows and all(row.completed_at is not None for row in rows):
        completion_seconds = (max(row.completed_at for row in rows) - min(job.created_at for job in jobs)).total_seconds()
    return {"scope": "selected_single_tenant_jobs", "read_only": True,
            "job_ids": job_ids, "accepted_requests": len(rows), "measurement_modes": modes,
            "statuses": dict(Counter(r.status for r in rows)), "errors": errors, "passed": not errors,
            "request_e2e_seconds_successful_only": percentiles(latencies),
            "accepted_to_last_terminal_seconds": completion_seconds,
            "submission_to_first_dispatch_seconds": percentiles(waits),
            "all_accepted_requests_successful_within_60_minutes": within / len(rows) if rows else None,
            "attempt_outcomes": dict(Counter(a.outcome or "pending" for a in attempts)),
            "retried_attempts": sum(a.epoch > 1 for a in attempts),
            "unique_usage_records": len(usage), "unique_capture_sources": len(captures),
            "captured_micro_usd": sum(r.captured for r in rows),
            "input_tokens": sum(r.input_tokens for r in rows), "output_tokens": sum(r.output_tokens for r in rows),
            "execution_semantics": "Inference may repeat; accepted customer usage/capture must not duplicate."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    jobs = json.loads((Path(args.run_directory) / "jobs.json").read_text(encoding="utf-8"))
    with Session.begin() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        report = audit_run(session, [job["id"] for job in jobs])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    if not report["passed"]:
        raise SystemExit("Audit failed; inspect saved evidence before any further load")
    print("Read-only timing/billing audit passed")


if __name__ == "__main__":
    main()
