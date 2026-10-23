import json
import secrets
from datetime import timedelta
from contextlib import asynccontextmanager
import jwt
import stripe
from fastapi import FastAPI, Depends, Request, Header, Query
from fastapi.responses import JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text, case
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST, REGISTRY
from packages.common.metrics import PlatformCollector

from packages.common.config import settings
from packages.common.db import Session, Tenant, Wallet, Key, Job, Work, Worker, Ledger, now, uid
from packages.common.security import digest_candidates, digest, token, encrypt, decrypt, validate_url
from packages.common.schemas import Submit, Completion, Registration, NamedKey, Checkout, Telemetry, Poll
from packages.common import service as svc
from packages.common.payments import handle_event
from apps.api.oidc import router as oidc_router

REGISTRY.register(PlatformCollector())


@asynccontextmanager
async def lifespan(app):
    settings().validate_runtime()
    yield


app = FastAPI(
    title="InferenceFlow",
    version="0.3.0",
    lifespan=lifespan,
    description="Prepaid asynchronous inference. Local mode uses deterministic mock execution and test-only rates. Targets are best effort; completed running work may be billed after cancellation.",
)
app.include_router(oidc_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings().dashboard_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-CSRF-Token"],
)
requests_metric = Counter("inferenceflow_http_requests_total", "HTTP requests", ["method", "status"])


@app.middleware("http")
async def boundary(request, call_next):
    rid = "req_" + uid()
    request.state.request_id = rid
    # Stream actual body to enforce limits even for chunked transfer.
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 5 * 1024 * 1024:
            return JSONResponse(
                {"error": {"code": "body_too_large", "message": "5 MiB limit", "retryable": False}, "request_id": rid},
                413,
            )
    request._body = bytes(data)
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Content-Type-Options"] = "nosniff"
    requests_metric.labels(request.method, str(response.status_code)).inc()
    # Never log headers, payloads, query strings, exceptions or outputs.
    print(json.dumps({"request_id": rid, "method": request.method, "status": response.status_code}), flush=True)
    return response


@app.exception_handler(svc.Problem)
async def problem(request, exc):
    return JSONResponse(
        {
            "error": {"code": exc.code, "message": exc.message, "retryable": exc.status in (429, 503)},
            "request_id": request.state.request_id,
        },
        exc.status,
    )


@app.exception_handler(RequestValidationError)
async def validation(request, exc):
    status_code = 400 if any(e["type"] == "json_invalid" for e in exc.errors()) else 422
    return JSONResponse(
        {
            "error": {"code": "validation_error", "message": "Invalid request parameters", "retryable": False},
            "request_id": request.state.request_id,
        },
        status_code,
    )


def db():
    with Session.begin() as s:
        yield s


def result(request, data):
    return {**data, "request_id": request.state.request_id}


def rate_window(session):
    return session.scalar(text("SELECT floor(extract(epoch FROM clock_timestamp()) / 60)::bigint"))


def rate_limit(tenant_id):
    # Commit independently so a failed endpoint cannot roll back its request allowance.
    from packages.common.db import RateBucket
    from sqlalchemy.dialects.postgresql import insert

    with Session.begin() as session:
        window = rate_window(session)
        statement = insert(RateBucket).values(tenant_id=tenant_id, window=window, hits=1)
        admission = statement.on_conflict_do_update(
            index_elements=[RateBucket.tenant_id],
            set_={"window": window, "hits": case((RateBucket.window == window, RateBucket.hits + 1), else_=1)},
            where=(RateBucket.window != window) | (RateBucket.hits < 120),
        ).returning(RateBucket.hits)
        admitted = session.scalar(admission)
    if admitted is None:
        raise svc.Problem(429, "rate_limit")


def auth(request: Request, s=Depends(db), authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise svc.Problem(401, "unauthorized")
    raw = authorization[7:]
    k = s.scalar(select(Key).where(Key.digest.in_(digest_candidates(raw)), Key.revoked.is_(False)))
    if not k:
        raise svc.Problem(401, "unauthorized")
    if k.digest != digest(raw):
        k.digest = digest(raw)
    rate_limit(k.tenant_id)
    return k.tenant_id


def dashboard(request: Request, s=Depends(db), authorization: str = Header(default="")):
    raw = request.cookies.get("if_session", "")
    try:
        claims = jwt.decode(raw, settings().secret_key, algorithms=["HS256"], audience="dashboard")
    except jwt.PyJWTError:
        raise svc.Problem(401, "dashboard_session_required")
    if request.method not in ("GET", "HEAD"):
        if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), claims["csrf"]):
            raise svc.Problem(403, "csrf")
    t = s.get(Tenant, claims["sub"])
    if not t:
        raise svc.Problem(401, "unauthorized")
    rate_limit(t.id)
    return t.id


def customer(request: Request, s=Depends(db), authorization: str = Header(default="")):
    if request.cookies.get("if_session"):
        return dashboard(request, s, authorization)
    return auth(request, s, authorization)


def worker_auth(request: Request, s=Depends(db), authorization: str = Header(default="")):
    raw = authorization.removeprefix("Bearer ")
    w = s.scalar(select(Worker).where(Worker.token_hash.in_(digest_candidates(raw)), Worker.expires_at > now()))
    if not w:
        raise svc.Problem(401, "worker_unauthorized")
    if w.token_hash != digest(raw):
        w.token_hash = digest(raw)
    return w.id


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.get("/readyz")
def ready(s=Depends(db)):
    s.execute(text("SELECT 1"))
    return {"status": "ready", "execution_mode": settings().execution_mode}


@app.get("/metrics")
def metrics(authorization: str = Header(default="")):
    expected = settings().metrics_token
    if not expected or not secrets.compare_digest(authorization, "Bearer " + expected):
        raise svc.Problem(401, "metrics_unauthorized")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/auth/login")
def login(request: Request, payload: dict, s=Depends(db)):
    if settings().environment == "development":
        subject = "dev:" + str(payload.get("email", "developer@example.local"))
    else:
        raise svc.Problem(403, "use_oidc_authorization_flow")
    t = svc.account(s, subject)
    csrf = secrets.token_urlsafe(32)
    encoded = jwt.encode(
        {"sub": t.id, "aud": "dashboard", "csrf": csrf, "exp": now() + timedelta(hours=8)},
        settings().secret_key,
        algorithm="HS256",
    )
    response = JSONResponse(result(request, {"tenant_id": t.id, "csrf_token": csrf, "mode": settings().execution_mode}))
    response.set_cookie(
        "if_session",
        encoded,
        httponly=True,
        secure=settings().environment != "development",
        samesite="strict",
        max_age=28800,
    )
    return response


@app.post("/auth/logout")
def logout(request: Request, t=Depends(dashboard)):
    response = JSONResponse(result(request, {"ok": True}))
    response.delete_cookie("if_session")
    return response


@app.get("/v1/keys")
def keys(request: Request, t=Depends(dashboard), s=Depends(db)):
    return result(
        request,
        {
            "items": [
                {"id": k.id, "name": k.name, "prefix": k.prefix, "revoked": k.revoked}
                for k in s.scalars(select(Key).where(Key.tenant_id == t))
            ]
        },
    )


@app.post("/v1/keys", status_code=201)
def create_key(request: Request, body: NamedKey, t=Depends(dashboard), s=Depends(db)):
    return result(request, svc.new_key(s, t, body.name))


@app.delete("/v1/keys/{kid}")
def revoke_key(request: Request, kid: str, t=Depends(dashboard), s=Depends(db)):
    k = s.scalar(select(Key).where(Key.id == kid, Key.tenant_id == t))
    if not k:
        raise svc.Problem(404, "not_found")
    k.revoked = True
    return result(request, {"revoked": True})


@app.get("/v1/models")
def models(request: Request, t=Depends(customer)):
    cfg = settings()
    return result(
        request,
        {
            "models": [
                {
                    "id": "qwen3-4b",
                    "display_name": "Qwen3 4B",
                    "revision": cfg.model_revision,
                    "tokenizer_revision": cfg.model_revision,
                    "max_context_tokens": 10240,
                    "max_prompt_tokens": 8192,
                    "max_output_tokens": 2048,
                    "input_price_micro_usd_per_million": cfg.input_rate,
                    "output_price_micro_usd_per_million": cfg.output_rate,
                    "supported_tiers": ["standard", "economy"],
                    "availability": "best_effort",
                    "execution_mode": cfg.execution_mode,
                    "rates_test_only": not cfg.public_beta_enabled,
                }
            ]
        },
    )


@app.post("/v1/jobs", status_code=202)
def create_job(
    request: Request, body: Submit, idempotency_key: str = Header(default=""), t=Depends(customer), s=Depends(db)
):
    return result(request, svc.view(s, svc.submit(s, t, body, idempotency_key)))


@app.get("/v1/jobs")
def jobs(
    request: Request,
    cursor: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    t=Depends(customer),
    s=Depends(db),
):
    rows = list(
        s.scalars(
            select(Job).where(Job.tenant_id == t).order_by(Job.created_at.desc(), Job.id).offset(cursor).limit(limit)
        )
    )
    return result(
        request,
        {"items": [svc.view(s, j) for j in rows], "next_cursor": cursor + limit if len(rows) == limit else None},
    )


@app.get("/v1/jobs/{jid}")
def job(request: Request, jid: str, t=Depends(customer), s=Depends(db)):
    return result(request, svc.view(s, svc.owned(s, t, jid)))


def item(r):
    return {
        "ordinal": r.ordinal,
        "custom_id": r.custom_id,
        "status": r.status,
        "output_text": decrypt(r.output) if r.output and r.status == "succeeded" else None,
        "finish_reason": r.finish_reason,
        "usage": {"input_tokens": r.input_tokens, "output_tokens": r.output_tokens},
        "charge_micro_usd": r.captured,
        "error": r.error,
        "late": r.late,
    }


@app.get("/v1/jobs/{jid}/results")
def results(
    request: Request,
    jid: str,
    cursor: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    t=Depends(customer),
    s=Depends(db),
):
    j = svc.owned(s, t, jid)
    rows = svc.works(s, jid)
    page = rows[cursor : cursor + limit]
    return result(
        request,
        {
            "job_id": jid,
            "items": [item(r) for r in page],
            "next_cursor": cursor + limit if cursor + limit < len(rows) else None,
            "complete": svc.status(j, rows) in svc.TERMINAL | {"partially_succeeded"},
        },
    )


@app.get("/v1/jobs/{jid}/results.jsonl")
def jsonl(request: Request, jid: str, t=Depends(customer), s=Depends(db)):
    svc.owned(s, t, jid)
    return Response(
        "".join(json.dumps(item(r)) + "\n" for r in svc.works(s, jid)),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{jid}.jsonl"'},
    )


@app.post("/v1/jobs/{jid}/cancel")
def cancel(request: Request, jid: str, t=Depends(customer), s=Depends(db)):
    return result(request, svc.cancel(s, svc.owned(s, t, jid)))


@app.get("/v1/wallet")
def wallet(request: Request, t=Depends(customer), s=Depends(db)):
    w = s.get(Wallet, t)
    return result(
        request,
        {
            "available_micro_usd": w.available,
            "reserved_micro_usd": w.reserved,
            "debt_micro_usd": w.debt,
            "total_balance_micro_usd": w.available + w.reserved,
            "frozen": s.get(Tenant, t).frozen,
        },
    )


@app.get("/v1/performance")
def performance(request: Request, t=Depends(customer), s=Depends(db)):
    from packages.common.performance import performance_report
    return result(request, performance_report(s, tenant=t))


@app.get("/internal/scheduling/report")
def scheduling_report(request: Request, authorization: str = Header(default=""), s=Depends(db)):
    expected = settings().metrics_token
    if not expected or not secrets.compare_digest(authorization, "Bearer " + expected):
        raise svc.Problem(401, "metrics_unauthorized")
    from packages.common.performance import operations_report
    return result(request, operations_report(s))


@app.get("/v1/wallet/transactions")
def transactions(
    request: Request,
    cursor: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    t=Depends(customer),
    s=Depends(db),
):
    rows = list(
        s.scalars(
            select(Ledger)
            .where(Ledger.tenant_id == t)
            .order_by(Ledger.created_at, Ledger.id)
            .offset(cursor)
            .limit(limit)
        )
    )
    return result(
        request,
        {
            "items": [
                {
                    "id": r.id,
                    "kind": r.kind,
                    "available_delta": r.available_delta,
                    "reserved_delta": r.reserved_delta,
                    "debt_delta": r.debt_delta,
                    "source": r.source,
                    "created_at": r.created_at,
                }
                for r in rows
            ],
            "next_cursor": cursor + limit if len(rows) == limit else None,
        },
    )


@app.post("/v1/webhook-destination")
def destination(request: Request, body: dict, t=Depends(dashboard), s=Depends(db)):
    try:
        ips = validate_url(body["url"])
    except (ValueError, KeyError, OSError):
        raise svc.Problem(422, "invalid_webhook")
    tenant = s.get(Tenant, t)
    secret = token("whsec_")
    tenant.webhook_url = body["url"]
    tenant.webhook_ips = json.dumps(ips)
    tenant.webhook_secret = encrypt(secret)
    return result(request, {"url": tenant.webhook_url, "secret": secret})


@app.post("/v1/billing/checkout-session")
def checkout(request: Request, body: Checkout, t=Depends(dashboard)):
    cfg = settings()
    if not cfg.stripe_enabled or not cfg.public_beta_enabled:
        raise svc.Problem(503, "stripe_disabled")
    if not cfg.stripe_secret_key.startswith("sk_test_"):
        raise svc.Problem(503, "test_mode_required")
    stripe.api_key = cfg.stripe_secret_key
    session = stripe.checkout.Session.create(
        mode="payment",
        client_reference_id=t,
        metadata={"tenant_id": t},
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": body.amount_usd * 100,
                    "product_data": {"name": "InferenceFlow prepaid test credits"},
                },
                "quantity": 1,
            }
        ],
        success_url=cfg.dashboard_url + "/?payment=returned",
        cancel_url=cfg.dashboard_url,
    )
    return result(request, {"url": session.url})


@app.post("/internal/stripe/webhook")
async def payment_webhook(request: Request, s=Depends(db)):
    if not settings().stripe_enabled:
        raise svc.Problem(503, "stripe_disabled")
    try:
        event = stripe.Webhook.construct_event(
            await request.body(), request.headers.get("stripe-signature", ""), settings().stripe_webhook_secret
        )
    except Exception:
        raise svc.Problem(400, "invalid_signature")
    handle_event(s, event)
    return result(request, {"received": True})


@app.post("/internal/workers/register")
def register(request: Request, body: Registration, authorization: str = Header(default=""), s=Depends(db)):
    if not secrets.compare_digest(authorization, "Bearer " + settings().worker_bootstrap_token):
        raise svc.Problem(401, "worker_unauthorized")
    raw = token("if_worker_")
    # Serialize concurrent enrollment for an ID, including the first insert.
    s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:identity))"), {"identity": "worker:" + body.id})
    w = s.scalar(select(Worker).where(Worker.id == body.id).with_for_update())

    if not w:
        w = Worker(id=body.id)
        s.add(w)
    if body.revision != settings().model_revision:
        raise svc.Problem(422, "model_revision_mismatch")
    if (body.repo, body.tokenizer_revision, body.execution_mode) != (
        settings().model_repo,
        settings().model_revision,
        settings().execution_mode,
    ):
        raise svc.Problem(422, "model_identity_mismatch")
    w.generation = uid()
    w.telemetry = None
    w.telemetry_at = None
    w.adaptive_limit = min(body.capacity, settings().adaptive_initial_slots)
    w.adaptive_changed_at = None
    w.model_loading_seconds = int(body.model_loading_seconds)
    w.revision = body.revision
    w.repo = body.repo
    w.tokenizer_revision = body.tokenizer_revision
    w.execution_mode = body.execution_mode
    w.provider_instance_id = body.provider_instance_id
    w.model = body.model
    w.capacity = body.capacity
    w.token_hash = digest(raw)
    w.heartbeat = now()
    w.expires_at = now() + timedelta(hours=1)
    return result(request, {"worker_token": raw, "expires_at": w.expires_at})


@app.post("/internal/workers/heartbeat")
def heartbeat(request: Request, body: Telemetry | None = None, wid=Depends(worker_auth), s=Depends(db)):
    # Same wallet-first ordering as scheduler/finalize; heartbeat cannot resurrect an expired lease.
    tenants = sorted(
        set(s.scalars(select(Work.tenant_id).where(Work.worker_id == wid, Work.status.in_(["leased", "running"]))))
    )
    for tid in tenants:
        svc.lock_wallet(s, tid)
    w = s.scalar(select(Worker).where(Worker.id == wid).with_for_update().execution_options(populate_existing=True))
    w.heartbeat = now()
    if body is not None:
        from packages.common.db import GpuObservation
        # Count only covered heartbeat intervals; a long outage is unknown, never idle.
        elapsed = min(settings().telemetry_stale_seconds, max(0, int((now() - w.telemetry_at).total_seconds()))) if w.telemetry_at else 0
        previous = json.loads(w.telemetry or "{}")
        active_before = bool(previous.get("active")) or previous.get("engine_running", 0) > 0
        if elapsed:
            s.add(GpuObservation(worker_id=wid, instance_id=w.provider_instance_id, mode=w.execution_mode,
                                 active_seconds=elapsed if active_before else 0, idle_seconds=0 if active_before else elapsed))
        w.telemetry = body.model_dump_json(exclude_none=True)
        w.telemetry_at = now()
    canceled = []
    active = {(lease.id, lease.epoch) for lease in (body.active if body else [])}
    for r in s.scalars(
        select(Work)
        .where(Work.worker_id == wid, Work.status.in_(["leased", "running"]), Work.lease_until > now())
        .with_for_update()
    ):
        if r.worker_generation != w.generation or (r.id, r.epoch) not in active:
            continue
        r.lease_until = now() + timedelta(seconds=settings().lease_seconds)
        if s.get(Job, r.job_id).cancel:
            canceled.append(r.id)
    w.expires_at = now() + timedelta(hours=1)
    if w.provider_instance_id:
        from packages.common.db import Instance

        instance = s.get(Instance, w.provider_instance_id)
        active = s.scalar(select(Work.id).where(Work.worker_id == wid, Work.status.in_(["leased", "running"])).limit(1))
        if instance and active:
            instance.last_busy = now()
    return result(request, {"cancel_requested": canceled})


@app.post("/internal/workers/poll")
def poll(request: Request, body: Poll | None = None, wid=Depends(worker_auth), s=Depends(db)):
    tenant_ids = sorted(set(s.scalars(select(Work.tenant_id).where(Work.worker_id == wid, Work.status == "leased"))))
    for tenant_id in tenant_ids:
        svc.lock_wallet(s, tenant_id)
    rows = list(
        s.scalars(
            select(Work)
            .where(Work.worker_id == wid, Work.status == "leased", Work.lease_until > now())
            .limit(body.available_slots if body else 16)
            .with_for_update(skip_locked=True)
        )
    )
    out = []
    node = s.scalar(select(Worker).where(Worker.id == wid).with_for_update().execution_options(populate_existing=True))
    for r in rows:
        if r.worker_generation != node.generation:
            continue
        if s.get(Tenant, r.tenant_id).frozen:
            svc.terminal(s, r, "canceled", "account_frozen")
            continue
        if s.get(Job, r.job_id).target <= now():
            svc.terminal(s, r, "expired")
            continue
        r.status = "running"
        r.started_at = r.started_at or now()
        from packages.common.db import ExecutionAttempt
        from packages.common.scheduling import worker_identity
        s.add(ExecutionAttempt(request_id=r.id, epoch=r.epoch, worker_id=wid,
                               instance_id=node.provider_instance_id, identity=worker_identity(node), mode=node.execution_mode,
                               started_at=now()))
        price = s.get(svc.ModelPrice, r.price_id)
        version = s.get(svc.ModelVersion, price.model_version_id)
        out.append(
            {
                "id": r.id,
                "epoch": r.epoch,
                "prompt_tokens": r.prompt_tokens,
                "payload": decrypt(r.payload),
                "identity": {
                    "repo": version.repo,
                    "revision": version.revision,
                    "tokenizer_revision": version.tokenizer_revision,
                    "execution_mode": version.execution_mode,
                },
            }
        )
    return result(request, {"items": out})


@app.post("/internal/workers/requests/{rid}/finalize")
def finalize(request: Request, rid: str, body: Completion, wid=Depends(worker_auth), s=Depends(db)):
    svc.finalize(s, wid, rid, body)
    return result(request, {"accepted": True})


from packages.common.tracing import instrument  # noqa: E402 -- instrument fully registered application

instrument(app)
