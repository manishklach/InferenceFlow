# Local Docker and temporary HTTPS rehearsal

This is an unpaid **mock operator rehearsal**, not a production deployment or real-GPU validation. It runs an isolated PostgreSQL database, API, scheduler and mock worker. The existing wallet implementation is unchanged; only a fresh synthetic tenant receives development test credit. No existing database is migrated or truncated.

## Start

Install Docker Desktop, Python dependencies using `pip install -r requirements.lock` and `pip install --no-deps -e .`, and [cloudflared from Cloudflare's official downloads](https://developers.cloudflare.com/tunnel/downloads/). Do not reuse an existing application's `.env`.

From the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/local_rehearsal.py prepare
.\.venv\Scripts\python.exe scripts/local_rehearsal.py start --minutes 120
```

Keep that terminal running. On Linux/macOS use `python` from the activated virtual environment. If cloudflared is not on PATH, pass `--cloudflared <absolute-path-to-official-binary>` to `start`. The helper builds the existing locked image, migrates only its new Compose database, seeds a synthetic account using the existing development CLI, opens a Quick Tunnel, waits for public HTTPS readiness, and then starts the worker against that HTTPS URL. First-time image downloads can take several minutes. Ports 18084 and 15434 must be available on localhost; 18085 is the tunnel's localhost metrics port. Check Windows reserved port ranges if a bind is denied.

The runtime directory `.runtime/local-rehearsal/` contains the private configuration, one-time tenant API key, URL, tunnel log and supervisor expiry. The preparation helper restricts this directory to the operator and SYSTEM on Windows, or mode 0700 on Unix with mode 0600 files. It refuses to overwrite existing preparation. **Never commit or upload this directory, paste its contents into chat, or copy control-plane credentials into a GPU worker.** RunPod credentials are not needed and must not be supplied to this rehearsal.

## Access and inspect

Read `.runtime/local-rehearsal/url.txt` privately. `GET /healthz` and `GET /readyz` are public; readiness explicitly reports `mock`. Customer job/wallet routes retain the application's real tenant Bearer-key checks. Worker routes retain bootstrap/session-token checks. Development login, dashboard cookie authentication, key administration, payment/webhook configuration and API documentation routes are unavailable through this gateway. It refuses startup in real mode or with any paid-operation/beta/experiment gate enabled. It does not weaken the product's staging/OIDC validation.

```powershell
docker compose -f infra/local-rehearsal/compose.yml ps -a
docker compose -f infra/local-rehearsal/compose.yml exec api python -m packages.common.cli reconcile
```

PostgreSQL binds only to `127.0.0.1:15434` and the API to `127.0.0.1:18084`. A dedicated named volume retains only this rehearsal's data. The mock worker receives its bootstrap token, model identity, capacity and HTTPS endpoint; it receives no database, provider, signing, encryption or payment credentials. Application containers drop capabilities and prohibit privilege escalation; no Docker socket is mounted.

## Stop and retain evidence

The foreground supervisor closes its tunnel and stops its exact Compose project after at most 120 configured minutes, on a supervised component failure, or when requested:

```powershell
.\.venv\Scripts\python.exe scripts/local_rehearsal.py stop
docker compose -f infra/local-rehearsal/compose.yml ps -a
```

Check `.runtime/local-rehearsal/stopped.json` and confirm the public endpoint is unavailable. During normal running the STOP marker is checked every two seconds; containers receive a 15-second shutdown grace period. Database volume, credentials and logs are retained for audit. Restarting requires explicitly removing the STOP marker and rerunning `start`; do not regenerate credentials over a retained database. If the supervisor was forcibly killed, manually run `docker compose -f infra/local-rehearsal/compose.yml stop` and stop the exact tunnel process from that run. Do not use global Docker pruning or delete unrelated resources.

Keep the PC awake and connected. The local supervisor is **not independent GPU teardown protection** and is not a provider spending cap. [Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) have no uptime guarantee, change hostname on restart, support at most 200 concurrent in-flight requests and do not support SSE. Exposing an authenticated test API this way does not make it production ready.

## Before an approved real-GPU run

Configure genuine staging OIDC and validate the reviewed real-mode control plane, pinned tokenizer and model identity. Verify independent RunPod cleanup credentials and an armed watchdog that survives loss of this PC, refresh balance and all-in GPU/storage quotes, preserve the $10 aggregate budget reserve, and obtain explicit approval for one GPU pod. Public beta, automatic provisioning and live payments remain disabled. Do not convert the rehearsal gateway to real mode or interpret its mock throughput as GPU performance.

See [October 24 validation](validation/2026-10-24/local-backend-report.md) for measured evidence and remaining blockers. The static ChatGPT Site continues to be a showcase; it does not host this backend.
