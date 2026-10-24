"""Restricted mock-only operator gateway; not production/OIDC staging."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from apps.api.main import app as platform_app
from packages.common.config import settings


def validate_rehearsal():
    config = settings()
    if (
        config.environment != "development"
        or config.execution_mode != "mock"
        or config.provisioning_enabled
        or config.stripe_enabled
        or config.public_beta_enabled
        or config.reviewed_gpu_experiment_enabled
    ):
        raise RuntimeError("This gateway is restricted to an unpaid mock rehearsal")


@asynccontextmanager
async def lifespan(app):
    validate_rehearsal()
    async with platform_app.router.lifespan_context(platform_app):
        yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/", platform_app)


@app.middleware("http")
async def rehearsal_boundary(request: Request, call_next):
    path = request.url.path
    public = request.method == "GET" and path in {"/healthz", "/readyz"}
    customer = path in {
        "/v1/models", "/v1/wallet", "/v1/wallet/transactions", "/v1/performance", "/v1/jobs"
    } or path.startswith("/v1/jobs/")
    worker = path.startswith("/internal/workers/")
    if not (public or customer or worker):
        return JSONResponse({"error": "route_unavailable_in_private_rehearsal"}, 404)
    if request.headers.get("cookie"):
        return JSONResponse({"error": "cookies_disabled_in_private_rehearsal"}, 403)
    if not public and not request.headers.get("authorization", "").startswith("Bearer "):
        return JSONResponse({"error": "bearer_required"}, 401)
    # Existing API dependencies verify tenant keys and worker bootstrap/session tokens.
    return await call_next(request)
