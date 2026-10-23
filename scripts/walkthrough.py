"""Reproducible, isolated mock walkthrough. Never contacts GPU or payment providers.

Run `python scripts/walkthrough.py serve` in a terminal; log in at :3001.
Use `python scripts/walkthrough.py execute` to start the worker after capturing queued work.
Use `python scripts/walkthrough.py verify` for SDK/idempotency/cancellation/billing evidence.
Ctrl+C or `python scripts/walkthrough.py stop` cleans up only this runner's processes.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid

import httpx
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime" / "walkthrough"
API = "http://127.0.0.1:8091"


def read_state():
    return json.loads((RUNTIME / "private-state.json").read_text())


def verify():
    from packages.python_sdk import InferenceFlowClient

    state = read_state()
    os.environ["DATABASE_URL"] = state["database_url"]
    with InferenceFlowClient(state["key"], API) as client:
        initial_jobs = client._call("GET", "/v1/jobs")["items"]
        assert initial_jobs and all(j["status"] == "succeeded" for j in initial_jobs), (
            "Complete the dashboard job first"
        )
        before = client.get_wallet()
        items = [
            {"custom_id": str(i), "messages": [{"role": "user", "content": prompt}], "max_output_tokens": 128}
            for i, prompt in enumerate(
                [
                    "Summarize: asynchronous execution separates admission from inference.",
                    "Extract the topic: model affinity keeps a pinned model warm.",
                    "Classify: prepaid billing captures actual completed usage.",
                ]
            )
        ]
        idem = "walkthrough-sdk-" + uuid.uuid4().hex
        job = client.create_job(items, idempotency_key=idem)
        replay = client.create_job(items, idempotency_key=idem)
        assert replay["id"] == job["id"]
        completed = client.wait_for_job(job["id"], timeout=120)
        assert completed["status"] == "succeeded"
        results = client.get_results(job["id"])
        assert len(results["items"]) == 3
        assert all(row["output_text"].startswith("MOCK") for row in results["items"])
        canceled = client.create_job(items[:1], deadline_seconds=1)
        canceled = client.cancel_job(canceled["id"])
        assert canceled["status"] == "canceled" and canceled["captured_micro_usd"] == 0
        after = client.get_wallet()
        assert before["available_micro_usd"] - after["available_micro_usd"] == completed["captured_micro_usd"]
        assert after["reserved_micro_usd"] == after["debt_micro_usd"] == 0
        ledger = client._call("GET", "/v1/wallet/transactions")["items"]
        evidence = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "mode": "mock",
            "mock_latency_seconds": 10,
            "seed_micro_usd": 10000000,
            "dashboard_jobs": initial_jobs,
            "sdk_job": completed,
            "sdk_results": results,
            "idempotent_replay_same_job": True,
            "canceled_job": canceled,
            "wallet_before_sdk": before,
            "wallet_after": after,
            "ledger": ledger,
            "real_gpu_used": False,
            "stripe_called": False,
            "provider_called": False,
        }
        from packages.common.db import Session, Work, Worker
        from packages.common.service import reconcile
        from sqlalchemy import select

        with Session.begin() as session:
            evidence["ledger_reconciliation_drift"] = reconcile(session)
            assert evidence["ledger_reconciliation_drift"] == []
            node = session.get(Worker, "walkthrough-worker")
            evidence["worker_identity"] = {
                name: getattr(node, name)
                for name in ["id", "model", "repo", "revision", "tokenizer_revision", "execution_mode", "capacity"]
            }
            evidence["request_accounting"] = [
                {
                    name: getattr(row, name)
                    for name in [
                        "custom_id",
                        "status",
                        "attempts",
                        "epoch",
                        "prompt_tokens",
                        "input_tokens",
                        "output_tokens",
                        "reservation",
                        "captured",
                        "released",
                        "worker_id",
                    ]
                }
                for row in session.scalars(
                    select(Work).where(Work.tenant_id == state["tenant_id"]).order_by(Work.job_id, Work.ordinal)
                )
            ]
        response = client.client.get("/v1/jobs/" + job["id"] + "/results.jsonl")
        response.raise_for_status()
        assert len(response.text.splitlines()) == 3
        (RUNTIME / "sdk-results.jsonl").write_text(response.text)
        (RUNTIME / "evidence.json").write_text(json.dumps(evidence, indent=2))
        print(
            json.dumps(
                {
                    "sdk_job": completed["id"],
                    "completed": completed["completed"],
                    "charge_micro_usd": completed["captured_micro_usd"],
                    "idempotent_replay_same_job": True,
                    "canceled_without_charge": True,
                    "remaining_reserved_micro_usd": after["reserved_micro_usd"],
                },
                indent=2,
            )
        )


def serve():
    load_dotenv(ROOT / ".env")
    if os.environ.get("ENVIRONMENT", "development") != "development":
        raise SystemExit("Walkthrough requires a local development configuration")
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("Configure DATABASE_URL in .env for your local PostgreSQL installation")
    base = make_url(os.environ["DATABASE_URL"])
    target = base.set(database=base.database + "_walkthrough")
    engine = create_engine(base, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        if not connection.scalar(text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": target.database}):
            name = engine.dialect.identifier_preparer.quote(target.database)
            try:
                connection.exec_driver_sql("CREATE DATABASE " + name)
            except Exception:
                raise SystemExit(
                    "Have a local database administrator create "
                    + target.database
                    + " owned by the application role and allow that role to connect. "
                    "Do not grant CREATEDB to the application role for this demo."
                ) from None
    engine.dispose()
    os.environ.update(
        DATABASE_URL=target.render_as_string(hide_password=False),
        ENVIRONMENT="development",
        EXECUTION_MODE="mock",
        MODEL_REVISION="mock-v1",
        MOCK_LATENCY_SECONDS="10",
        PROVISIONING_ENABLED="false",
        STRIPE_ENABLED="false",
        PUBLIC_BETA_ENABLED="false",
        CONTROL_PLANE_URL=API,
        WORKER_ID="walkthrough-worker",
        API_PROXY_URL=API,
        NEXT_DIST_DIR=".next-walkthrough",
        DASHBOARD_URL="http://127.0.0.1:3001",
    )
    # Fresh local secrets; only the explicitly published evidence is safe to commit.
    os.environ["WORKER_BOOTSTRAP_TOKEN"] = uuid.uuid4().hex + uuid.uuid4().hex
    os.environ["METRICS_TOKEN"] = uuid.uuid4().hex
    RUNTIME.mkdir(parents=True, exist_ok=True)
    for flag in ("start-worker", "stop"):
        (RUNTIME / flag).unlink(missing_ok=True)
    for port in (8091, 3001):
        import socket

        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit(f"Port {port} is already in use; stop the prior walkthrough first")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True)
    from packages.common.db import Session, Key
    from packages.common.service import account, new_key, lock_wallet, post

    email = "walkthrough-" + uuid.uuid4().hex[:8] + "@example.local"
    with Session.begin() as session:
        tenant = account(session, "dev:" + email)
        post(session, lock_wallet(session, tenant.id), "walkthrough-seed:" + tenant.id, "topup", 10000000, 0)
        key = new_key(session, tenant.id, "Walkthrough SDK")
    (RUNTIME / "private-state.json").write_text(
        json.dumps(
            {
                "email": email,
                "key": key["key"],
                "key_id": key["id"],
                "tenant_id": tenant.id,
                "database_url": os.environ["DATABASE_URL"],
            }
        )
    )
    processes, logs = [], []
    # Next dev regenerates these for a custom distDir; preserve existing source settings.
    dashboard = ROOT / "apps" / "dashboard"
    generated_sources = {name: (dashboard / name).read_text() for name in ("tsconfig.json", "next-env.d.ts")}

    def start(name, command, cwd=ROOT):
        log = open(RUNTIME / (name + ".log"), "w")
        logs.append(log)
        p = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
        processes.append(p)
        return p

    try:
        start(
            "api",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "apps.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8091",
                "--no-access-log",
            ],
        )
        for _ in range(100):
            try:
                if httpx.get(API + "/readyz", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError("Walkthrough API did not start; inspect .runtime/walkthrough/api.log")
        start("scheduler", [sys.executable, "-m", "apps.scheduler.main"])
        start("callbacks", [sys.executable, "-m", "apps.callbacks.main"])
        npm = shutil.which("npm")
        if not npm:
            raise RuntimeError("npm is required")
        command = [npm, "run", "dev", "--", "-H", "127.0.0.1", "-p", "3001"]
        if os.name == "nt":
            command = ["cmd.exe", "/d", "/c", *command]
        start("dashboard", command, ROOT / "apps" / "dashboard")
        for _ in range(90):
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("Walkthrough service failed during startup; inspect its runtime log")
            try:
                if httpx.get("http://127.0.0.1:3001", timeout=2, trust_env=False).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        else:
            raise RuntimeError("Walkthrough dashboard did not become ready; inspect its runtime log")
        print("Walkthrough: http://127.0.0.1:3001 | login: " + email, flush=True)
        print("Worker paused. Run: python scripts/walkthrough.py execute", flush=True)
        worker = None
        while not (RUNTIME / "stop").exists():
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("A walkthrough process exited; inspect its .runtime/walkthrough log")
            if not worker and (RUNTIME / "start-worker").exists():
                worker = start("worker", [sys.executable, "-m", "apps.worker.main"])
                print("Worker running", flush=True)
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                else:
                    os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        with Session.begin() as session:
            session.get(Key, key["id"]).revoked = True
        for log in logs:
            log.close()
        for name, original in generated_sources.items():
            path = dashboard / name
            current = path.read_text()
            if name == "tsconfig.json":
                value = json.loads(current)
                value["include"] = [v for v in value.get("include", []) if not v.startswith(".next-walkthrough/")]
                safe_to_restore = value == json.loads(original)
            else:
                safe_to_restore = current.replace(".next-walkthrough/dev/", ".next/") == original
            if safe_to_restore:
                path.write_text(original)
        print("Walkthrough processes stopped; SDK key revoked. Demo database retained.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["serve", "execute", "verify", "publish", "stop"])
    command = parser.parse_args().command
    if command == "serve":
        serve()
    elif command == "verify":
        verify()
    elif command == "publish":
        state = read_state()
        evidence = (RUNTIME / "evidence.json").read_text()
        assert state["key"] not in evidence, "Refusing to publish a credential"
        assert "database_url" not in evidence, "Refusing to publish private runtime configuration"
        destination = ROOT / "docs" / "media" / "walkthrough"
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "execution-evidence.json").write_text(evidence)
        shutil.copyfile(RUNTIME / "sdk-results.jsonl", destination / "sdk-results.jsonl")
        print("Published synthetic execution evidence; private runtime state was excluded")
    else:
        (RUNTIME / ("start-worker" if command == "execute" else "stop")).touch()
        print("Worker start requested" if command == "execute" else "Stop requested")
