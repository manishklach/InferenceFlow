"""Bounded private real-mode CPU control plane. No GPU/provider API calls."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import re
import signal
import subprocess
import sys
import time

import httpx

from scripts import github_staging_host as host
from scripts.experiment_connection import seal_connection
from scripts.sealed_evidence import seal
from scripts.staging_supervisor import monitor, private_write

REVISION = "1cfa9a7208912126459214e8b04321603b3df60c"
COMPOSE = host.COMPOSE + ["-f", str(host.ROOT / "infra/github-staging/real.yml")]
RUNTIME = host.RUNTIME


def real_configuration(oidc):
    values, postgres = host.configuration(oidc)
    values.update(EXECUTION_MODE="vllm", MODEL_REVISION=REVISION, MODEL_REPO="Qwen/Qwen3-4B",
                  REVIEWED_GPU_EXPERIMENT_ENABLED="true", SCHEDULER_V2_ENABLED="false",
                  ADAPTIVE_DISPATCH_ENABLED="false", ESTIMATOR_CALIBRATED="false")
    return values, postgres


def seed_real():
    # This entrypoint runs only inside the isolated API container, not on a tenant request.
    from packages.common.config import settings
    from packages.common.db import Session, Tenant
    from packages.common.service import account, lock_wallet, new_key, post
    from sqlalchemy import select
    cfg = settings()
    identity = os.environ.get("HOSTED_REAL_IDENTITY", "")
    if (not re.fullmatch(r"[0-9]+-[0-9]+", identity) or cfg.environment != "staging"
            or cfg.execution_mode != "vllm" or cfg.model_revision != REVISION
            or not cfg.reviewed_gpu_experiment_enabled or cfg.public_beta_enabled
            or cfg.provisioning_enabled or cfg.stripe_enabled or cfg.runpod_api_key):
        raise RuntimeError("Isolated reviewed real-mode control plane required")
    with Session.begin() as session:
        subject = "github-disposable-real:"+identity
        if session.scalar(select(Tenant.id).where(Tenant.subject == subject)):
            raise RuntimeError("Refuse to reseed an existing tenant")
        tenant = account(session, subject)
        post(session, lock_wallet(session, tenant.id), "github-real-test-credit:"+identity, "topup", 10_000_000, 0)
        print(json.dumps({"key": new_key(session, tenant.id, "private GPU experiment")["key"]}))


def serve():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise RuntimeError("Reviewed main-branch GitHub runner required")
    host.COMPOSE = COMPOSE
    RUNTIME.mkdir(parents=True, exist_ok=False, mode=0o700)
    private_write(RUNTIME / "host.pid", str(os.getpid()))
    public_pem = os.environ["EVIDENCE_RECIPIENT_PUBLIC_KEY"].encode()
    seal(b"recipient-preflight", public_pem)
    deadline = time.monotonic()+150*60
    expires = datetime.now(timezone.utc)+timedelta(minutes=150)
    stopping = False
    tunnel = None
    database_started = False

    def signal_stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, signal_stop)
    signal.signal(signal.SIGINT, signal_stop)
    try:
        issuer = os.environ["AUTH0_STAGING_ISSUER"].rstrip("/")+"/"
        if not re.fullmatch(r"https://[a-z0-9-]+\.(?:us\.|eu\.|au\.)?auth0\.com/", issuer):
            raise RuntimeError("Existing Auth0 tenant required")
        with httpx.Client(trust_env=False, timeout=15) as client:
            response = client.get(issuer+".well-known/openid-configuration")
            response.raise_for_status()
            metadata = response.json()
        if metadata["issuer"] != issuer:
            raise RuntimeError("Issuer mismatch")
        values, postgres = real_configuration({"OIDC_ISSUER": issuer,
            "OIDC_CLIENT_ID": os.environ["AUTH0_STAGING_CLIENT_ID"],
            "OIDC_CLIENT_SECRET": os.environ["AUTH0_STAGING_CLIENT_SECRET"],
            "OIDC_AUDIENCE": os.environ["AUTH0_STAGING_AUDIENCE"],
            "OIDC_JWKS_URL": metadata["jwks_uri"], "OIDC_AUTHORIZATION_URL": metadata["authorization_endpoint"],
            "OIDC_TOKEN_URL": metadata["token_endpoint"]})
        host.write_env(RUNTIME / "control.env", values)
        host.write_env(RUNTIME / "postgres.env", postgres)
        # Compose parses the unused worker service's env file, but never starts it.
        host.write_env(RUNTIME / "worker.env", {"EXECUTION_MODE": "mock"})
        subprocess.run(["docker", "build", "-f", str(host.ROOT / "infra/Dockerfile"), "-t",
                        "inferenceflow-control:github-staging", str(host.ROOT)], capture_output=True,
                       text=True, timeout=300, check=True)
        host.docker("up", "-d", "--build", "--wait", "postgres", "api", "scheduler")
        database_started = True
        with (RUNTIME / "tunnel.log").open("w", encoding="utf-8") as log:
            tunnel = subprocess.Popen([str(host.ROOT / ".runtime/cloudflared"), "tunnel", "--url",
                                       "http://127.0.0.1:18086", "--no-autoupdate"], stdout=log,
                                      stderr=subprocess.STDOUT)
            for _ in range(90):
                matches = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com",
                                     (RUNTIME / "tunnel.log").read_text(errors="replace"))
                if matches:
                    url = matches[0]
                    break
                if tunnel.poll() is not None:
                    raise RuntimeError("Tunnel exited")
                time.sleep(1)
            else:
                raise RuntimeError("Tunnel URL unavailable")
            values.update(OIDC_REDIRECT_URI=url+"/auth/oidc/callback", DASHBOARD_URL=url+"/healthz")
            host.write_env(RUNTIME / "control.env", values)
            host.docker("up", "-d", "--wait", "api", "scheduler")
            with httpx.Client(trust_env=False, timeout=10) as client:
                for _ in range(60):
                    try:
                        ready = client.get(url+"/readyz")
                        ready.raise_for_status()
                        if ready.json().get("execution_mode") != "vllm":
                            raise RuntimeError("Real-mode readiness required")
                        break
                    except httpx.HTTPError:
                        time.sleep(2)
                else:
                    raise RuntimeError("HTTPS readiness failed")
                if client.get(url+"/v1/wallet").status_code != 401:
                    raise RuntimeError("Anonymous wallet boundary failed")
            identity = os.environ["GITHUB_RUN_ID"]+"-"+os.environ["GITHUB_RUN_ATTEMPT"]
            seeded = json.loads(host.docker("exec", "-T", "-e", "HOSTED_REAL_IDENTITY="+identity, "api",
                                            "python", "-m", "scripts.github_real_host", "seed").stdout)
            private_write(RUNTIME / "connection.enc.json", seal_connection(url, values["WORKER_BOOTSTRAP_TOKEN"],
                          values["METRICS_TOKEN"], seeded["key"], public_pem).decode())
            private_write(RUNTIME / "real-ready.json", json.dumps({"endpoint": url, "execution_mode": "vllm",
                          "expires_at": expires.isoformat(), "gpu_created": False, "worker_ready": False,
                          "owner_login_verified": False}))
            monitor(COMPOSE, RUNTIME, deadline, {"postgres", "api", "scheduler"}, RUNTIME / "STOP",
                    stopped=lambda: stopping or tunnel.poll() is not None)
    except Exception as exc:
        private_write(RUNTIME / "host-error.json", json.dumps({"error_type": type(exc).__name__}))
        raise SystemExit("Real control host failed; no credentials printed") from None
    finally:
        if database_started:
            try:
                dump = host.docker("exec", "-T", "postgres", "pg_dump", "-U", "if_hosted_staging",
                                   "--no-owner", "--no-acl", "if_hosted_staging").stdout
                private_write(RUNTIME / "final-evidence.enc.json", seal(json.dumps({"kind": "real-control-db",
                              "database_sql": dump, "run_id": os.environ["GITHUB_RUN_ID"]}).encode(), public_pem).decode())
            except Exception as exc:
                private_write(RUNTIME / "export-error.json", json.dumps({"error_type": type(exc).__name__}))
        if tunnel is not None and tunnel.poll() is None:
            tunnel.terminate()
        result = subprocess.run(COMPOSE+["down", "--volumes", "--timeout", "15"], capture_output=True,
                                text=True, timeout=60, check=False)
        private_write(RUNTIME / "real-stopped.json", json.dumps({"stop_returncode": result.returncode,
                       "export_sealed": (RUNTIME / "final-evidence.enc.json").exists()}))


def start():
    # Linux GitHub runner only. Detached child stays supervised by the job's hold/finalizer steps.
    log_path = host.ROOT / ".runtime/real-host.log"
    with log_path.open("w", encoding="utf-8") as log:
        child = subprocess.Popen([sys.executable, "-m", "scripts.github_real_host", "serve"],
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(600):
        ready = RUNTIME / "real-ready.json"
        if ready.exists():
            print(ready.read_text(), flush=True)
            return
        if child.poll() is not None:
            raise RuntimeError("Real host failed before readiness; private diagnostics retained")
        time.sleep(1)
    raise RuntimeError("Real host startup timed out")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "serve", "wait", "stop", "seed"])
    action = parser.parse_args().action
    if action == "serve":
        serve()
    elif action == "start":
        start()
    elif action == "seed":
        seed_real()
    elif action == "stop":
        if RUNTIME.exists():
            private_write(RUNTIME / "STOP", "Operator/job requested shutdown")
            for _ in range(90):
                if (RUNTIME / "real-stopped.json").exists():
                    return
                time.sleep(1)
    else:
        for _ in range(150*30):
            if (RUNTIME / "real-stopped.json").exists():
                stopped = json.loads((RUNTIME / "real-stopped.json").read_text())
                if (RUNTIME / "host-error.json").exists() or not stopped["export_sealed"] or stopped["stop_returncode"]:
                    raise RuntimeError("Host stopped without clean export/teardown")
                return
            time.sleep(2)
        raise RuntimeError("Host lifetime exhausted; finalizer required")


if __name__ == "__main__":
    main()
