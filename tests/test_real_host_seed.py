import json

import pytest

from packages.common.config import settings
from packages.common.db import Session, Wallet
from scripts.github_real_host import REVISION, seed_real


def test_real_host_initialization_is_disposable_and_preserves_existing_wallet(tenant, monkeypatch, capsys):
    cfg = settings()
    for name, value in (("environment", "staging"), ("execution_mode", "vllm"),
                        ("model_revision", REVISION), ("reviewed_gpu_experiment_enabled", True)):
        monkeypatch.setattr(cfg, name, value)
    monkeypatch.setenv("HOSTED_REAL_IDENTITY", "1234567-1")
    with Session.begin() as session:
        before = session.get(Wallet, tenant[0]).available
    seed_real()
    result = json.loads(capsys.readouterr().out)
    assert len(result["key"]) >= 32
    with Session.begin() as session:
        assert session.get(Wallet, tenant[0]).available == before
    with pytest.raises(RuntimeError, match="existing tenant"):
        seed_real()


def test_real_seed_blocks_provider_authority_and_public_mode(monkeypatch):
    cfg = settings()
    for name, value in (("environment", "staging"), ("execution_mode", "vllm"),
                        ("model_revision", REVISION), ("reviewed_gpu_experiment_enabled", True),
                        ("public_beta_enabled", True)):
        monkeypatch.setattr(cfg, name, value)
    monkeypatch.setenv("HOSTED_REAL_IDENTITY", "1234567-1")
    with pytest.raises(RuntimeError):
        seed_real()
    monkeypatch.setattr(cfg, "public_beta_enabled", False)
    monkeypatch.setattr(cfg, "runpod_api_key", "deliberately-invalid-provider-key")
    with pytest.raises(RuntimeError):
        seed_real()
