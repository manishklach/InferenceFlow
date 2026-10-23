"""Internal GPU costs, independent of immutable customer rates and wallets."""
from decimal import Decimal, ROUND_CEILING
from sqlalchemy import select
from packages.common.db import Instance, GpuCostProfile, GpuObservation, ExecutionAttempt, Work, Audit, now


def quoted_cost(seconds, hourly_micro_usd, increment=1):
    if seconds < 0 or hourly_micro_usd < 0 or increment < 1:
        raise ValueError("Nonnegative duration/rate and positive billing increment required")
    ticks = (Decimal(str(seconds)) / increment).to_integral_value(rounding=ROUND_CEILING)
    return int((ticks * increment * hourly_micro_usd / 3600).to_integral_value(rounding=ROUND_CEILING))


def unit_economics(cost, input_tokens, output_tokens, revenue):
    if min(cost, input_tokens, output_tokens, revenue) < 0:
        raise ValueError("Nonnegative economics inputs required")
    total = input_tokens + output_tokens
    return {"input_tokens": input_tokens, "output_tokens": output_tokens,
            "cost_per_million_total_tokens_micro_usd": float(Decimal(cost) * 1000000 / total) if total else None,
            "cost_per_million_output_tokens_micro_usd": float(Decimal(cost) * 1000000 / output_tokens) if output_tokens else None,
            "customer_revenue_micro_usd": revenue,
            "gross_margin": float(Decimal(revenue - cost) / revenue) if revenue else None}


def record_invoice(s, instance_id, provider, gpu_type, increment, amount, reference, through, startup=None):
    i = s.scalar(select(Instance).where(Instance.id == instance_id).with_for_update())
    p = s.get(GpuCostProfile, instance_id)
    startup = startup if startup is not None else (p.startup_seconds if p else 0)
    if i is None or not reference or amount < 0 or increment < 1 or startup < 0:
        raise ValueError("Known instance, provider billing reference and nonnegative values required")
    if through < i.created_at or through > (i.terminated_at or now()):
        raise ValueError("Invoice coverage must fall within recorded lifetime")
    if p and p.invoiced_through and through < p.invoiced_through:
        raise ValueError("Cumulative invoice coverage cannot move backwards")
    if p and p.invoice_reference == reference:
        if (p.invoiced_micro_usd, p.invoiced_through, p.provider, p.gpu_type, p.billing_increment_seconds, p.startup_seconds) != (amount, through, provider, gpu_type, increment, startup):
            raise ValueError("Invoice reference conflict")
        return
    if not p:
        p = GpuCostProfile(instance_id=instance_id)
        s.add(p)
    p.provider, p.gpu_type, p.billing_increment_seconds = provider, gpu_type, increment
    p.invoiced_micro_usd, p.invoice_reference, p.invoiced_through = amount, reference, through
    p.startup_seconds = startup
    s.add(Audit(kind="gpu_invoice_recorded", reference=f"{instance_id}:{reference}:{amount}:{through.isoformat()}"))


def economics_report(s, stamp=None):
    stamp = stamp or now()
    profiles = {p.instance_id: p for p in s.scalars(select(GpuCostProfile))}
    observations = list(s.scalars(select(GpuObservation)))
    attempts = list(s.scalars(select(ExecutionAttempt)))
    charges = {r.id: r.captured for r in s.scalars(select(Work).where(Work.status == "succeeded"))}
    rows = []
    for i in s.scalars(select(Instance).order_by(Instance.id)):
        p = profiles.get(i.id)
        increment = p.billing_increment_seconds if p else 60
        elapsed = max(0, ((i.terminated_at or stamp) - i.created_at).total_seconds())
        estimated = quoted_cost(elapsed, i.hourly_micro_usd, increment)
        a = [a for a in attempts if a.instance_id == i.id and a.outcome in {"succeeded", "succeeded_reconciled"}]
        observed = [o for o in observations if o.instance_id == i.id]
        inp, out = sum(a.input_tokens for a in a), sum(a.output_tokens for a in a)
        revenue = sum(charges.get(a.request_id, 0) for a in a)
        invoice_attempts = [x for x in a if p and p.invoiced_through and x.ended_at <= p.invoiced_through]
        invoice_economics = unit_economics(p.invoiced_micro_usd, sum(x.input_tokens for x in invoice_attempts),
                                          sum(x.output_tokens for x in invoice_attempts),
                                          sum(charges.get(x.request_id, 0) for x in invoice_attempts)) if p and p.invoiced_micro_usd is not None else None
        rows.append({"instance_id": i.id, "provider": p.provider if p else "unrecorded",
                     "gpu_type": p.gpu_type if p else "unrecorded", "hourly_quote_micro_usd": i.hourly_micro_usd,
                     "started_at": i.created_at.isoformat(), "shutdown_at": i.terminated_at.isoformat() if i.terminated_at else None,
                     "startup_seconds": p.startup_seconds if p else None,
                     "model_loading_seconds": None, "elapsed_seconds": elapsed,
                     "observed_active_seconds": sum(o.active_seconds for o in observed),
                     "observed_idle_seconds": sum(o.idle_seconds for o in observed),
                     "unobserved_seconds": max(0, elapsed - sum(o.active_seconds + o.idle_seconds for o in observed)),
                     "estimated_cost_micro_usd": estimated,
                     "provider_invoiced_micro_usd": p.invoiced_micro_usd if p else None,
                     "invoice_reference": p.invoice_reference if p else None,
                     "provider_invoice_economics": invoice_economics,
                     "invoiced_through": p.invoiced_through.isoformat() if p and p.invoiced_through else None,
                     "measurement_modes": sorted({o.mode for o in observed} | {x.mode for x in a}),
                     **unit_economics(estimated, inp, out, revenue)})
    from packages.common.db import Worker
    for row in rows:
        loads = [w.model_loading_seconds for w in s.scalars(select(Worker).where(Worker.provider_instance_id == row["instance_id"]))]
        row["model_loading_seconds"] = sum(loads) if any(loads) else None
    estimated_total = sum(r["estimated_cost_micro_usd"] for r in rows)
    return {"cost_basis": "estimated_quote_not_provider_invoice", "activity_basis": "sampled_heartbeat_proxy_not_gpu_active_time",
            "instances": rows, "estimated_cost_micro_usd": estimated_total,
            "provider_invoiced_micro_usd": sum(p.invoiced_micro_usd or 0 for p in profiles.values()) if profiles else None,
            "unattributed_successful_requests": sum(a.outcome in {"succeeded", "succeeded_reconciled"} and a.instance_id not in {r["instance_id"] for r in rows} for a in attempts),
            **unit_economics(estimated_total, sum(r["input_tokens"] for r in rows), sum(r["output_tokens"] for r in rows),
                             sum(r["customer_revenue_micro_usd"] for r in rows))}


def record_attachment(s, instance_id, provider, gpu_type, hourly, started, increment=60, startup=0):
    if not instance_id or not provider or not gpu_type or hourly < 0 or increment < 1 or startup < 0 or started > now():
        raise ValueError("Valid manual attachment metadata required")
    if s.get(Instance, instance_id):
        raise ValueError("Instance already tracked; do not reset its cost clock")
    s.add(Instance(id=instance_id, source="manual:" + instance_id, hourly_micro_usd=hourly, created_at=started))
    s.flush()
    s.add(GpuCostProfile(instance_id=instance_id, provider=provider, gpu_type=gpu_type,
                         billing_increment_seconds=increment, startup_seconds=startup))
    s.add(Audit(kind="manual_gpu_attached", reference=instance_id))
