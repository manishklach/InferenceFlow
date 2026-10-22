from sqlalchemy import select, text
from packages.common.db import Payment, Tenant, Audit, Work
from packages.common.service import lock_wallet, post, terminal, TERMINAL, Problem


def handle_event(s, event):
    if event.get("livemode"):
        raise Problem(400, "live_payment_rejected")
    obj = event["data"]["object"]
    kind = event["type"]
    s.execute(text("SELECT pg_advisory_xact_lock(1982011)"))
    if s.get(Audit, event["id"]):
        return
    if kind in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        if obj.get("payment_status") != "paid":
            return
        if obj.get("currency") != "usd" or obj.get("amount_total") not in (1000, 2500, 10000):
            raise Problem(400, "invalid_payment")
        tid = obj.get("client_reference_id")
        intent = obj.get("payment_intent")
        if not tid or not intent or not s.get(Tenant, tid):
            raise Problem(400, "unknown_payment")
        w = lock_wallet(s, tid)
        if not s.scalar(select(Payment).where(Payment.intent == intent)):
            amount = obj["amount_total"] * 10000
            s.add(Payment(id=obj["id"], tenant_id=tid, intent=intent, amount=amount))
            post(s, w, "stripe:" + intent, "topup", amount, 0)
    elif kind in ("charge.refunded", "charge.dispute.created"):
        p = s.scalar(select(Payment).where(Payment.intent == obj.get("payment_intent")))
        if not p:
            raise Problem(409, "payment_not_yet_recorded")
        w = lock_wallet(s, p.tenant_id)
        tenant = s.get(Tenant, p.tenant_id)
        tenant.frozen = True
        # Freeze is immediate, including running work: discard later completions without charging.
        for request in s.scalars(
            select(Work).where(Work.tenant_id == p.tenant_id, Work.status.not_in(TERMINAL)).with_for_update()
        ):
            request.epoch += 1
            terminal(s, request, "canceled", "funding_reversed")
        s.flush()
        target = p.amount if kind == "charge.dispute.created" else min(p.amount, obj.get("amount_refunded", 0) * 10000)
        delta = max(0, target - p.reversed_amount)
        debit = min(w.available, delta)
        post(s, w, "reversal:" + event["id"], "reversal", -debit, 0, debt=delta - debit)
        # Liability is journaled above; audit preserves the operator-facing payment reference.
        if debit < delta:
            s.add(Audit(kind="reversal_debt", reference=f"{p.id}:{delta - debit}"))
        p.reversed_amount += delta
    s.add(Audit(id=event["id"], kind="stripe_event", reference=kind))
