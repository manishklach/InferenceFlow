"""Verify and retain customer receipts against this stage's successful outputs."""
import json
import re
import httpx
from packages.common.receipt_format import verify_receipt, text_sha256
from scripts.experiment_http import get
from scripts.staging_supervisor import private_write


def collect(connection, directory):
    jobs = json.loads((directory / "jobs.json").read_text())
    results = json.loads((directory / "results.json").read_text())
    expected = {row["custom_id"]: row for row in results}
    if len(expected) != len(results):
        raise RuntimeError("Duplicate output identity")
    envelopes, seen = [], set()
    with httpx.Client(base_url=connection["CONTROL_PLANE_URL"], timeout=10, trust_env=False,
                      headers={"Authorization": "Bearer "+connection["INFERENCEFLOW_API_KEY"]}) as client:
        for job in jobs:
            if not re.fullmatch(r"job_[A-Za-z0-9_-]+", job["id"]):
                raise ValueError("Invalid job identity")
            cursor = 0
            while True:
                page = get(client, "/v1/jobs/"+job["id"]+"/receipts", params={"cursor": cursor, "limit": 100}).json()
                for envelope in page["items"]:
                    receipt = envelope["receipt"]
                    custom = receipt["custom_id"]
                    output = expected.get(custom)
                    if (not verify_receipt(envelope) or custom in seen or output is None
                            or receipt["job_id"] != job["id"] or receipt["status"] != "succeeded"
                            or receipt["model"]["execution_mode"] != "vllm"
                            or not receipt["billing"]["request_settlement_reconciled"]
                            or receipt["billing"]["capture_records"] != 1 or receipt["billing"]["usage_records"] != 1
                            or receipt["billing"]["captured"] != output["charge_micro_usd"]
                            or receipt["usage"] != output["usage"]
                            or receipt["hashes"]["output_sha256"] != text_sha256(output["output_text"])):
                        raise RuntimeError("Receipt/output/settlement mismatch")
                    seen.add(custom)
                    envelopes.append(envelope)
                next_cursor = page["next_cursor"]
                if next_cursor is None:
                    break
                if not isinstance(next_cursor, int) or next_cursor <= cursor or next_cursor > len(expected):
                    raise RuntimeError("Invalid receipt pagination")
                cursor = next_cursor
    if seen != set(expected):
        raise RuntimeError("Missing customer receipts")
    private_write(directory / "receipts.json", json.dumps(envelopes))
    return len(envelopes)
