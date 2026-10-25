"""Temporary no-GPU Auth0 staging rehearsal on a reviewed GitHub runner."""

import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import time

from cryptography.fernet import Fernet
import httpx

from packages.common.config import Settings
from scripts.staging_supervisor import monitor, private_write

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime/github-staging"
COMPOSE = ["docker", "compose", "-f", str(ROOT / "infra/github-staging/compose.yml")]


def write_env(path, values):
    if any("'" in str(value) or "\n" in str(value) or "\r" in str(value) for value in values.values()):
        raise ValueError("Unsupported environment value")
    private_write(path, "".join(f"{key}='{value}'\n" for key, value in values.items()))


def configuration(oidc):
    password = secrets.token_hex(32)
    values = {
        "DATABASE_URL": f"postgresql+psycopg://if_hosted_staging:{password}@postgres:5432/if_hosted_staging",
        "ENVIRONMENT": "staging", "EXECUTION_MODE": "mock", "MODEL_REVISION": "mock-v1",
        "SECRET_KEY": secrets.token_urlsafe(48), "CREDENTIAL_HASH_KEY": secrets.token_urlsafe(48),
        "ENCRYPTION_KEYS": json.dumps({"hosted": Fernet.generate_key().decode()}, separators=(",", ":")),
        "ENCRYPTION_ACTIVE_KEY": "hosted", "WORKER_BOOTSTRAP_TOKEN": secrets.token_urlsafe(48),
        "METRICS_TOKEN": secrets.token_urlsafe(48), "RUNPOD_API_KEY": "", "STRIPE_ENABLED": "false",
        "STRIPE_SECRET_KEY": "", "PUBLIC_BETA_ENABLED": "false", "PROVISIONING_ENABLED": "false",
        "REVIEWED_GPU_EXPERIMENT_ENABLED": "false", "SCHEDULER_V2_ENABLED": "true",
        "ADAPTIVE_DISPATCH_ENABLED": "false", "MAX_INFLIGHT": "4", "WORKER_CAPACITY": "4",
        "OIDC_REDIRECT_URI": "https://not-registered.invalid/auth/oidc/callback",
        "DASHBOARD_URL": "https://not-registered.invalid/healthz", **oidc,
    }
    typed = {key.lower(): value for key, value in values.items()}
    typed["encryption_keys"] = json.loads(values["ENCRYPTION_KEYS"])
    Settings(_env_file=None, **typed).validate_runtime()  # type: ignore[call-arg]
    return values, {"POSTGRES_USER": "if_hosted_staging", "POSTGRES_PASSWORD": password,
                    "POSTGRES_DB": "if_hosted_staging"}


def docker(*args):
    result = subprocess.run(COMPOSE + list(args), capture_output=True, text=True, timeout=300, check=False)
    if result.returncode:
        private_write(RUNTIME / f"docker-failure-{time.time_ns()}.txt", result.stderr)
        raise RuntimeError("Compose failed; private diagnostics retained on runner")
    return result


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise SystemExit("Reviewed main-branch GitHub runner required")
    RUNTIME.mkdir(parents=True, exist_ok=False, mode=0o700)
    deadline = time.monotonic()+120*60
    stopping = False

    def stop_signal(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    tunnel = None
    try:
        issuer = os.environ["AUTH0_STAGING_ISSUER"].rstrip("/")+"/"
        if not re.fullmatch(r"https://[a-z0-9-]+\.(?:us\.|eu\.|au\.)?auth0\.com/", issuer):
            raise RuntimeError("Expected the existing HTTPS Auth0 tenant")
        with httpx.Client(trust_env=False, timeout=15) as client:
            discovery = client.get(issuer+".well-known/openid-configuration")
            discovery.raise_for_status()
            metadata = discovery.json()
        if metadata["issuer"] != issuer:
            raise RuntimeError("OIDC issuer mismatch")
        oidc = {"OIDC_ISSUER": issuer, "OIDC_AUDIENCE": os.environ["AUTH0_STAGING_AUDIENCE"],
                "OIDC_CLIENT_ID": os.environ["AUTH0_STAGING_CLIENT_ID"],
                "OIDC_CLIENT_SECRET": os.environ["AUTH0_STAGING_CLIENT_SECRET"],
                "OIDC_JWKS_URL": metadata["jwks_uri"], "OIDC_AUTHORIZATION_URL": metadata["authorization_endpoint"],
                "OIDC_TOKEN_URL": metadata["token_endpoint"]}
        values, postgres = configuration(oidc)
        for key in ("SECRET_KEY", "CREDENTIAL_HASH_KEY", "WORKER_BOOTSTRAP_TOKEN", "METRICS_TOKEN"):
            print("::add-mask::"+values[key], flush=True)
        print("::add-mask::"+postgres["POSTGRES_PASSWORD"], flush=True)
        write_env(RUNTIME / "control.env", values)
        write_env(RUNTIME / "postgres.env", postgres)
        worker = {key: values[key] for key in ("ENVIRONMENT", "EXECUTION_MODE", "MODEL_REVISION",
                                               "WORKER_BOOTSTRAP_TOKEN", "WORKER_CAPACITY")}
        worker.update(CONTROL_PLANE_URL="http://api:8080", WORKER_ID="github-mock-rehearsal")
        write_env(RUNTIME / "worker.env", worker)
        docker("up", "-d", "--build", "--wait", "postgres", "api", "scheduler")
        with (RUNTIME / "tunnel.log").open("w", encoding="utf-8") as log:
            tunnel = subprocess.Popen([str(ROOT / ".runtime/cloudflared"), "tunnel", "--url",
                                       "http://127.0.0.1:18086", "--no-autoupdate"],
                                      stdout=log, stderr=subprocess.STDOUT)
            for _ in range(90):
                matches = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com",
                                     (RUNTIME / "tunnel.log").read_text(errors="replace"))
                if matches:
                    url = matches[0]
                    break
                if stopping or tunnel.poll() is not None:
                    raise RuntimeError("Tunnel stopped")
                time.sleep(1)
            else:
                raise RuntimeError("Tunnel URL unavailable")
            values.update(OIDC_REDIRECT_URI=url+"/auth/oidc/callback", DASHBOARD_URL=url+"/healthz")
            write_env(RUNTIME / "control.env", values)
            docker("up", "-d", "--wait", "api", "scheduler")
            # Staging workers require HTTPS even when worker and API share a runner.
            worker["CONTROL_PLANE_URL"] = url
            write_env(RUNTIME / "worker.env", worker)
            docker("up", "-d", "worker")
            with httpx.Client(trust_env=False, timeout=10) as client:
                for _ in range(60):
                    try:
                        ready = client.get(url+"/readyz")
                        ready.raise_for_status()
                        if ready.json().get("execution_mode") != "mock":
                            raise RuntimeError("No-GPU rehearsal must remain mock")
                        break
                    except httpx.HTTPError:
                        time.sleep(2)
                else:
                    raise RuntimeError("HTTPS readiness failed")
                if client.get(url+"/v1/wallet").status_code not in (401, 403):
                    raise RuntimeError("Anonymous wallet access was not rejected")
                if client.post(url+"/auth/login", json={"email": "test@example.invalid"}).status_code < 400:
                    raise RuntimeError("Development login must remain disabled")
            with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
                summary.write("## No-GPU staging rehearsal\n\nHTTPS ready in mock mode; anonymous wallet "
                              "and development login rejected. Owner login and mock execution remain unverified.\n\n"
                              f"Endpoint: {url}\n\nExact callback awaiting owner approval: "
                              f"{url}/auth/oidc/callback\n\n"
                              "No GPU provisioned; no RunPod key on this runner. Session stops within 120 minutes.\n")
            print(json.dumps({"status": "https_mock_ready_owner_login_unverified", "endpoint": url,
                              "callback_awaiting_approval": url+"/auth/oidc/callback", "gpu_created": False}), flush=True)

            def tunnel_stopped():
                return stopping or tunnel.poll() is not None

            monitor(COMPOSE, RUNTIME, deadline, {"postgres", "api", "scheduler", "worker"},
                    RUNTIME / "STOP", stopped=tunnel_stopped)
    except Exception:
        raise SystemExit("Hosted rehearsal stopped; no private configuration or provider responses printed") from None
    finally:
        if tunnel is not None and tunnel.poll() is None:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=10)
            except subprocess.TimeoutExpired:
                tunnel.kill()
        # Only the newly isolated, disposable rehearsal database is removed.
        result = subprocess.run(COMPOSE+["down", "--volumes", "--timeout", "15"],
                                capture_output=True, text=True, timeout=60, check=False)
        private_write(RUNTIME / "stopped.json", json.dumps({"stop_returncode": result.returncode,
                                                          "mode": "mock", "gpu_created": False}))


if __name__ == "__main__":
    main()
