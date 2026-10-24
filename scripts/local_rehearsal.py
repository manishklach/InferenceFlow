"""Prepare and supervise an unpaid, isolated Docker/HTTPS mock rehearsal."""

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import time

from cryptography.fernet import Fernet
import httpx

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime/local-rehearsal"
COMPOSE = ["docker", "compose", "-f", str(ROOT / "infra/local-rehearsal/compose.yml")]
WORKER_FIELDS = {
    "ENVIRONMENT", "EXECUTION_MODE", "MODEL_REVISION", "WORKER_BOOTSTRAP_TOKEN",
    "WORKER_CAPACITY", "WORKER_ID", "MOCK_LATENCY_SECONDS",
}


def write_private(path, content):
    path.write_text(content, encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)


def write_env(path, values):
    if any("'" in str(value) or "\n" in str(value) or "\r" in str(value) for value in values.values()):
        raise ValueError("Unsupported environment value")
    write_private(path, "".join(f"{key}='{value}'\n" for key, value in values.items()))


def prepare():
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (RUNTIME / "private.json").exists():
        raise ValueError("Existing preparation retained; refusing credential rotation")
    if os.name == "nt":
        # whoami's CSV avoids assumptions about localized user names.
        import csv
        identity = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
                                  capture_output=True, text=True, check=True).stdout
        sid = next(csv.reader(identity.splitlines()))[1]
        subprocess.run(["icacls", str(RUNTIME), "/inheritance:r", "/grant:r",
                        f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"], check=True, capture_output=True)
    else:
        RUNTIME.chmod(0o700)
    password = secrets.token_hex(32)
    env = {
        "DATABASE_URL": f"postgresql+psycopg://if_rehearsal:{password}@postgres:5432/if_rehearsal",
        "ENVIRONMENT": "development", "EXECUTION_MODE": "mock", "MODEL_REVISION": "mock-v1",
        "SECRET_KEY": secrets.token_urlsafe(48), "CREDENTIAL_HASH_KEY": secrets.token_urlsafe(48),
        "ENCRYPTION_KEYS": json.dumps({"rehearsal": Fernet.generate_key().decode()}, separators=(",", ":")),
        "ENCRYPTION_ACTIVE_KEY": "rehearsal", "WORKER_BOOTSTRAP_TOKEN": secrets.token_urlsafe(48),
        "METRICS_TOKEN": secrets.token_urlsafe(48), "RUNPOD_API_KEY": "", "STRIPE_ENABLED": "false",
        "STRIPE_SECRET_KEY": "", "PUBLIC_BETA_ENABLED": "false", "PROVISIONING_ENABLED": "false",
        "REVIEWED_GPU_EXPERIMENT_ENABLED": "false", "SCHEDULER_V2_ENABLED": "true",
        "ADAPTIVE_DISPATCH_ENABLED": "false", "MAX_INFLIGHT": "4", "WORKER_CAPACITY": "4",
        "MOCK_LATENCY_SECONDS": "0.05", "WORKER_ID": "isolated-docker-rehearsal",
        "OIDC_ISSUER": "", "OIDC_AUDIENCE": "", "OIDC_JWKS_URL": "",
    }
    worker = {key: value for key, value in env.items() if key in WORKER_FIELDS}
    worker["CONTROL_PLANE_URL"] = "http://api:8080"
    write_env(RUNTIME / "control.env", env)
    write_env(RUNTIME / "postgres.env", {"POSTGRES_USER": "if_rehearsal", "POSTGRES_PASSWORD": password,
                                        "POSTGRES_DB": "if_rehearsal"})
    write_env(RUNTIME / "worker.env", worker)
    write_private(RUNTIME / "private.json", json.dumps({"worker_env": worker}, indent=2))
    print("Prepared ignored private configuration. Mock only; no cloud resources created.")


def docker(*args):
    return subprocess.run(COMPOSE + list(args), cwd=ROOT, capture_output=True, text=True, check=True)


def wait_https(url, process, attempts=60):
    with httpx.Client(trust_env=False, timeout=5) as client:
        for _ in range(attempts):
            if process.poll() is not None:
                raise RuntimeError("Tunnel process exited")
            try:
                response = client.get(url + "/readyz")
                response.raise_for_status()
                if response.json().get("execution_mode") != "mock":
                    raise RuntimeError("Refusing non-mock endpoint")
                return
            except httpx.HTTPError:
                time.sleep(2)
    raise RuntimeError("Public HTTPS readiness failed")


def start(cloudflared, minutes):
    binary = shutil.which(cloudflared) or (str(Path(cloudflared).resolve()) if Path(cloudflared).is_file() else None)
    if not binary:
        raise ValueError("Install cloudflared from Cloudflare's official downloads first")
    if not (RUNTIME / "private.json").exists():
        raise ValueError("Run prepare first")
    if (RUNTIME / "STOP").exists():
        raise ValueError("STOP marker exists; remove it explicitly before restarting")
    tunnel = None
    deadline = time.time() + minutes * 60
    try:
        print("Starting isolated mock containers (build output is captured).", flush=True)
        docker("up", "-d", "--build", "--wait", "postgres", "api", "scheduler")
        private = json.loads((RUNTIME / "private.json").read_text())
        if "api_key" not in private:
            # Existing development CLI; stdout contains a key, so never print it.
            seeded = docker("exec", "-T", "api", "python", "-m", "packages.common.cli", "seed",
                            "--email", "isolated-rehearsal@example.invalid", "--reference", "local-rehearsal")
            values = json.loads(seeded.stdout)
            private.update(tenant_id=values["tenant_id"], api_key=values["key"])
            write_private(RUNTIME / "private.json", json.dumps(private, indent=2))
        with (RUNTIME / "tunnel.log").open("w", encoding="utf-8") as log:
            kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            tunnel = subprocess.Popen([binary, "tunnel", "--url", "http://127.0.0.1:18084",
                                       "--no-autoupdate", "--metrics", "127.0.0.1:18085"],
                                      stdout=log, stderr=subprocess.STDOUT, **kwargs)
            for _ in range(90):
                matches = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com",
                                     (RUNTIME / "tunnel.log").read_text(errors="replace"))
                if matches:
                    url = matches[0]
                    break
                if tunnel.poll() is not None:
                    raise RuntimeError("Tunnel exited before publishing a URL")
                time.sleep(1)
            else:
                raise RuntimeError("Tunnel URL unavailable")
            wait_https(url, tunnel)
            write_private(RUNTIME / "url.txt", url)
            worker = private["worker_env"]
            worker["CONTROL_PLANE_URL"] = url
            write_env(RUNTIME / "worker.env", worker)
            docker("up", "-d", "worker")
            write_private(RUNTIME / "running.json", json.dumps({"expires_at_epoch": deadline, "mode": "mock"}))
            print("HTTPS mock rehearsal ready. URL saved privately; automatic shutdown armed.", flush=True)
            while time.time() < deadline and not (RUNTIME / "STOP").exists():
                services = docker("ps", "--status", "running", "--services").stdout.split()
                if tunnel.poll() is not None or not {"api", "postgres", "scheduler", "worker"}.issubset(services):
                    raise RuntimeError("A supervised component stopped")
                time.sleep(2)
    finally:
        if tunnel is not None and tunnel.poll() is None:
            tunnel.terminate()
            tunnel.wait(timeout=10)
        result = subprocess.run(COMPOSE + ["stop", "--timeout", "15"], capture_output=True)
        write_private(RUNTIME / "stopped.json", json.dumps({"stop_returncode": result.returncode}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "start", "stop"])
    parser.add_argument("--cloudflared", default="cloudflared")
    parser.add_argument("--minutes", type=int, default=120)
    args = parser.parse_args()
    if not 1 <= args.minutes <= 120:
        parser.error("Duration must be 1–120 minutes")
    try:
        if args.command == "prepare":
            prepare()
        elif args.command == "start":
            start(args.cloudflared, args.minutes)
        else:
            if not RUNTIME.exists():
                raise ValueError("No rehearsal has been prepared")
            write_private(RUNTIME / "STOP", "Operator requested shutdown\n")
            print("Shutdown requested; inspect stopped.json and Compose status.")
    except (ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        # Captured subprocess output can contain keys. Do not dump it on failure.
        raise SystemExit(f"Rehearsal failed: {type(exc).__name__}; no captured output printed") from None


if __name__ == "__main__":
    main()
