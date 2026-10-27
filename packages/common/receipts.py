"""Tenant-scoped, read-only execution and settlement receipts."""
from datetime import timezone
from sqlalchemy import select
from packages.common.db import Ledger, ModelPrice, ModelVersion, Usage
from packages.common.receipt_format import canonical_sha256


def stamp(value):
    return value.astimezone(timezone.utc).isoformat() if value else None


def execution_receipt(session, job, work):
    price = session.get(ModelPrice, work.price_id) if work.price_id else None
    model = session.get(ModelVersion, price.model_version_id) if price else None
    usage = session.get(Usage, work.id)
    entries = list(session.scalars(select(Ledger).where(Ledger.tenant_id == work.tenant_id,
        Ledger.source.in_([work.id+":reserve", work.id+":capture", work.id+":release"]))))
    captures = [entry for entry in entries if entry.source == work.id+":capture" and entry.kind == "capture"]
    reserves = [entry for entry in entries if entry.source == work.id+":reserve" and entry.kind == "reservation"]
    releases = [entry for entry in entries if entry.source == work.id+":release" and entry.kind == "release"]
    ledger_matches = (len(captures) == len(reserves) == len(releases) == 1
        and captures[0].reserved_delta == -work.captured and captures[0].available_delta == 0
        and reserves[0].available_delta == -work.reservation and reserves[0].reserved_delta == work.reservation
        and releases[0].available_delta == work.released and releases[0].reserved_delta == -work.released
        and all(entry.debt_delta == 0 for entry in entries)
        and work.reservation == work.captured+work.released)
    usage_matches = (usage is not None and usage.charge == work.captured
        and usage.input_tokens == work.input_tokens and usage.output_tokens == work.output_tokens
        if work.status == "succeeded" else usage is None and work.captured == 0)
    receipt = {"schema": "inferenceflow.execution-receipt.v1", "job_id": job.id, "request_id": work.id,
        "custom_id": work.custom_id, "ordinal": work.ordinal, "status": work.status,
        "model": {"public_id": job.model, "repository": model.repo if model else None,
            "revision": work.model_revision, "tokenizer_revision": model.tokenizer_revision if model else None,
            "execution_mode": model.execution_mode if model else None},
        "hashes": {"prompt_sha256": work.prompt_sha256, "payload_sha256": work.payload_sha256,
            "output_sha256": work.output_sha256},
        "usage": {"input_tokens": work.input_tokens, "output_tokens": work.output_tokens},
        "billing": {"currency": "USD", "unit": "micro_usd", "price_id": work.price_id,
            "rates_test_only": price.test_only if price else None,
            "input_per_million": work.input_rate, "output_per_million": work.output_rate,
            "reserved": work.reservation, "captured": work.captured, "released": work.released,
            "capture_records": len(captures), "usage_records": int(usage is not None),
            "request_settlement_reconciled": bool(ledger_matches and usage_matches)},
        "execution": {"attempts": work.attempts, "finish_reason": work.finish_reason, "error": work.error,
            "submitted_at": stamp(job.created_at), "completed_at": stamp(work.completed_at),
            "deadline_at": stamp(job.target), "late": work.late},
        "attestation": "operator_record_unsigned"}
    return {"receipt": receipt, "sha256": canonical_sha256(receipt)}
