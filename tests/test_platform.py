import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from sqlalchemy import select, text, func
from packages.common.db import Session, Work, Wallet, Job, Usage, Ledger, now
from packages.common.service import (
    account,
    new_key,
    lock_wallet,
    post,
    submit,
    schedule,
    finalize,
    reconcile,
    Problem,
    purge,
)
from packages.common.schemas import Submit, Completion
from packages.common.tokenizer import cost
from packages.common.security import validate_url, digest
from packages.common.webhooks import signature, verify, send
from packages.common.providers import RunpodProvider, NotConfigured, FakeProvider, GpuSpec, watchdog
from packages.common.payments import handle_event
from packages.common.config import settings
from apps.worker.engines import MockInferenceEngine


def body(n=1, **kwargs):
    return {
        "requests": [
            {
                "custom_id": str(i),
                "messages": [{"role": "user", "content": "Summarize this document."}],
                "max_output_tokens": 128,
            }
            for i in range(n)
        ],
        **kwargs,
    }


def register(client):
    r = client.post(
        "/internal/workers/register",
        headers={"Authorization": "Bearer local-worker-only"},
        json={"id": "worker", "capacity": 16},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["worker_token"]}


def drain(client, wh):
    for _ in range(30):
        with Session.begin() as s:
            schedule(s)
        r = client.post("/internal/workers/poll", headers=wh)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        if not items:
            break

        async def run():
            return await asyncio.gather(*(MockInferenceEngine().execute(i) for i in items))

        outputs = asyncio.run(run())
        for i, o in zip(items, outputs):
            r = client.post(
                "/internal/workers/requests/" + i["id"] + "/finalize", headers=wh, json={"epoch": i["epoch"], **o}
            )
            assert r.status_code == 200, r.text


def test_lifecycle_100_order_billing(client, headers, tenant):
    r = client.post("/v1/jobs", json=body(100), headers=headers)
    assert r.status_code == 202, r.text
    jid = r.json()["id"]
    assert r.json()["reserved_micro_usd"] > 0
    wh = register(client)
    drain(client, wh)
    result = client.get("/v1/jobs/" + jid, headers=headers).json()
    assert result["status"] == "succeeded", result
    assert result["completed"] == 100 and result["reserved_micro_usd"] == 0
    page = client.get("/v1/jobs/" + jid + "/results?limit=31", headers=headers).json()
    assert page["next_cursor"] == 31
    assert [i["custom_id"] for i in page["items"]] == [str(i) for i in range(31)]
    lines = client.get("/v1/jobs/" + jid + "/results.jsonl", headers=headers).text.splitlines()
    assert len(lines) == 100
    assert all(json.loads(x)["output_text"].startswith("MOCK") for x in lines)
    with Session.begin() as s:
        assert reconcile(s) == []
        w = s.get(Wallet, tenant[0])
        assert w.available == 10000000 - result["captured_micro_usd"] and w.reserved == 0
        assert s.scalar(select(func.count()).select_from(Usage)) == 100


def test_idempotency_validation_and_auth(client, headers):
    a = client.post("/v1/jobs", json=body(), headers=headers)
    b = client.post("/v1/jobs", json=body(), headers=headers)
    assert a.json()["id"] == b.json()["id"]
    assert client.post("/v1/jobs", json=body(2), headers=headers).status_code == 409
    assert client.get("/v1/models").status_code == 401
    assert client.post("/v1/jobs", json=body(101), headers=headers).status_code == 422
    bad = body()
    bad["requests"][0]["tools"] = []
    assert client.post("/v1/jobs", json=bad, headers=headers).status_code == 422
    assert client.post("/v1/jobs", json=body(2), headers={"Authorization": headers["Authorization"]}).status_code == 400


def test_keys_csrf_revocation(client):
    r = client.post("/auth/login", json={"email": "dev@local"})
    csrf = r.json()["csrf_token"]
    h = {"X-CSRF-Token": csrf}
    assert client.post("/v1/keys", json={}).status_code == 403
    k = client.post("/v1/keys", json={"name": "test"}, headers=h).json()
    assert k["key"].startswith("if_live_")
    assert "key" not in client.get("/v1/keys").json()["items"][0]
    assert client.delete("/v1/keys/" + k["id"], headers=h).status_code == 200
    client.cookies.clear()
    assert client.get("/v1/models", headers={"Authorization": "Bearer " + k["key"]}).status_code == 401
    with Session.begin() as s:
        from packages.common.db import Key

        assert s.get(Key, k["id"]).digest == digest(k["key"])


def test_tenant_isolation(client, headers, tenant):
    jid = client.post("/v1/jobs", json=body(), headers=headers).json()["id"]
    with Session.begin() as s:
        t = account(s, "test:b")
        other = new_key(s, t.id, "b")["key"]
    h = {"Authorization": "Bearer " + other}
    for route in [jid, jid + "/results", jid + "/results.jsonl"]:
        assert client.get("/v1/jobs/" + route, headers=h).status_code == 404
    assert client.post("/v1/jobs/" + jid + "/cancel", headers=h).status_code == 404
    assert client.get("/v1/jobs", headers=h).json()["items"] == []
    assert client.get("/v1/wallet", headers=h).json()["total_balance_micro_usd"] == 0
    assert client.post("/internal/workers/poll", headers=headers).status_code == 401
    assert client.post("/v1/keys", json={}, headers=headers).status_code == 401


def test_concurrent_reserves_no_overspend(tenant):
    with Session.begin() as s:
        w = lock_wallet(s, tenant[0])
        post(s, w, "remove", "adjustment", -9999950, 0)

    def attempt(i):
        try:
            with Session.begin() as s:
                submit(s, tenant[0], Submit(**body()), str(i))
            return True
        except Problem as e:
            assert e.status == 402
            return False

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(attempt, range(100)))
    assert 0 < sum(results) < 100
    with Session.begin() as s:
        assert reconcile(s) == []
        w = s.get(Wallet, tenant[0])
        assert w.available >= 0
        assert s.scalar(select(func.count()).select_from(Job)) == sum(results)


def test_concurrent_idempotency(tenant):
    def attempt(i):
        with Session.begin() as s:
            return submit(s, tenant[0], Submit(**body()), "same").id

    with ThreadPoolExecutor(max_workers=20) as pool:
        ids = list(pool.map(attempt, range(100)))
    assert len(set(ids)) == 1


def test_duplicate_stale_completion_crash_recovery(client, headers):
    jid = client.post("/v1/jobs", json=body(), headers=headers).json()["id"]
    wh = register(client)
    with Session.begin() as s:
        schedule(s)
    item = client.post("/internal/workers/poll", headers=wh).json()["items"][0]
    output = asyncio.run(MockInferenceEngine().execute(item))
    with Session.begin() as s:
        s.get(Work, item["id"]).lease_until = now() - timedelta(seconds=1)
    with Session.begin() as s:
        schedule(s)
    with Session.begin() as s:
        s.get(Work, item["id"]).eligible_at = now() - timedelta(seconds=1)
    with Session.begin() as s:
        schedule(s)
    current = client.post("/internal/workers/poll", headers=wh).json()["items"][0]
    path = "/internal/workers/requests/" + item["id"] + "/finalize"
    assert client.post(path, headers=wh, json={"epoch": item["epoch"], **output}).status_code == 409
    assert client.post(path, headers=wh, json={"epoch": current["epoch"], **output}).status_code == 200
    assert client.post(path, headers=wh, json={"epoch": current["epoch"], **output}).status_code == 409
    assert client.get("/v1/jobs/" + jid, headers=headers).json()["status"] == "succeeded"
    with Session.begin() as s:
        assert reconcile(s) == []
        assert s.scalar(select(func.count()).select_from(Usage)) == 1


def test_cancel_deadline_permanent_partial_late(client, headers):
    jid = client.post("/v1/jobs", json=body(3), headers=headers).json()["id"]
    wh = register(client)
    with Session.begin() as s:
        schedule(s)
    items = client.post("/internal/workers/poll", headers=wh).json()["items"]
    with Session.begin() as s:
        s.get(Job, jid).target = now() - timedelta(seconds=1)
    first = items[0]
    out = asyncio.run(MockInferenceEngine().execute(first))
    assert (
        client.post(
            "/internal/workers/requests/" + first["id"] + "/finalize", headers=wh, json={"epoch": first["epoch"], **out}
        ).status_code
        == 200
    )
    failed = items[1]
    client.post(
        "/internal/workers/requests/" + failed["id"] + "/finalize",
        headers=wh,
        json={"epoch": failed["epoch"], "error": "permanent"},
    )
    client.post("/v1/jobs/" + jid + "/cancel", headers=headers)
    last = items[2]
    out = asyncio.run(MockInferenceEngine().execute(last))
    client.post(
        "/internal/workers/requests/" + last["id"] + "/finalize", headers=wh, json={"epoch": last["epoch"], **out}
    )
    j = client.get("/v1/jobs/" + jid, headers=headers).json()
    assert j["status"] == "partially_succeeded" and j["late"] and j["reserved_micro_usd"] == 0
    h = {**headers, "Idempotency-Key": "queued"}
    jid2 = client.post("/v1/jobs", json=body(), headers=h).json()["id"]
    assert client.post("/v1/jobs/" + jid2 + "/cancel", headers=headers).json()["status"] == "canceled"
    h["Idempotency-Key"] = "expiry"
    jid3 = client.post("/v1/jobs", json=body(), headers=h).json()["id"]
    with Session.begin() as s:
        s.get(Job, jid3).target = now() - timedelta(seconds=1)
    with Session.begin() as s:
        schedule(s)
    assert client.get("/v1/jobs/" + jid3, headers=headers).json()["status"] == "expired"
    with Session.begin() as s:
        assert reconcile(s) == []


def test_retry_exhaustion_and_missing_usage(client, headers):
    client.post("/v1/jobs", json=body(2), headers=headers)
    wh = register(client)
    with Session.begin() as s:
        schedule(s)
    items = client.post("/internal/workers/poll", headers=wh).json()["items"]
    i = items[0]
    client.post(
        "/internal/workers/requests/" + i["id"] + "/finalize",
        headers=wh,
        json={"epoch": i["epoch"], "output_text": "unmetered"},
    )
    with Session.begin() as s:
        r = s.get(Work, i["id"])
        assert r.status == "billing_pending" and r.captured == 0
        r = s.get(Work, items[1]["id"])
        r.attempts = 3
        r.lease_until = now() - timedelta(seconds=1)
    with Session.begin() as s:
        schedule(s)
    with Session.begin() as s:
        assert s.get(Work, items[1]["id"]).status == "failed"
        assert reconcile(s) == []


def test_rounding_and_immutable_ledger(tenant):
    assert cost(1, 1) == 1 and cost(1000000, 300000) == 300000 and cost(0, 123) == 0
    with pytest.raises(Exception):
        with Session.begin() as s:
            s.execute(text("UPDATE wallet_ledger SET available_delta=0"))


def test_ssrf(monkeypatch):
    for url in [
        "http://example.com",
        "https://127.0.0.1",
        "https://localhost",
        "https://169.254.169.254",
        "https://10.0.0.1",
        "https://[::1]",
        "https://user:pass@example.com",
    ]:
        with pytest.raises((ValueError, OSError)):
            validate_url(url)
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("8.8.8.8", 443))])
    assert validate_url("https://example.com") == ["8.8.8.8"]
    with pytest.raises(ValueError):
        send("https://example.com", '["1.1.1.1"]', b"{}", {})
    stamp = str(int(time.time()))
    sig = signature("secret", stamp, b"{}")
    assert verify("secret", stamp, b"{}", sig) and not verify("secret", str(int(stamp) - 301), b"{}", sig)


def test_payments_dedupe_refund(tenant):
    obj = {
        "id": "cs_test",
        "payment_intent": "pi_test",
        "payment_status": "paid",
        "currency": "usd",
        "amount_total": 1000,
        "client_reference_id": tenant[0],
    }
    event = {"id": "evt_test", "livemode": False, "type": "checkout.session.completed", "data": {"object": obj}}
    for _ in range(2):
        with Session.begin() as s:
            handle_event(s, event)
    event2 = {**event, "id": "evt_other"}
    with Session.begin() as s:
        handle_event(s, event2)
    with Session.begin() as s:
        assert s.get(Wallet, tenant[0]).available == 20000000
    event = {
        "id": "evt_refund",
        "livemode": False,
        "type": "charge.refunded",
        "data": {"object": {"payment_intent": "pi_test", "amount_refunded": 1000}},
    }
    for _ in range(2):
        with Session.begin() as s:
            handle_event(s, event)
    with Session.begin() as s:
        assert s.get(Wallet, tenant[0]).available == 10000000
        assert reconcile(s) == []


def test_stripe_signature_invalid(client, monkeypatch):
    monkeypatch.setattr(settings(), "stripe_enabled", True)
    monkeypatch.setattr(settings(), "stripe_webhook_secret", "whsec_test")
    assert (
        client.post("/internal/stripe/webhook", content=b"{}", headers={"stripe-signature": "bad"}).status_code == 400
    )


def test_provider_killswitch_and_orphans():
    with pytest.raises(NotConfigured):
        RunpodProvider().create_instance(GpuSpec("GPU", "US", "image", 1000000), "test")
    fake = FakeProvider()
    fake.create_instance(GpuSpec("GPU", "US", "image", 1000000), "test")
    watchdog(fake)
    assert fake.list_instances() == []


def test_ttl_keeps_ledger(client, headers):
    jid = client.post("/v1/jobs", json=body(), headers=headers).json()["id"]
    wh = register(client)
    drain(client, wh)
    with Session.begin() as s:
        r = s.scalar(select(Work).where(Work.job_id == jid))
        r.completed_at = now() - timedelta(days=8)
    with Session.begin() as s:
        purge(s)
    with Session.begin() as s:
        r = s.scalar(select(Work).where(Work.job_id == jid))
        assert r.payload is None and r.output is None
        assert s.scalar(select(func.count()).select_from(Ledger)) == 4 and reconcile(s) == []


def test_100_concurrent_submissions_then_execute(tenant, client):
    def create(i):
        with Session.begin() as s:
            return submit(s, tenant[0], Submit(**body()), str(i)).id

    with ThreadPoolExecutor(max_workers=20) as pool:
        ids = list(pool.map(create, range(100)))
    assert len(set(ids)) == 100
    wh = register(client)
    drain(client, wh)
    with Session.begin() as s:
        assert s.scalar(select(func.count()).select_from(Work).where(Work.status != "succeeded")) == 0
        assert reconcile(s) == []


def test_concurrent_finalizers_exactly_once(client, headers):
    client.post("/v1/jobs", json=body(), headers=headers)
    wh = register(client)
    with Session.begin() as s:
        schedule(s)
    i = client.post("/internal/workers/poll", headers=wh).json()["items"][0]
    output = asyncio.run(MockInferenceEngine().execute(i))

    def complete(_):
        try:
            with Session.begin() as s:
                finalize(s, "worker", i["id"], Completion(epoch=i["epoch"], **output))
            return True
        except Problem as e:
            assert e.code == "stale_lease"
            return False

    with ThreadPoolExecutor(max_workers=16) as pool:
        values = list(pool.map(complete, range(32)))
    assert sum(values) == 1
    with Session.begin() as s:
        assert reconcile(s) == []
        assert s.scalar(select(func.count()).select_from(Usage)) == 1


def test_provider_http_contract_caps_and_intent(monkeypatch):
    import httpx

    cfg = settings()
    monkeypatch.setattr(cfg, "provisioning_enabled", True)
    monkeypatch.setattr(cfg, "runpod_api_key", "test-not-real")
    state = []

    def handler(request):
        if request.method == "GET" and request.url.path == "/v2/pods":
            return httpx.Response(200, json={"pods": state, "pagination": {"hasNextPage": False}})
        if request.method == "POST":
            data = json.loads(request.content)
            assert data["gpu"]["count"] == 1 and data["env"]["IF_OWNER"] == "inferenceflow"
            pod = {"id": "pod_test", "name": data["name"], "cost": 1}
            state.append(pod)
            return httpx.Response(201, json=pod)
        if request.method == "GET":
            return httpx.Response(200, json=state[0])
        return httpx.Response(204)

    provider = RunpodProvider(httpx.Client(base_url="https://api.runpod.io/v2", transport=httpx.MockTransport(handler)))
    spec = GpuSpec("NVIDIA L40S", "US", "image@sha256:test", 1000000)
    assert provider.create_instance(spec, "one")["id"] == "pod_test"
    assert provider.create_instance(spec, "one")["id"] == "pod_test"
    with pytest.raises(NotConfigured):
        provider.create_instance(spec, "two")
    provider.terminate_instance("pod_test")


def test_webhook_redirect_denied(monkeypatch):
    import httpx
    from packages.common import webhooks

    monkeypatch.setattr(webhooks, "validate_url", lambda u: ["8.8.8.8"])
    real_client = httpx.Client

    def client(**kwargs):
        def handler(request):
            assert request.url.host == "8.8.8.8"
            assert request.headers["host"] == "example.com"
            assert request.extensions["sni_hostname"] == b"example.com"
            return httpx.Response(302, headers={"location": "https://127.0.0.1"})

        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(webhooks.httpx, "Client", client)
    with pytest.raises(ValueError):
        send("https://example.com/hook", '["8.8.8.8"]', b"{}", {})


def test_webhook_enqueue_once_and_delivery_retry(client, headers, monkeypatch, tenant):
    from packages.common.db import Tenant, Delivery
    from packages.common.security import encrypt
    from packages.common import webhooks

    with Session.begin() as s:
        t = s.get(Tenant, tenant[0])
        t.webhook_url = "https://example.com/hook"
        t.webhook_ips = '["8.8.8.8"]'
        t.webhook_secret = encrypt("secret")
    client.post("/v1/jobs", json=body(), headers=headers)
    wh = register(client)
    drain(client, wh)
    for _ in range(2):
        with Session.begin() as s:
            webhooks.enqueue(s)

    def fail(*args):
        raise ValueError("failure")

    monkeypatch.setattr(webhooks, "send", fail)
    webhooks.deliver()
    with Session.begin() as s:
        deliveries = list(s.scalars(select(Delivery)))
        assert len(deliveries) == 1
        assert deliveries[0].attempts == 1 and not deliveries[0].delivered
        deliveries[0].due = now() - timedelta(seconds=1)
    monkeypatch.setattr(webhooks, "send", lambda *args: None)
    webhooks.deliver()
    with Session.begin() as s:
        assert s.scalar(select(Delivery)).delivered


def test_logs_redact_sensitive_body(client, headers, capsys):
    data = body()
    data["requests"][0]["messages"][0]["content"] = "private-customer-prompt-1234"
    client.post("/v1/jobs", json=data, headers=headers)
    log = capsys.readouterr().out
    assert "private-customer-prompt-1234" not in log and headers["Authorization"] not in log
    assert "request_id" in log


def test_metrics_and_body_limit(client, headers):
    assert client.get("/readyz").status_code == 200
    assert "inferenceflow_wallet_drift" in client.get("/metrics").text
    assert client.post("/v1/jobs", content=b"x" * (5 * 1024 * 1024 + 1), headers=headers).status_code == 413


def test_oidc_flow_state_rejected(client, monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, "oidc_authorization_url", "https://identity.example/authorize")
    monkeypatch.setattr(cfg, "oidc_client_id", "test-client")
    r = client.get("/auth/oidc/start", follow_redirects=False)
    assert r.status_code == 303 and "code_challenge=" in r.headers["location"]
    assert client.get("/auth/oidc/callback?state=wrong&code=invalid").status_code == 401


def test_audited_usage_reconciliation(client, headers):
    from packages.common.service import reconcile_request

    client.post("/v1/jobs", json=body(), headers=headers)
    wh = register(client)
    with Session.begin() as s:
        schedule(s)
    item = client.post("/internal/workers/poll", headers=wh).json()["items"][0]
    client.post(
        "/internal/workers/requests/" + item["id"] + "/finalize",
        headers=wh,
        json={"epoch": item["epoch"], "output_text": "durable output"},
    )
    with Session.begin() as s:
        reconcile_request(s, item["id"], item["prompt_tokens"], 4, "review-123")
    with Session.begin() as s:
        r = s.get(Work, item["id"])
        assert r.status == "succeeded" and r.captured > 0 and reconcile(s) == []
    with pytest.raises(Problem):
        with Session.begin() as s:
            reconcile_request(s, item["id"], item["prompt_tokens"], 4, "review-duplicate")


def test_oidc_authorization_code_success(client, monkeypatch):
    import jwt
    from types import SimpleNamespace
    from cryptography.hazmat.primitives.asymmetric import rsa
    from apps.api import oidc

    cfg = settings()
    for attr, value in {
        "oidc_authorization_url": "https://identity.example/auth",
        "oidc_token_url": "https://identity.example/token",
        "oidc_client_id": "client",
        "oidc_audience": "client",
        "oidc_issuer": "https://identity.example",
        "oidc_jwks_url": "https://identity.example/jwks",
    }.items():
        monkeypatch.setattr(cfg, attr, value)
    client.get("/auth/oidc/start", follow_redirects=False)
    flow = jwt.decode(client.cookies["if_oidc_flow"], cfg.secret_key, algorithms=["HS256"], audience="oidc-flow")
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    identity = jwt.encode(
        {
            "sub": "oidc-user",
            "aud": "client",
            "iss": cfg.oidc_issuer,
            "exp": now() + timedelta(minutes=5),
            "nonce": flow["nonce"],
        },
        private,
        algorithm="RS256",
    )

    class TokenClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, data):
            assert data["code_verifier"] == flow["verifier"] and data["code"] == "valid-code"
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"id_token": identity})

    monkeypatch.setattr(oidc.httpx, "Client", TokenClient)
    monkeypatch.setattr(
        jwt.PyJWKClient, "get_signing_key_from_jwt", lambda self, raw: SimpleNamespace(key=private.public_key())
    )
    r = client.get("/auth/oidc/callback", params={"state": flow["state"], "code": "valid-code"}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/auth/session").json()["csrf_token"]
    assert client.get("/v1/wallet").json()["total_balance_micro_usd"] == 0


def test_checkout_and_signed_payment_webhook(client, monkeypatch):
    import hashlib
    import hmac
    from types import SimpleNamespace
    from apps.api import main

    cfg = settings()
    monkeypatch.setattr(cfg, "stripe_enabled", True)
    monkeypatch.setattr(cfg, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(cfg, "stripe_webhook_secret", "whsec_fake")
    monkeypatch.setattr(cfg, "public_beta_enabled", True)
    login = client.post("/auth/login", json={"email": "pay@example.local"}).json()
    headers = {"X-CSRF-Token": login["csrf_token"]}
    monkeypatch.setattr(
        main.stripe.checkout.Session,
        "create",
        lambda **kwargs: SimpleNamespace(url="https://checkout.stripe.com/test-session"),
    )
    assert client.post("/v1/billing/checkout-session", json={"amount_usd": 10}, headers=headers).status_code == 200
    assert client.get("/v1/wallet").json()["total_balance_micro_usd"] == 0
    event = {
        "id": "evt_signed",
        "object": "event",
        "livemode": False,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_signed",
                "payment_intent": "pi_signed",
                "client_reference_id": login["tenant_id"],
                "payment_status": "paid",
                "currency": "usd",
                "amount_total": 1000,
            }
        },
    }
    raw = json.dumps(event).encode()
    stamp = str(int(time.time()))
    sig = hmac.new(b"whsec_fake", stamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    for _ in range(2):
        r = client.post("/internal/stripe/webhook", content=raw, headers={"stripe-signature": f"t={stamp},v1={sig}"})
        assert r.status_code == 200, r.text
    assert client.get("/v1/wallet").json()["total_balance_micro_usd"] == 10000000


def test_leased_deadline_cannot_start(client, headers):
    jid = client.post("/v1/jobs", json=body(), headers=headers).json()["id"]
    wh = register(client)
    with Session.begin() as s:
        schedule(s)
    with Session.begin() as s:
        s.get(Job, jid).target = now() - timedelta(seconds=1)
    assert client.post("/internal/workers/poll", headers=wh).json()["items"] == []
    assert client.get("/v1/jobs/" + jid, headers=headers).json()["status"] == "expired"
    with Session.begin() as s:
        assert reconcile(s) == []


def test_vllm_http_protocol():
    import httpx
    from apps.worker.engines import VllmInferenceEngine

    calls = []

    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={})
        p = json.loads(request.content)
        calls.append(p)
        assert p["stream"] is False and p["chat_template_kwargs"] == {"enable_thinking": False}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Paris"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 18, "completion_tokens": 1},
            },
        )

    async def run():
        engine = VllmInferenceEngine()
        await engine.client.aclose()
        engine.client = httpx.AsyncClient(base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(handler))
        assert await engine.ready()
        result = await engine.execute({"payload": body()["requests"][0] | {"temperature": 0.2, "top_p": 1.0}})
        assert result["output_text"] == "Paris" and result["input_tokens"] == 18 and result["output_tokens"] == 1
        await engine.client.aclose()

    asyncio.run(run())
    assert len(calls) == 2


def test_provider_catalog_endpoint():
    import httpx

    def handler(request):
        assert request.method == "GET" and request.url.path == "/v2/catalog/gpus"
        return httpx.Response(200, json={"gpus": []})

    provider = RunpodProvider(httpx.Client(base_url="https://api.runpod.io/v2", transport=httpx.MockTransport(handler)))
    assert provider.get_price_quote("GPU", "US")["catalog"] == {"gpus": []}


def test_pending_usage_retention_release(client, headers):
    from packages.common.service import reconcile_request

    client.post("/v1/jobs", json=body(), headers=headers)
    wh = register(client)
    with Session.begin() as s:
        schedule(s)
    item = client.post("/internal/workers/poll", headers=wh).json()["items"][0]
    client.post(
        "/internal/workers/requests/" + item["id"] + "/finalize",
        headers=wh,
        json={"epoch": item["epoch"], "output_text": "private unmetered output"},
    )
    with Session.begin() as s:
        s.get(Work, item["id"]).started_at = now() - timedelta(days=8)
    with Session.begin() as s:
        purge(s)
    with Session.begin() as s:
        r = s.get(Work, item["id"])
        assert r.payload is None and r.output is None
        reconcile_request(s, r.id, 0, 0, "release-review", release_only=True)
    with Session.begin() as s:
        r = s.get(Work, item["id"])
        assert r.status == "failed" and r.captured == 0 and r.released == r.reservation
        assert reconcile(s) == []


def test_kv_headroom_pauses_dispatch(client, headers):
    from packages.common.db import Worker

    client.post("/v1/jobs", json=body(), headers=headers)
    wh = register(client)
    assert (
        client.post(
            "/internal/workers/heartbeat", headers=wh, json={"kv_cache_usage": 0.95, "gpu_utilization": 0.8}
        ).status_code
        == 200
    )
    with Session.begin() as s:
        schedule(s)
    assert client.post("/internal/workers/poll", headers=wh).json()["items"] == []
    with Session.begin() as s:
        w = s.get(Worker, "worker")
        assert json.loads(w.telemetry)["kv_cache_usage"] == 0.95
    client.post("/internal/workers/heartbeat", headers=wh, json={"kv_cache_usage": 0.2})
    with Session.begin() as s:
        schedule(s)
    assert len(client.post("/internal/workers/poll", headers=wh).json()["items"]) == 1
