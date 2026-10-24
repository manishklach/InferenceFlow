import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from packages.common.config import settings


@pytest.fixture
def gateway():
    path = Path(__file__).resolve().parents[1] / "infra/local-rehearsal/gateway.py"
    spec = importlib.util.spec_from_file_location("rehearsal_gateway_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", ["/auth/login", "/v1/keys", "/v1/billing/checkout-session",
                                  "/internal/stripe/webhook", "/v1/webhook-destination", "/docs"])
def test_rehearsal_cannot_expose_dev_login_or_payment_admin(gateway, path):
    with TestClient(gateway.app) as client:
        assert client.post(path, json={}).status_code == 404


def test_rehearsal_preserves_real_tenant_key_checks(gateway, tenant):
    with TestClient(gateway.app) as client:
        assert client.get("/v1/wallet").status_code == 401
        assert client.get("/v1/wallet", headers={"Authorization": "Bearer wrong"}).status_code == 401
        headers = {"Authorization": "Bearer " + tenant[1]}
        assert client.get("/v1/wallet", headers=headers).status_code == 200
        headers["Cookie"] = "if_session=forged"
        assert client.get("/v1/wallet", headers=headers).status_code == 403


def test_rehearsal_does_not_accept_arbitrary_worker_bearer(gateway):
    with TestClient(gateway.app) as client:
        response = client.post("/internal/workers/register", headers={"Authorization": "Bearer wrong"},
                               json={"id": "intruder", "model": "qwen3-4b", "capacity": 1})
        assert response.status_code == 401


@pytest.mark.parametrize("flag,value", [("execution_mode", "vllm"), ("environment", "staging"),
                                        ("provisioning_enabled", True), ("stripe_enabled", True),
                                        ("public_beta_enabled", True), ("reviewed_gpu_experiment_enabled", True)])
def test_rehearsal_refuses_real_or_paid_operation(gateway, monkeypatch, flag, value):
    monkeypatch.setattr(settings(), flag, value)
    with pytest.raises(RuntimeError, match="unpaid mock rehearsal"):
        with TestClient(gateway.app):
            pass


def test_rehearsal_wrapper_does_not_change_product_local_login(gateway, client):
    # Importing the wrapper must not add its restrictions to the shared product app.
    assert client.post("/auth/login", json={"email": "local-test@example.invalid"}).status_code == 200
