"""Run inside API container after stack boot. Does not provision anything."""

import json
from packages.common.db import Session
from packages.common.service import account, new_key, lock_wallet, post, reconcile
from packages.python_sdk import InferenceFlowClient

with Session.begin() as s:
    t = account(s, "dev:developer@example.local")
    w = lock_wallet(s, t.id)
    post(s, w, "docker-demo:" + t.id, "topup", 10000000, 0)
    raw = new_key(s, t.id, "Docker smoke")["key"]
with InferenceFlowClient(raw, "http://api:8080") as client:
    job = client.create_job(
        [
            {
                "custom_id": str(i),
                "messages": [{"role": "user", "content": f"Summarize document {i}"}],
                "max_output_tokens": 128,
            }
            for i in range(100)
        ]
    )
    result = client.wait_for_job(job["id"], timeout=120)
    assert result["status"] == "succeeded", result
    assert len(client.get_results(job["id"])["items"]) == 100
    with Session.begin() as s:
        assert reconcile(s) == []
    print(
        json.dumps(
            {
                "transport": "Docker HTTP",
                "completed": result["completed"],
                "captured_micro_usd": result["captured_micro_usd"],
                "usage": result["usage"],
                "ledger_drift": 0,
            }
        )
    )
