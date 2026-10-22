"""Regression tests for the production readiness audit, using isolated PostgreSQL only."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading
import time
import httpx
import jwt
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, text

from packages.common.config import Settings, settings
from packages.common.db import Session, Work, Wallet, Tenant, Instance, Worker, now
from packages.common.identity import model_identity
from packages.common.payments import handle_event
from packages.common.security import encrypt, decrypt, digest
from packages.common.service import schedule, reconcile, lock_wallet, post, account, submit
from packages.common.schemas import Submit
from packages.common.providers import RunpodProvider, GpuSpec, watchdog
from tests.test_platform import body, register, drain


def dispatch(client, wh):
    with Session.begin() as s:
        schedule(s)
    return client.post("/internal/workers/poll", headers=wh).json()["items"]


def test_production_rejects_default_worker_enrollment():
    cfg = Settings(
        _env_file=None,
        environment="production",
        secret_key="x" * 64,
        oidc_issuer="issuer",
        oidc_audience="audience",
        oidc_jwks_url="https://issuer/keys",
    )
    with pytest.raises(ValueError, match="WORKER_BOOTSTRAP_TOKEN"):
        cfg.validate_runtime()


def test_restart_fences_abandoned_work_and_old_credentials(client, headers):
    client.post("/v1/jobs", headers=headers, json=body())
    old = register(client)
    item = dispatch(client, old)[0]
    new = register(client)
    assert client.post("/internal/workers/poll", headers=old).status_code == 401
    assert (
        client.post(
            "/internal/workers/heartbeat", headers=new, json={"active": [{"id": item["id"], "epoch": item["epoch"]}]}
        ).status_code
        == 200
    )
    with Session.begin() as s:
        schedule(s)
        request = s.get(Work, item["id"])
        assert request.status == "queued"
        request.eligible_at = now()
    items = dispatch(client, new)
    assert len(items) == 1 and items[0]["epoch"] > item["epoch"]
    assert (
        client.post(
            "/internal/workers/requests/" + item["id"] + "/finalize",
            headers=new,
            json={"epoch": item["epoch"], "output_text": "stale"},
        ).status_code
        == 409
    )


def test_heartbeat_renews_only_active_epochs(client, headers):
    client.post("/v1/jobs", headers=headers, json=body(2))
    wh = register(client)
    items = dispatch(client, wh)
    with Session.begin() as s:
        for item in items:
            s.get(Work, item["id"]).lease_until = now() + timedelta(seconds=2)
    client.post(
        "/internal/workers/heartbeat", headers=wh, json={"active": [{"id": items[0]["id"], "epoch": items[0]["epoch"]}]}
    )
    with Session.begin() as s:
        assert s.get(Work, items[0]["id"]).lease_until > now() + timedelta(seconds=30)
        assert s.get(Work, items[1]["id"]).lease_until < now() + timedelta(seconds=5)


@pytest.mark.parametrize(
    "field,value",
    [("revision", "other"), ("execution_mode", "vllm"), ("repo", "other/repo"), ("tokenizer_revision", "other")],
)
def test_dispatch_requires_all_identity_fields(client, headers, field, value):
    client.post("/v1/jobs", headers=headers, json=body())
    wh = register(client)
    with Session.begin() as s:
        setattr(s.get(Worker, "worker"), field, value)
    assert dispatch(client, wh) == []


def test_revision_upgrade_keeps_queued_job_on_matching_worker(client, headers, monkeypatch):
    client.post("/v1/jobs", headers=headers, json=body())
    wh = register(client)
    monkeypatch.setattr(settings(), "model_revision", "b" * 40)
    # Existing worker identity stays fixed even if the control-plane configuration changes.
    item = dispatch(client, wh)[0]
    assert item["identity"]["revision"] == "mock-v1"


def paid_event(tid):
    return {
        "id": "evt-paid",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs-test",
                "payment_status": "paid",
                "currency": "usd",
                "amount_total": 1000,
                "client_reference_id": tid,
                "payment_intent": "pi-test",
            }
        },
    }


def refund_event():
    return {
        "id": "evt-refund",
        "type": "charge.refunded",
        "data": {"object": {"payment_intent": "pi-test", "amount_refunded": 1000}},
    }


@pytest.mark.parametrize("running", [False, True])
def test_refund_cancels_work_and_fences_late_results(client, headers, tenant, running):
    with Session.begin() as s:
        w = lock_wallet(s, tenant[0])
        post(s, w, "remove-seed", "adjustment", -w.available, 0)
        handle_event(s, paid_event(tenant[0]))
    client.post("/v1/jobs", headers=headers, json=body())
    wh = register(client)
    items = dispatch(client, wh) if running else []
    with Session.begin() as s:
        handle_event(s, refund_event())
    assert dispatch(client, wh) == []
    if items:
        assert (
            client.post(
                "/internal/workers/requests/" + items[0]["id"] + "/finalize",
                headers=wh,
                json={"epoch": items[0]["epoch"], "output_text": "late"},
            ).status_code
            == 409
        )
    with Session.begin() as s:
        assert s.get(Tenant, tenant[0]).frozen
        w = s.get(Wallet, tenant[0])
        assert (w.available, w.reserved, w.debt) == (0, 0, 0)
        assert s.scalar(select(Work)).captured == 0
        assert reconcile(s) == []


def test_refund_liability_is_journaled_and_future_credit_repays_it(client, headers, tenant):
    with Session.begin() as s:
        w = lock_wallet(s, tenant[0])
        post(s, w, "remove-seed", "adjustment", -w.available, 0)
        handle_event(s, paid_event(tenant[0]))
    client.post("/v1/jobs", headers=headers, json=body())
    drain(client, register(client))
    with Session.begin() as s:
        charge = s.scalar(select(Work)).captured
        assert charge > 0
        handle_event(s, refund_event())
        w = s.get(Wallet, tenant[0])
        assert w.debt == charge and w.available == 0
        post(s, w, "repayment", "topup", charge + 7, 0)
        assert (w.debt, w.available) == (0, 7)
        assert reconcile(s) == []


def test_refund_racing_finalization_preserves_funding(client, headers, tenant):
    from packages.common.service import finalize, Problem
    from packages.common.schemas import Completion
    from apps.worker.engines import MockInferenceEngine

    with Session.begin() as s:
        w = lock_wallet(s, tenant[0])
        post(s, w, "remove-seed", "adjustment", -w.available, 0)
        handle_event(s, paid_event(tenant[0]))
    client.post("/v1/jobs", headers=headers, json=body())
    item = dispatch(client, register(client))[0]
    output = asyncio.run(MockInferenceEngine().execute(item))
    barrier = threading.Barrier(2)

    def finish():
        barrier.wait()
        try:
            with Session.begin() as s:
                finalize(s, "worker", item["id"], Completion(epoch=item["epoch"], **output))
        except Problem as exc:
            assert exc.status == 409

    def refund():
        barrier.wait()
        with Session.begin() as s:
            handle_event(s, refund_event())

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(finish), pool.submit(refund)]
        for future in futures:
            future.result(timeout=10)
    with Session.begin() as s:
        w = s.get(Wallet, tenant[0])
        assert w.available == w.reserved == 0
        assert w.debt == s.get(Work, item["id"]).captured
        assert reconcile(s) == []


def test_creation_watchdog_matches_pending_intent(monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, "provisioning_enabled", True)
    monkeypatch.setattr(cfg, "runpod_api_key", "fake-audit-key")
    provider = RunpodProvider()
    inventory, deleted = [], []

    def fake_call(method, path, **kwargs):
        if method == "GET" and path == "/pods":
            return {"pods": list(inventory)}
        if method == "POST":
            pod = {"id": "audit-pod", "name": kwargs["json"]["name"]}
            inventory.append(pod)
            watchdog(provider)
            return pod
        if method == "DELETE":
            deleted.append(path)
            return {}
        raise AssertionError((method, path))

    monkeypatch.setattr(provider, "call", fake_call)
    assert provider.create_instance(GpuSpec("gpu", "region", "image", 1000000), "audit")["id"] == "audit-pod"
    assert not deleted
    with Session.begin() as s:
        assert not s.get(Instance, "audit-pod").terminated
    inventory.clear()
    watchdog(provider)
    with Session.begin() as s:
        assert s.get(Instance, "audit-pod").terminated


def test_busy_tenant_does_not_block_other_tenant(client, tenant):
    with Session.begin() as s:
        other = account(s, "other-tenant")
        post(s, lock_wallet(s, other.id), "other-fund", "topup", 10000, 0)
        submit(s, tenant[0], Submit(**body()), "first")
        job = submit(s, other.id, Submit(**body()), "second")
    register(client)
    with Session.begin() as locked:
        lock_wallet(locked, tenant[0])

        def run():
            with Session.begin() as s:
                s.execute(text("SET LOCAL statement_timeout = '1500ms'"))
                schedule(s)

        with ThreadPoolExecutor(1) as pool:
            pool.submit(run).result(timeout=4)
        with Session.begin() as s:
            assert s.scalar(select(Work).where(Work.job_id == job.id)).status == "leased"


def test_callback_io_holds_no_transaction_and_does_not_block_tick(client, headers, tenant, monkeypatch):
    from packages.common import webhooks
    from apps.scheduler.main import tick
    from packages.common.db import Delivery

    with Session.begin() as s:
        t = s.get(Tenant, tenant[0])
        t.webhook_url, t.webhook_ips, t.webhook_secret = "https://example.com", '["8.8.8.8"]', encrypt("test")
    jid = client.post("/v1/jobs", headers=headers, json=body()).json()["id"]
    client.post("/v1/jobs/" + jid + "/cancel", headers=headers)
    with Session.begin() as s:
        webhooks.enqueue(s)
    entered, release = threading.Event(), threading.Event()

    def slow_send(*args):
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(webhooks, "send", slow_send)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(webhooks.deliver)
        try:
            assert entered.wait(3)
            started = time.monotonic()
            tick()
            assert time.monotonic() - started < 1.5
            with Session.begin() as s:
                s.execute(text("SET LOCAL lock_timeout = '500ms'"))
                assert s.scalar(select(Delivery).with_for_update()) is not None
        finally:
            release.set()
        future.result(timeout=5)


def test_session_and_api_key_share_persistent_limit(client, tenant, monkeypatch):
    # Fixed clock avoids a test crossing a minute boundary.
    monkeypatch.setattr("apps.api.main.rate_window", lambda session: 30000000)
    raw = jwt.encode(
        {"sub": tenant[0], "aud": "dashboard", "csrf": "test", "exp": 1900000000},
        settings().secret_key,
        algorithm="HS256",
    )
    client.cookies.set("if_session", raw)
    assert all(client.get("/v1/wallet").status_code == 200 for _ in range(60))
    client.cookies.clear()
    key = {"Authorization": "Bearer " + tenant[1]}
    assert all(client.get("/v1/wallet", headers=key).status_code == 200 for _ in range(60))
    assert client.get("/v1/wallet", headers=key).status_code == 429
    client.cookies.set("if_session", raw)
    assert client.get("/v1/wallet").status_code == 429


def test_metrics_requires_separate_credential(client, headers, monkeypatch):
    monkeypatch.setattr(settings(), "metrics_token", "m" * 40)
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers=headers).status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer " + "m" * 40}).status_code == 200


def test_encryption_and_credential_keys_rotate_independently(client, tenant, monkeypatch):
    cfg = settings()
    legacy = encrypt({"prompt": "retain"})
    old_digest = digest(tenant[1])
    old_secret = cfg.secret_key
    monkeypatch.setattr(cfg, "encryption_legacy_secret", old_secret)
    key_a, key_b = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setattr(cfg, "encryption_keys", {"a": key_a, "b": key_b})
    monkeypatch.setattr(cfg, "encryption_active_key", "a")
    encrypted = encrypt({"result": "retain"})
    monkeypatch.setattr(cfg, "secret_key", "new-session-signing-key" * 3)
    monkeypatch.setattr(cfg, "credential_hash_key", "new-independent-hash-key" * 3)
    monkeypatch.setattr(cfg, "credential_hash_previous_keys", [old_secret])
    monkeypatch.setattr(cfg, "encryption_active_key", "b")
    assert decrypt(legacy) == {"prompt": "retain"} and decrypt(encrypted) == {"result": "retain"}
    migrated = encrypt(decrypt(legacy))
    assert migrated.startswith("v1:b:") and decrypt(migrated) == {"prompt": "retain"}
    assert client.get("/v1/wallet", headers={"Authorization": "Bearer " + tenant[1]}).status_code == 200
    from packages.common.db import Key

    with Session.begin() as s:
        assert s.scalar(select(Key)).digest != old_digest
        assert s.scalar(select(Key)).digest == digest(tenant[1])


def test_wrong_served_model_fails_readiness():
    from apps.worker.engines import VllmInferenceEngine

    async def run():
        engine = VllmInferenceEngine()
        await engine.client.aclose()
        engine.client = httpx.AsyncClient(
            base_url="http://engine",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": [{"id": "wrong-model"}]})),
        )
        with pytest.raises(RuntimeError, match="identity"):
            await engine.ready()
        await engine.client.aclose()

    asyncio.run(run())


def test_worker_stops_on_failed_canary(monkeypatch):
    from apps.worker import main as worker

    async def failed(self):
        return False

    monkeypatch.setattr(worker.MockInferenceEngine, "ready", failed)
    with pytest.raises(RuntimeError, match="canary"):
        asyncio.run(worker.main())


def test_worker_retries_finalization_beyond_three_attempts(monkeypatch):
    from apps.worker import main as worker

    real_client, real_sleep = httpx.AsyncClient, asyncio.sleep
    completed = False
    polls, attempts = 0, 0

    async def sleep(_):
        await real_sleep(0)

    def handler(request):
        nonlocal completed, polls, attempts
        if request.url.path.endswith("/register"):
            return httpx.Response(200, json={"worker_token": "test"})
        if request.url.path.endswith("/heartbeat"):
            return httpx.Response(200, json={"cancel_requested": []})
        if request.url.path.endswith("/finalize"):
            attempts += 1
            completed = attempts == 5
            return httpx.Response(200 if completed else 503, json={})
        if request.url.path.endswith("/poll"):
            if completed:
                raise RuntimeError("test-complete")
            polls += 1
            items = (
                [
                    {
                        "id": "r",
                        "epoch": 1,
                        "prompt_tokens": 18,
                        "identity": model_identity(),
                        "payload": body()["requests"][0],
                    }
                ]
                if polls == 1
                else []
            )
            return httpx.Response(200, json={"items": items})
        raise AssertionError(request.url)

    monkeypatch.setattr(
        worker.httpx, "AsyncClient", lambda **kw: real_client(**kw, transport=httpx.MockTransport(handler))
    )
    monkeypatch.setattr(worker.asyncio, "sleep", sleep)
    with pytest.raises(RuntimeError, match="test-complete"):
        asyncio.run(asyncio.wait_for(worker.main(), timeout=3))
    assert attempts == 5


def test_watchdog_counts_terminated_session_spend(monkeypatch):
    from packages.common.providers import FakeProvider
    from packages.common import providers

    provider = FakeProvider()
    pod = provider.create_instance(GpuSpec("gpu", "region", "image", 1000000), "active")
    fixed_now = now().replace(hour=12, minute=0, second=0)
    with Session.begin() as s:
        s.add(
            Instance(
                id="old",
                source="old",
                hourly_micro_usd=30000000,
                created_at=fixed_now - timedelta(hours=2),
                terminated=True,
                terminated_at=fixed_now - timedelta(hours=1),
            )
        )
        s.add(Instance(id=pod["id"], source="active", hourly_micro_usd=1000000))
    monkeypatch.setattr(providers, "now", lambda: fixed_now)
    watchdog(provider)
    assert provider.list_instances() == []
