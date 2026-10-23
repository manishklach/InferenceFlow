import json
from datetime import timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy import select
from packages.common.config import settings
from packages.common.db import Session, Job, Work, Wallet, Worker, ExecutionAttempt, Instance, now
from packages.common.scheduling import DeadlineEstimator, DispatchPolicy, CapacityPlanner, AdaptiveDispatch, available_limit, capacity_report
from packages.common.economics import quoted_cost, unit_economics, record_invoice, economics_report
from packages.common.performance import performance_report
from packages.common.service import schedule, reconcile
from packages.common.providers import RunpodProvider, GpuSpec, NotConfigured
from tests.test_platform import body, register, drain


@pytest.fixture
def v2(monkeypatch):
    monkeypatch.setattr(settings(), "scheduler_v2_enabled", True)
    return settings()


def node(stamp=None, **overrides):
    values = dict(capacity=16, adaptive_limit=8, adaptive_changed_at=None, telemetry_at=stamp or now(),
                  telemetry=json.dumps({"kv_cache_usage": .3, "engine_running": 4, "engine_waiting": 0, "gpu_utilization": .4}))
    return SimpleNamespace(**{**values, **overrides})


def test_estimator_backlog_parallelism_margin_and_boundary():
    est = DeadlineEstimator(100, 20)
    p = est.predict([(100, 20)] * 4, [(100, 20)] * 4, 2, 12)
    assert p.estimated_seconds == 12 and not p.at_risk and not p.calibrated
    assert est.predict([(100, 20)] * 4, [], 2, 5.99).at_risk
    assert est.predict([(100, 20)], [], 0, 3600).estimated_seconds is None
    assert est.predict([(100, 20)] * 4, [], 4, 7, max_parallel=1).at_risk


def test_admission_explicit_and_strict_atomic(client, headers, tenant, v2):
    rejected = client.post("/v1/jobs", headers=headers, json=body(admission_policy="reject_if_at_risk"))
    assert rejected.status_code == 503 and rejected.json()["error"]["code"] == "deadline_not_feasible"
    with Session.begin() as s:
        assert s.get(Wallet, tenant[0]).reserved == 0
        assert not list(s.scalars(select(Job)))
    accepted = client.post("/v1/jobs", headers=headers, json=body())
    assert accepted.status_code == 202
    j = accepted.json()
    assert j["admission"]["outcome"] == "best_effort"
    assert "no_usable_warm_capacity" in j["admission"]["reasons"]
    assert j["admission"]["target_seconds"] == 3600
    assert not j["deadline_is_guaranteed"]
    wh = register(client)
    again = client.post("/v1/jobs", headers=headers, json=body()).json()
    assert again["admission"] == j["admission"]  # Accepted prediction is immutable across idempotent retries.
    drain(client, wh)
    with Session.begin() as s:
        assert reconcile(s) == []
        assert len(list(s.scalars(select(ExecutionAttempt)))) == 1


def test_legacy_default_and_strict_feature_flag(client, headers):
    r = client.post("/v1/jobs", headers=headers, json=body(admission_policy="reject_if_at_risk"))
    assert r.status_code == 503
    j = client.post("/v1/jobs", headers=headers, json=body()).json()
    assert j["admission"]["source"] == "legacy_scheduler"


def test_priority_weight_aging_and_bounded_urgency():
    score = DispatchPolicy.score
    assert score(8, "standard", 10, 100, 20, 0) < score(8, "economy", 10, 100, 20, 0)
    assert score(0, "economy", 600, 100, 20, 0) < score(0, "standard", 0, -100, 20, 0)
    # Even an arbitrarily late job cannot permanently exclude a less-served tenant.
    assert score(100, "standard", 60, -1000000, 20, 0) > score(0, "economy", 60, 100, 20, 0)
    assert score(0, "standard", 0, 1, 20, 0) < score(0, "standard", 0, 100, 20, 0)


def test_adaptive_limits_hysteresis_and_overload(monkeypatch):
    monkeypatch.setattr(settings(), "adaptive_dispatch_enabled", True)
    t = now()
    w = node(t)
    assert AdaptiveDispatch.update(w, t, True) == 9
    assert AdaptiveDispatch.update(w, t + timedelta(seconds=1), True) == 9
    w.telemetry_at = t + timedelta(seconds=31)
    w.telemetry = json.dumps({"kv_cache_usage": .85, "engine_running": 9, "engine_waiting": 5})
    assert AdaptiveDispatch.update(w, w.telemetry_at, True) == 4
    w.capacity = 2
    assert available_limit(w, w.telemetry_at) <= 2
    w.telemetry = json.dumps({"kv_cache_usage": .95})
    assert available_limit(w, t) == 0


@pytest.mark.parametrize("payload", [None, "{}", "broken", "[]", '{"kv_cache_usage": -1}', '{"kv_cache_usage": 2}', '{"engine_running": "bad"}'])
def test_missing_inconsistent_telemetry_safe(monkeypatch, payload):
    monkeypatch.setattr(settings(), "adaptive_dispatch_enabled", True)
    w = node(telemetry=payload)
    assert AdaptiveDispatch.update(w, now(), True) <= settings().adaptive_initial_slots


def test_stale_and_future_telemetry_safe(monkeypatch):
    monkeypatch.setattr(settings(), "adaptive_dispatch_enabled", True)
    for offset in (-120, 120):
        w = node(now() + timedelta(seconds=offset))
        assert AdaptiveDispatch.update(w, now(), True) == 2


def test_capacity_limits_cold_start_and_no_spending(monkeypatch):
    monkeypatch.setattr(settings(), "max_active_gpus", 2)
    p = CapacityPlanner.recommend(200000, 3600, 1, 1, 0)
    assert p["recommended_start_count"] == 1 and "gpu_count_cap" in p["blocked_by"]
    assert p["mode"] == "recommendation_only" and p["operator_approval_required"]
    assert CapacityPlanner.recommend(200000, 60, 0, 0, 0)["recommended_start_count"] == 0
    assert CapacityPlanner.recommend(200000, 3600, 1, 1, 25000000)["recommended_start_count"] == 0
    assert CapacityPlanner.recommend(0, 3600, 1, 1, 0, ["idle"])["recommended_stop_instance_ids"] == ["idle"]
    # Recommendation code cannot reach the provider, even if its external-call method is poisoned.
    monkeypatch.setattr(RunpodProvider, "call", lambda *a, **kw: pytest.fail("provider called"))
    with Session.begin() as s:
        assert capacity_report(s)["mode"] == "recommendation_only"
    with pytest.raises(NotConfigured):
        RunpodProvider().create_instance(GpuSpec("test", "test", "test", 1000000), "not-approved")


def test_economics_integer_rounding_zero_and_invoice(tenant):
    assert quoted_cost(1, 3600000, 60) == 60000
    assert quoted_cost(3600, 1000000, 60) == 1000000
    e = unit_economics(1000000, 1000000, 1000000, 2000000)
    assert e["gross_margin"] == .5 and e["cost_per_million_total_tokens_micro_usd"] == 500000
    assert unit_economics(5, 0, 0, 0)["gross_margin"] is None
    with pytest.raises(ValueError):
        quoted_cost(-1, 1)
    stamp = now()
    with Session.begin() as s:
        s.add(Instance(id="i", source="manual", hourly_micro_usd=1000000, created_at=stamp - timedelta(hours=1)))
        s.flush()
        before = s.get(Wallet, tenant[0]).available
        record_invoice(s, "i", "manual", "approved-test", 60, 1200000, "bill-1", stamp)
        report = economics_report(s, stamp)
        assert report["estimated_cost_micro_usd"] == 1000000
        assert report["provider_invoiced_micro_usd"] == 1200000
        assert report["instances"][0]["unobserved_seconds"] == 3600
        assert s.get(Wallet, tenant[0]).available == before
        with pytest.raises(ValueError, match="conflict"):
            record_invoice(s, "i", "manual", "approved-test", 60, 1200001, "bill-1", stamp)


def test_performance_tenant_isolation_failed_not_success(client, headers, tenant, v2, monkeypatch):
    wh = register(client)
    client.post("/v1/jobs", headers=headers, json=body())
    drain(client, wh)
    r = client.post("/v1/jobs", headers={**headers, "Idempotency-Key": "cancel"}, json=body()).json()
    client.post("/v1/jobs/" + r["id"] + "/cancel", headers=headers)
    perf = client.get("/v1/performance", headers=headers).json()
    assert perf["successful_jobs"] == 1 and perf["unsuccessful_terminal_jobs"] == 1
    assert perf["successful_within_60_minutes"] == 1
    assert perf["prediction_accuracy"]["samples"] == 1
    with Session.begin() as s:
        from packages.common.service import account
        other = account(s, "other")
        assert performance_report(s, other.id)["successful_jobs"] == 0
    assert client.get("/internal/scheduling/report", headers=headers).status_code == 401
    monkeypatch.setattr(settings(), "metrics_token", "operator-test-token")
    ops = client.get("/internal/scheduling/report", headers={"Authorization": "Bearer operator-test-token"})
    assert ops.status_code == 200 and ops.json()["capacity"]["mode"] == "recommendation_only"


def test_worker_outage_deadline_risk_and_restart(client, headers, v2):
    wh = register(client)
    jid = client.post("/v1/jobs", headers=headers, json=body()).json()["id"]
    with Session.begin() as s:
        schedule(s)
    item = client.post("/internal/workers/poll", headers=wh).json()["items"][0]
    with Session.begin() as s:
        r = s.get(Work, item["id"])
        r.lease_until = now() - timedelta(seconds=1)
        w = s.get(Worker, "worker")
        w.heartbeat = now() - timedelta(seconds=120)
        schedule(s)
    p = client.get("/v1/performance", headers=headers).json()
    assert p["estimated_deadline_risk_jobs"] == 1
    wh = register(client)
    with Session.begin() as s:
        s.get(Work, item["id"]).eligible_at = now() - timedelta(seconds=1)
    drain(client, wh)
    assert client.get("/v1/jobs/" + jid, headers=headers).json()["status"] == "succeeded"
    with Session.begin() as s:
        assert reconcile(s) == []
        attempts = list(s.scalars(select(ExecutionAttempt).order_by(ExecutionAttempt.epoch)))
        assert [a.outcome for a in attempts] == ["lease_lost", "succeeded"]


def test_offline_simulation_deterministic_and_outage(monkeypatch):
    from scripts.benchmark_scheduler import simulate
    monkeypatch.setattr(settings(), "adaptive_dispatch_enabled", True)
    a = simulate(42, "outage", "adaptive", 100)
    assert a == simulate(42, "outage", "adaptive", 100)
    assert a["failed_attempts"] > 0 and a["retried_executions"] > 0
    assert 0 <= a["gpu_utilization_slot_proxy"] <= 1
    assert a["successful"] + a["failed"] + a["expired"] == 100


def test_v2_concurrent_submissions_accounting_and_legacy_fingerprint(tenant, v2):
    from concurrent.futures import ThreadPoolExecutor
    from packages.common.service import submit
    from packages.common.schemas import Submit
    import hashlib
    request = Submit(**body())

    def accept(i):
        with Session.begin() as s:
            return submit(s, tenant[0], request, f"v2-{i}").id

    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = list(pool.map(accept, range(32)))
    assert len(set(jobs)) == 32
    canonical = request.model_dump(exclude={"admission_policy"})
    legacy_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with Session.begin() as s:
        assert s.get(Job, jobs[0]).body_hash == legacy_hash
        assert reconcile(s) == []
        assert s.get(Wallet, tenant[0]).available >= 0


def test_expiration_exact_boundary_releases_and_v2_fairness(client, headers, tenant, v2, monkeypatch):
    from packages.common.service import account, post, lock_wallet, submit
    from packages.common.schemas import Submit
    register(client)
    with Session.begin() as s:
        old = submit(s, tenant[0], Submit(**body(40, tier="economy")), "old")
        old.created_at = now() - timedelta(minutes=10)
        other = account(s, "small-tenant")
        post(s, lock_wallet(s, other.id), "small-seed", "topup", 1000000, 0)
        small = submit(s, other.id, Submit(**body()), "small")
        s.get(Worker, "worker").capacity = 16
        schedule(s)
        # Aging promotes old economy work, while bounded served counters still admit the small tenant.
        assert any(r.status == "leased" for r in s.scalars(select(Work).where(Work.job_id == old.id)))
        assert any(r.status == "leased" for r in s.scalars(select(Work).where(Work.job_id == small.id)))
    stamp = now()
    monkeypatch.setattr("packages.common.service.now", lambda: stamp)
    with Session.begin() as s:
        for job in s.scalars(select(Job)):
            job.target = stamp
        schedule(s)
        assert all(r.status == "expired" for r in s.scalars(select(Work)))
        assert reconcile(s) == [] and s.get(Wallet, tenant[0]).reserved == 0


def test_vllm_telemetry_records_success_errors_and_latency(monkeypatch):
    import asyncio
    from apps.worker.engines import VllmInferenceEngine
    engine = VllmInferenceEngine()

    async def success(item):
        return {"input_tokens": 100, "output_tokens": 20}

    async def failure(item):
        raise RuntimeError("synthetic")

    async def run():
        monkeypatch.setattr(engine, "_execute", success)
        await engine.execute({})
        monkeypatch.setattr(engine, "_execute", failure)
        with pytest.raises(RuntimeError):
            await engine.execute({})
        await engine.client.aclose()

    asyncio.run(run())
    assert len(engine.samples) == 2
    assert engine.samples[0][3:] == (100, 20) and engine.samples[1][2] == 1


def test_attachment_startup_metadata_survives_invoice():
    from packages.common.economics import record_attachment
    stamp = now()
    with Session.begin() as s:
        record_attachment(s, "manual-1", "approved", "nvidia-test", 3600000,
                          stamp - timedelta(seconds=61), 60, 30)
        record_invoice(s, "manual-1", "approved", "nvidia-test", 60, 125000, "invoice", stamp)
        r = economics_report(s, stamp)["instances"][0]
        assert r["startup_seconds"] == 30 and r["estimated_cost_micro_usd"] == 120000
        assert r["provider_invoiced_micro_usd"] == 125000
        with pytest.raises(ValueError, match="already tracked"):
            record_attachment(s, "manual-1", "approved", "nvidia-test", 1, stamp)
