"""Database-backed billing/recovery gates for fixed and adaptive dispatch."""
from datetime import timedelta
import asyncio
import pytest
from sqlalchemy import select, func
from packages.common.config import settings
from packages.common.db import Session, Work, Worker, Usage, Ledger, now
from packages.common.service import schedule
from apps.worker.engines import MockInferenceEngine
from scripts.audit_gpu_run import audit_run
from tests.test_platform import body, drain


@pytest.mark.parametrize("adaptive", [False, True])
def test_interruption_recovery_and_read_only_billing_audit(client, headers, monkeypatch, adaptive):
    monkeypatch.setattr(settings(), "scheduler_v2_enabled", adaptive)
    monkeypatch.setattr(settings(), "adaptive_dispatch_enabled", adaptive)
    job = client.post("/v1/jobs", headers=headers, json=body(4, deadline_seconds=3600)).json()
    def enroll():
        response = client.post("/internal/workers/register", json={"id": "worker", "capacity": 4},
                               headers={"Authorization": "Bearer local-worker-only"})
        assert response.status_code == 200
        return {"Authorization": "Bearer " + response.json()["worker_token"]}
    credential = enroll()
    with Session.begin() as session:
        schedule(session)
    abandoned = client.post("/internal/workers/poll", headers=credential).json()["items"]
    assert abandoned
    old = abandoned[0]
    output = asyncio.run(MockInferenceEngine().execute(old))
    # Simulate interruption after physical execution and before finalization.
    with Session.begin() as session:
        for row in session.scalars(select(Work).where(Work.job_id == job["id"])):
            if row.status in {"leased", "running"}:
                row.lease_until = now() - timedelta(seconds=1)
        session.get(Worker, "worker").heartbeat = now() - timedelta(seconds=120)
        schedule(session)
    credential = enroll()
    with Session.begin() as session:
        for row in session.scalars(select(Work).where(Work.job_id == job["id"])):
            row.eligible_at = now() - timedelta(seconds=1)
    stale = client.post("/internal/workers/requests/" + old["id"] + "/finalize", headers=credential,
                        json={"epoch": old["epoch"], **output})
    assert stale.status_code == 409
    drain(client, credential)
    with Session.begin() as session:
        report = audit_run(session, [job["id"]], require_vllm=False)
        assert report["passed"], report
        assert report["unique_usage_records"] == report["unique_capture_sources"] == 4
        assert report["retried_attempts"] > 0
        assert session.scalar(select(func.count()).select_from(Usage)) == 4
        assert session.scalar(select(func.count()).select_from(Ledger).where(Ledger.kind == "capture")) == 4
        assert report["all_accepted_requests_successful_within_60_minutes"] == 1


def test_capacity_planner_respects_four_sequence_worker(monkeypatch):
    from packages.common.scheduling import CapacityPlanner
    monkeypatch.setattr(settings(), "worker_capacity", 4)
    # 100 usable seconds at four slots means 800 slot-seconds need two GPUs.
    monkeypatch.setattr(settings(), "gpu_startup_seconds", 0)
    monkeypatch.setattr(settings(), "model_loading_seconds", 0)
    assert CapacityPlanner.recommend(800, 100, 0, 0, 0)["required_gpus_estimate"] == 2
