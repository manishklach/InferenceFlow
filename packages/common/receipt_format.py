"""Versioned receipt serialization. Hash integrity is not an operator signature."""
import hashlib
import hmac
import json


def canonical_sha256(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def text_sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_receipt(envelope):
    try:
        return (envelope["receipt"]["schema"] == "inferenceflow.execution-receipt.v1"
                and hmac.compare_digest(canonical_sha256(envelope["receipt"]), envelope["sha256"]))
    except (KeyError, TypeError, ValueError):
        return False
