import pytest

from packages.common.config import settings
from packages.common.db import Session
from scripts.hosted_mock_pipeline import require_mock, seed


def test_disposable_seed_is_unique_and_does_not_change_rates(monkeypatch):
    cfg = settings()
    rates = cfg.input_rate, cfg.output_rate
    monkeypatch.setattr(cfg, "environment", "staging")
    monkeypatch.setattr(cfg, "execution_mode", "mock")
    monkeypatch.setenv("HOSTED_DISPOSABLE_MOCK", "true")
    with Session.begin() as session:
        result = seed(session, "123456-1")
        assert result["key"] and result["tenant_id"]
    with Session.begin() as session:
        with pytest.raises(RuntimeError, match="existing tenant"):
            seed(session, "123456-1")
    assert (cfg.input_rate, cfg.output_rate) == rates


def test_seed_cannot_run_in_real_mode_or_without_disposable_flag(monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, "environment", "staging")
    monkeypatch.setattr(cfg, "execution_mode", "vllm")
    with pytest.raises(RuntimeError):
        require_mock()
    monkeypatch.setattr(cfg, "execution_mode", "mock")
    monkeypatch.delenv("HOSTED_DISPOSABLE_MOCK", raising=False)
    with Session.begin() as session:
        with pytest.raises(RuntimeError, match="Disposable"):
            seed(session, "123456-1")
