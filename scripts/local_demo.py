"""Real HTTP/process smoke test. Uses local Postgres, never GPU/payment provider APIs."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from packages.common.config import settings
from packages.common.db import Session
from packages.common.service import account, new_key, lock_wallet, post, reconcile
from packages.python_sdk import InferenceFlowClient

root = Path(__file__).resolve().parents[1]
runtime = root / ".runtime"
runtime.mkdir(exist_ok=True)
if settings().environment != "development" or settings().execution_mode != "mock":
    raise SystemExit("Local development mock only")
processes = []
logs = []
try:
    commands = [
        [sys.executable, "-m", "uvicorn", "apps.api.main:app", "--host", "127.0.0.1", "--port", "8080"],
        [sys.executable, "-m", "apps.scheduler.main"],
        [sys.executable, "-m", "apps.worker.main"],
    ]
    for idx, command in enumerate(commands):
        log = open(runtime / f"service-{idx}.log", "w")
        logs.append(log)
        process = subprocess.Popen(
            command,
            cwd=root,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        processes.append(process)
        if idx == 0:
            for _ in range(100):
                try:
                    if httpx.get("http://127.0.0.1:8080/readyz", timeout=1, trust_env=False).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError("API not ready")
    with Session.begin() as s:
        t = account(s, "dev:developer@example.local")
        w = lock_wallet(s, t.id)
        post(s, w, "demo-seed:" + t.id, "topup", 10000000, 0)
        raw = new_key(s, t.id, "process smoke test")["key"]
    with InferenceFlowClient(raw) as client:
        j = client.create_job(
            [
                {
                    "custom_id": str(i),
                    "messages": [{"role": "user", "content": f"Summarize document {i}"}],
                    "max_output_tokens": 128,
                }
                for i in range(100)
            ]
        )
        terminal = client.wait_for_job(j["id"], timeout=120)
        assert terminal["status"] == "succeeded", terminal
        rows = client.get_results(j["id"])["items"]
        assert len(rows) == 100 and all(x["output_text"].startswith("MOCK") for x in rows)
        assert [x["custom_id"] for x in rows] == [str(i) for i in range(100)]
        with Session.begin() as s:
            assert reconcile(s) == []
        summary = {
            "job_id": j["id"],
            "status": terminal["status"],
            "completed": terminal["completed"],
            "captured_micro_usd": terminal["captured_micro_usd"],
            "usage": terminal["usage"],
            "ledger_drift": 0,
            "transport": "HTTP",
            "processes": "API + scheduler + worker",
            "mode": "mock",
        }
        (runtime / "smoke-result.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2))
finally:
    for process in reversed(processes):
        process.terminate()
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    for log in logs:
        log.close()
