# InferenceFlow
A prepaid asynchronous inference execution platform. FastAPI + PostgreSQL 16 + a durable scheduler + outbound GPU worker + Next.js dashboard + Python SDK. Local mode produces clearly labeled deterministic MOCK outputs. No GPU is provisioned and no real payment is accepted by default.

## Local Docker quickstart
Requires Docker Engine/Compose. In PowerShell:
```powershell
cd C:\Users\ManishKL\Documents\Playground\inferenceflow
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec api python -m packages.common.cli seed
```
The last command prints a new API key once and adds $10 in test credits (the funding reference is idempotent). Visit http://localhost:3000 and sign in as `developer@example.local`. API docs: http://localhost:8080/docs. OpenAPI: `/openapi.json` and `docs-openapi.json`.

```powershell
$env:INFERENCEFLOW_API_KEY = '<key printed by seed>'
# Install locally if you want to use the SDK outside Docker:
python -m venv .venv
.venv/Scripts/python -m pip install -e '.[dev]'
.venv/Scripts/python examples/batch.py
```
`python scripts/local_demo.py` performs the same 100-request smoke test with three real local processes and cleans them up. `docker compose exec api python scripts/docker_smoke.py` tests the running container stack.

The example submits 100 independent requests and polls until `succeeded`, prints ordered results, token counts and the remaining wallet. Each output starts with `MOCK` in mock mode. `POST /v1/jobs/{id}/cancel` releases queued reservations; running work can finish and be billed if returned.

## Without Docker
Use PostgreSQL 16 and set `DATABASE_URL` in `.env`. Python 3.12 is the deployment target; development also supports 3.11.
```powershell
.venv/Scripts/python -m pip install -e '.[dev,gpu]'
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m packages.common.cli seed
# Separate terminals, same working directory:
.venv/Scripts/python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8080
.venv/Scripts/python -m apps.scheduler.main
.venv/Scripts/python -m apps.worker.main
cd apps/dashboard
npm ci
npm run dev
```

## Verification
Tests always use a separate database ending `_test` (by default the DATABASE_URL database name plus `_test`) and truncate only that test database. Create it first; set TEST_DATABASE_URL to customize. No SQLite fallback exists.
```powershell
.venv/Scripts/python -m alembic upgrade head
# For Docker's local Postgres:
docker compose exec postgres createdb -U inferenceflow inferenceflow_test
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m mypy apps packages
.venv/Scripts/python -m packages.common.cli reconcile
cd apps/dashboard
npm ci
npm run build
```
Linux equivalents: `make test lint typecheck`. CI supplies PostgreSQL 16.9. GPU test is opt-in with `RUN_GPU_E2E=1`; it requires a real-mode catalog and verifies real output, engine usage and captured credit.

See [implementation status](IMPLEMENTATION_STATUS.md), [architecture](docs/architecture.md), [API](docs/api.md), [billing](docs/billing.md), [GPU setup](docs/gpu-deploy.md), [security](docs/security.md) and [operations](docs/ops.md). Public beta remains gated pending measured pricing, external integration validation and launch review.

This machine was additionally validated using an isolated Docker Engine in WSL because Docker Desktop was stopped. Standard Docker commands above require your normal engine to be running. The native Windows preview uses PostgreSQL in WSL; its local `.env` is intentionally ignored by Git.
