import hashlib
import json
from datetime import timedelta
from sqlalchemy import select, func, text, or_, and_
from packages.common.db import Tenant, Wallet, Ledger, Key, Job, Work, Worker, Usage, Audit, now
from packages.common.security import digest, token, encrypt, decrypt
from packages.common.config import settings
from packages.common.tokenizer import count_prompt, cost
from packages.common.db import ModelVersion, ModelPrice, User, Membership, ExecutionAttempt
from sqlalchemy.dialects.postgresql import insert

TERMINAL = {"succeeded", "failed", "canceled", "expired"}


class Problem(Exception):
    def __init__(self, status, code, message=None):
        self.status, self.code, self.message = status, code, message or code.replace("_", " ")


def lock_wallet(s, tenant):
    return s.scalar(select(Wallet).where(Wallet.tenant_id == tenant).with_for_update())


def post(s, w, source, kind, available, reserved, debt=0):
    if s.scalar(select(Ledger.id).where(Ledger.source == source)):
        return False
    # Credits, including released reservations, repay reversal liabilities first.
    repayment = min(max(available, 0), w.debt)
    available -= repayment
    debt -= repayment
    if w.available + available < 0 or w.reserved + reserved < 0 or w.debt + debt < 0:
        raise Problem(402, "insufficient_credits")
    w.available += available
    w.reserved += reserved
    w.debt += debt
    s.add(
        Ledger(
            tenant_id=w.tenant_id,
            source=source,
            kind=kind,
            available_delta=available,
            reserved_delta=reserved,
            debt_delta=debt,
        )
    )
    s.flush()
    return True


def account(s, subject):
    s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:v))"), {"v": "account:" + subject})
    user = s.scalar(select(User).where(User.subject == subject))
    if user is None:
        user = User(subject=subject)
        s.add(user)
        s.flush()
    tenant_id = s.scalar(select(Membership.tenant_id).where(Membership.user_id == user.id))
    if tenant_id:
        return s.get(Tenant, tenant_id)
    t = s.scalar(select(Tenant).where(Tenant.subject == subject))
    if t is None:
        t = Tenant(subject=subject)
        s.add(t)
        s.flush()
        s.add(Wallet(tenant_id=t.id))
        s.flush()
    s.add(Membership(user_id=user.id, tenant_id=t.id, role="owner"))
    s.flush()
    return t


def new_key(s, tenant, name):
    raw = token()
    k = Key(tenant_id=tenant, name=name, prefix=raw[:16], digest=digest(raw))
    s.add(k)
    s.flush()
    return {"id": k.id, "key": raw, "prefix": k.prefix, "name": name}


def submit(s, tenant, body, idem):
    if not idem or len(idem) > 200:
        raise Problem(400, "idempotency_key_required")
    prepared = []
    for item in body.requests:
        data = item.model_dump()
        n = count_prompt(data["messages"])
        if n > 8192 or n + item.max_output_tokens > 10240:
            raise Problem(422, "context_limit")
        reserve = cost(n, settings().input_rate) + cost(item.max_output_tokens, settings().output_rate)
        prepared.append((data, n, reserve))
    w = lock_wallet(s, tenant)
    canonical = body.model_dump()
    # Preserve pre-v0.3 idempotency fingerprints for the unchanged default policy.
    if body.admission_policy == "best_effort":
        canonical.pop("admission_policy")
    fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    old = s.scalar(select(Job).where(Job.tenant_id == tenant, Job.idempotency_key == idem))
    if old:
        if old.body_hash != fingerprint:
            raise Problem(409, "idempotency_conflict")
        return old
    t = s.scalar(select(Tenant).where(Tenant.id == tenant).execution_options(populate_existing=True))
    if t.frozen or w.debt:
        raise Problem(403, "account_frozen")
    if body.webhook_url and body.webhook_url != t.webhook_url:
        raise Problem(422, "webhook_not_registered")
    pending = s.scalar(
        select(func.count()).select_from(Work).where(Work.tenant_id == tenant, Work.status.not_in(TERMINAL))
    )
    if pending + len(body.requests) > settings().max_pending:
        raise Problem(429, "pending_quota")
    cfg = settings()
    seconds = body.deadline_seconds or (cfg.default_completion_target_seconds if cfg.scheduler_v2_enabled
                                       else (1800 if body.tier == "standard" else 86400))
    prediction = None
    if cfg.scheduler_v2_enabled:
        # Serialize estimates with concurrent accepts; no cross-tenant wallet locks.
        s.execute(text("SELECT pg_advisory_xact_lock(1081844)"))
        from packages.common.scheduling import admission
        prediction = admission(s, prepared, seconds)
        if body.admission_policy == "reject_if_at_risk" and (prediction["at_risk"] or not prediction["calibrated"]):
            raise Problem(503, "deadline_not_feasible", "Target cannot be confidently met; retry with best_effort, a longer deadline, or attached calibrated capacity. No credits reserved.")
    elif body.admission_policy == "reject_if_at_risk":
        raise Problem(503, "deadline_estimator_disabled", "Enable SCHEDULER_V2_ENABLED or use admission_policy=best_effort.")
    version_id = hashlib.sha256((cfg.model_repo + cfg.model_revision + cfg.execution_mode).encode()).hexdigest()
    price_id = hashlib.sha256(
        (version_id + ":" + str(cfg.input_rate) + ":" + str(cfg.output_rate)).encode()
    ).hexdigest()
    s.execute(
        insert(ModelVersion)
        .values(
            id=version_id,
            public_id=body.model,
            repo=cfg.model_repo,
            revision=cfg.model_revision,
            tokenizer_revision=cfg.model_revision,
            execution_mode=cfg.execution_mode,
        )
        .on_conflict_do_nothing()
    )
    s.execute(
        insert(ModelPrice)
        .values(
            id=price_id,
            model_version_id=version_id,
            input_rate=cfg.input_rate,
            output_rate=cfg.output_rate,
            test_only=not cfg.public_beta_enabled,
        )
        .on_conflict_do_nothing()
    )
    if w.available < sum(x[2] for x in prepared):
        raise Problem(402, "insufficient_credits")
    j = Job(
        tenant_id=tenant,
        idempotency_key=idem,
        body_hash=fingerprint,
        model=body.model,
        tier=body.tier,
        target=now() + timedelta(seconds=seconds),
        admission=json.dumps(prediction) if prediction else None,
    )
    s.add(j)
    s.flush()
    for i, (data, n, reserve) in enumerate(prepared):
        r = Work(
            job_id=j.id,
            tenant_id=tenant,
            ordinal=i,
            custom_id=data["custom_id"],
            payload=encrypt(data),
            model_revision=cfg.model_revision,
            price_id=price_id,
            prompt_tokens=n,
            max_output=data["max_output_tokens"],
            input_rate=settings().input_rate,
            output_rate=settings().output_rate,
            reservation=reserve,
        )
        s.add(r)
        s.flush()
        post(s, w, r.id + ":reserve", "reservation", -reserve, reserve)
    return j


def owned(s, tenant, jid):
    j = s.scalar(select(Job).where(Job.id == jid, Job.tenant_id == tenant))
    if not j:
        raise Problem(404, "not_found")
    return j


def works(s, jid):
    return list(s.scalars(select(Work).where(Work.job_id == jid).order_by(Work.ordinal)))


def status(j, rows):
    states = {r.status for r in rows}
    if states <= TERMINAL:
        if states == {"succeeded"}:
            return "succeeded"
        if "succeeded" in states:
            return "partially_succeeded"
        if states == {"canceled"}:
            return "canceled"
        if states == {"expired"}:
            return "expired"
        return "failed"
    if "billing_pending" in states:
        return "billing_pending"
    if j.cancel:
        return "cancel_requested"
    if states & {"running", "leased"}:
        return "running"
    return "queued"


def view(s, j):
    rows = works(s, j.id)
    state = status(j, rows)
    return {
        "id": j.id,
        "status": state,
        "model": j.model,
        "tier": j.tier,
        "total": len(rows),
        "request_count": len(rows),
        "completed": sum(r.status == "succeeded" for r in rows),
        "failed": sum(r.status == "failed" for r in rows),
        "queued": sum(r.status == "queued" for r in rows),
        "running": sum(r.status in {"running", "leased"} for r in rows),
        "created_at": j.created_at,
        "started_at": min((r.started_at for r in rows if r.started_at), default=None),
        "completed_at": max((r.completed_at for r in rows if r.completed_at), default=None)
        if state in TERMINAL | {"partially_succeeded"}
        else None,
        "target_completion_at": j.target,
        "deadline_is_guaranteed": False,
        "admission": json.loads(j.admission) if j.admission else {"outcome": "best_effort", "source": "legacy_scheduler", "calibrated": False},
        "late": any(r.late for r in rows),
        "estimated_max_charge_micro_usd": sum(r.reservation for r in rows),
        "reserved_micro_usd": sum(r.reservation - r.captured - r.released for r in rows),
        "captured_micro_usd": sum(r.captured for r in rows),
        "released_micro_usd": sum(r.released for r in rows),
        "usage": {
            "input_tokens": sum(r.input_tokens for r in rows),
            "output_tokens": sum(r.output_tokens for r in rows),
        },
        "error_summary": sorted({r.error for r in rows if r.error}),
    }


def settle(s, r, charge):
    w = lock_wallet(s, r.tenant_id)
    release = r.reservation - charge
    post(s, w, r.id + ":capture", "capture", 0, -charge)
    post(s, w, r.id + ":release", "release", release, -release)
    r.captured = charge
    r.released = release


def terminal(s, r, state, error=None):
    if r.status in TERMINAL:
        return
    settle(s, r, 0)
    r.status = state
    r.error = error
    r.completed_at = now()
    finish_attempt(s, r, state)


def finish_attempt(s, r, outcome, input_tokens=0, output_tokens=0):
    attempt = s.get(ExecutionAttempt, (r.id, r.epoch))
    if attempt and attempt.ended_at is None:
        attempt.ended_at = now()
        attempt.outcome = outcome
        attempt.input_tokens = input_tokens
        attempt.output_tokens = output_tokens


def cancel(s, j):
    # Every mutation locks tenant wallet before request rows: one lock order everywhere.
    lock_wallet(s, j.tenant_id)
    j.cancel = True
    rows = s.scalars(select(Work).where(Work.job_id == j.id).order_by(Work.id).with_for_update())
    for r in rows:
        if r.status in {"queued", "leased"}:
            terminal(s, r, "canceled")
    s.flush()
    return view(s, j)


def finalize(s, worker, rid, body):
    tenant = s.scalar(select(Work.tenant_id).where(Work.id == rid))
    if tenant is None:
        raise Problem(404, "not_found")
    lock_wallet(s, tenant)
    r = s.scalar(select(Work).where(Work.id == rid).with_for_update())
    if r.worker_id != worker or r.epoch != body.epoch or r.status not in {"leased", "running"} or r.lease_until < now():
        raise Problem(409, "stale_lease")
    j = s.get(Job, r.job_id)
    worker_node = s.scalar(
        select(Worker).where(Worker.id == worker).with_for_update().execution_options(populate_existing=True)
    )
    if worker_node is None or r.worker_generation != worker_node.generation:
        raise Problem(409, "stale_generation")
    if s.get(Tenant, tenant).frozen:
        terminal(s, r, "canceled", "account_frozen")
        return
    if worker_node and worker_node.provider_instance_id:
        from packages.common.db import Instance

        instance = s.get(Instance, worker_node.provider_instance_id)
        if instance:
            instance.last_busy = now()
    if body.error:
        finish_attempt(s, r, body.error)
        if body.error == "transient" and r.attempts < settings().max_attempts and not j.cancel:
            r.status = "queued"
            r.worker_id = None
            r.eligible_at = now() + timedelta(seconds=2**r.attempts)
            r.error = "retry_pending"
        else:
            terminal(s, r, "canceled" if j.cancel else "failed", body.error)
        return
    if (
        body.output_text is None
        or body.input_tokens is None
        or body.output_tokens is None
        or body.input_tokens != r.prompt_tokens
        or body.output_tokens > r.max_output
    ):
        # Preserve reservation for explicit audited reconciliation; no guessed customer charge.
        r.status = "billing_pending"
        finish_attempt(s, r, "usage_mismatch")
        r.error = "usage_mismatch"
        r.output = encrypt(body.output_text)
        s.add(Audit(kind="billing_pending", reference=r.id))
        return
    charge = cost(body.input_tokens, r.input_rate) + cost(body.output_tokens, r.output_rate)
    charge = min(charge, r.reservation)
    settle(s, r, charge)
    r.status = "succeeded"
    r.output = encrypt(body.output_text)
    r.input_tokens = body.input_tokens
    r.output_tokens = body.output_tokens
    r.finish_reason = body.finish_reason
    r.completed_at = now()
    r.late = now() > j.target
    r.error = None
    s.add(Usage(request_id=r.id, input_tokens=r.input_tokens, output_tokens=r.output_tokens, charge=charge))
    finish_attempt(s, r, "succeeded", r.input_tokens, r.output_tokens)


def schedule(s):
    # Serialize dispatch/recovery, then use SKIP LOCKED. Wallet-first ordering prevents API deadlocks.
    if not s.scalar(text("SELECT pg_try_advisory_xact_lock(1081841)")):
        return
    # A busy tenant cannot hold the global dispatcher behind its wallet transaction.
    wallets = list(
        s.scalars(
            select(Wallet)
            .where(Wallet.tenant_id.in_(select(Work.tenant_id).where(Work.status.in_(["queued", "leased", "running"]))))
            .order_by(Wallet.schedule_checked, Wallet.tenant_id)
            .limit(64)
            .with_for_update(skip_locked=True)
        )
    )
    tenants = [w.tenant_id for w in wallets]
    for wallet in wallets:
        wallet.schedule_checked = now()
    for tid in tenants:
        rows = list(
            s.scalars(
                select(Work)
                .where(Work.tenant_id == tid, Work.status.in_(["queued", "leased", "running"]))
                .with_for_update(skip_locked=True)
            )
        )
        for r in rows:
            j = s.get(Job, r.job_id)
            if s.get(Tenant, tid).frozen:
                r.epoch += 1
                terminal(s, r, "canceled", "account_frozen")
                continue
            node = s.get(Worker, r.worker_id) if r.worker_id else None
            if r.status in {"leased", "running"} and (node is None or r.worker_generation != node.generation):
                r.lease_until = now() - timedelta(seconds=1)
            if r.status in {"leased", "running"} and r.lease_until < now():
                finish_attempt(s, r, "lease_lost")
                if j.cancel:
                    terminal(s, r, "canceled")
                elif r.attempts >= settings().max_attempts:
                    terminal(s, r, "failed", "lease_exhausted")
                else:
                    r.status = "queued"
                    r.worker_id = None
                    r.eligible_at = now() + timedelta(seconds=2**r.attempts)
            if r.status in {"queued", "leased"} and j.target <= now():
                terminal(s, r, "expired")
    s.flush()
    workers = list(
        s.scalars(
            select(Worker)
            .where(Worker.heartbeat > now() - timedelta(seconds=90), Worker.expires_at > now())
            .order_by(Worker.id)
            .with_for_update(skip_locked=True)
        )
    )
    from packages.common.scheduling import context
    estimator = context(s)[0] if settings().scheduler_v2_enabled else None
    for worker in workers:
        active = s.scalar(
            select(func.count())
            .select_from(Work)
            .where(Work.worker_id == worker.id, Work.status.in_(["leased", "running"]))
        )
        candidates = list(
            s.scalars(
                select(Work)
                .join(Job)
                .join(ModelPrice, Work.price_id == ModelPrice.id)
                .join(ModelVersion, ModelPrice.model_version_id == ModelVersion.id)
                .where(
                    Work.status == "queued",
                    Work.eligible_at <= now(),
                    Job.model == worker.model,
                    Job.cancel.is_(False),
                    Work.tenant_id.in_(tenants),
                    ModelVersion.repo == worker.repo,
                    ModelVersion.revision == worker.revision,
                    ModelVersion.tokenizer_revision == worker.tokenizer_revision,
                    ModelVersion.execution_mode == worker.execution_mode,
                )
                .with_for_update(of=Work, skip_locked=True)
            )
        )
        # Deficit/served counters per tenant, priority weight and age prevent starvation.
        loads = {
            tid: s.scalar(
                select(func.count())
                .select_from(Work)
                .where(Work.tenant_id == tid, Work.status.in_(["leased", "running"]))
            )
            for tid in tenants
        }
        served = {
            tid: s.scalar(
                select(func.count())
                .select_from(Work)
                .where(
                    Work.tenant_id == tid,
                    or_(Work.started_at >= now() - timedelta(minutes=5), Work.status.in_(["leased", "running"])),
                )
            )
            for tid in tenants
        }
        from packages.common.scheduling import available_limit, AdaptiveDispatch, DispatchPolicy
        effective_capacity = available_limit(worker, now())
        if settings().adaptive_dispatch_enabled:
            effective_capacity = AdaptiveDispatch.update(worker, now(), bool(candidates))
        while candidates and active < effective_capacity:
            candidates = [r for r in candidates if loads[r.tenant_id] < settings().max_inflight]
            if not candidates:
                break

            def score(r):
                j = s.get(Job, r.job_id)
                age = (now() - j.created_at).total_seconds()
                if estimator is not None:
                    return DispatchPolicy.score(served[r.tenant_id], j.tier, age, (j.target - now()).total_seconds(),
                                                estimator.duration(r.prompt_tokens, r.max_output), r.ordinal)
                return (
                    served[r.tenant_id] / (4 if j.tier == "standard" or age >= 300 else 1) - age / 60,
                    j.target,
                    r.ordinal,
                )

            r = min(candidates, key=score)
            candidates.remove(r)
            r.status = "leased"
            r.first_dispatched_at = r.first_dispatched_at or now()
            r.worker_id = worker.id
            r.worker_generation = worker.generation
            r.epoch += 1
            r.attempts += 1
            r.lease_until = now() + timedelta(seconds=settings().lease_seconds)
            loads[r.tenant_id] += 1
            served[r.tenant_id] += 1
            active += 1


def reconcile(s):
    failures = []
    for w in s.scalars(select(Wallet)):
        a, b, debt = s.execute(
            select(
                func.coalesce(func.sum(Ledger.available_delta), 0),
                func.coalesce(func.sum(Ledger.reserved_delta), 0),
                func.coalesce(func.sum(Ledger.debt_delta), 0),
            ).where(Ledger.tenant_id == w.tenant_id)
        ).one()
        outstanding = s.scalar(
            select(func.coalesce(func.sum(Work.reservation - Work.captured - Work.released), 0)).where(
                Work.tenant_id == w.tenant_id
            )
        )
        captured = s.scalar(select(func.coalesce(func.sum(Work.captured), 0)).where(Work.tenant_id == w.tenant_id))
        usage = s.scalar(
            select(func.coalesce(func.sum(Usage.charge), 0))
            .join(Work, Usage.request_id == Work.id)
            .where(Work.tenant_id == w.tenant_id)
        )
        if (a, b, debt) != (w.available, w.reserved, w.debt) or outstanding != w.reserved or captured != usage:
            failures.append(w.tenant_id)
    return failures


def purge(s):
    cutoff = now() - timedelta(days=settings().retention_days)
    for r in s.scalars(
        select(Work)
        .where(
            or_(Work.completed_at < cutoff, and_(Work.status == "billing_pending", Work.started_at < cutoff)),
            Work.payload.is_not(None),
        )
        .with_for_update(skip_locked=True)
    ):
        r.payload = None
        r.output = None
        s.add(Audit(kind="content_purged", reference=r.id))


def reconcile_request(s, rid, input_tokens, output_tokens, reference, release_only=False):
    tenant = s.scalar(select(Work.tenant_id).where(Work.id == rid))
    if tenant is None:
        raise Problem(404, "not_found")
    lock_wallet(s, tenant)
    r = s.scalar(select(Work).where(Work.id == rid).with_for_update())
    if r.status != "billing_pending":
        raise Problem(409, "not_billing_pending")
    if not reference:
        raise ValueError("Reviewed reconciliation reference required")
    if release_only:
        terminal(s, r, "failed", "unverifiable_usage_released")
        s.add(Audit(kind="billing_reconciled_release", reference=f"{r.id}:{reference}"))
        return
    if input_tokens < 0 or output_tokens < 0 or output_tokens > r.max_output:
        raise ValueError("Invalid engine usage")
    if r.output is None or decrypt(r.output) is None:
        raise ValueError("No durable output to bill")
    actual = cost(input_tokens, r.input_rate) + cost(output_tokens, r.output_rate)
    charge = min(actual, r.reservation)
    settle(s, r, charge)
    r.input_tokens = input_tokens
    r.output_tokens = output_tokens
    r.status = "succeeded"
    r.error = None
    r.completed_at = now()
    r.finish_reason = "reconciled"
    r.late = now() > s.get(Job, r.job_id).target
    s.add(Usage(request_id=r.id, input_tokens=input_tokens, output_tokens=output_tokens, charge=charge))
    s.add(Audit(kind="billing_reconciled", reference=f"{r.id}:{reference}:actual={actual}:charged={charge}"))
    attempt = s.get(ExecutionAttempt, (r.id, r.epoch))
    if attempt:
        attempt.outcome = "succeeded_reconciled"
        attempt.input_tokens, attempt.output_tokens = input_tokens, output_tokens
