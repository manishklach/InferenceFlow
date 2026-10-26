import pytest

from packages.common.config import settings
from packages.common.db import Session
from packages.common.service import account
from scripts.hosted_real_audit import audit
from tests.test_platform import body


def test_audit_selects_only_exact_disposable_tenant(client, headers, monkeypatch):
    # Another tenant's queued job must not be admitted to the experiment audit scope.
    assert client.post('/v1/jobs', headers=headers, json=body()).status_code == 202
    with Session.begin() as session:
        account(session, 'github-disposable-real:123-1')
    for key, value in {'environment': 'staging', 'execution_mode': 'vllm',
            'reviewed_gpu_experiment_enabled': True, 'provisioning_enabled': False,
            'public_beta_enabled': False, 'stripe_enabled': False, 'runpod_api_key': ''}.items():
        monkeypatch.setattr(settings(), key, value)
    assert audit('123-1') == {'passed': True, 'accepted_requests': 0}
    with pytest.raises(RuntimeError, match='tenant missing'):
        audit('123-2')


def test_audit_rejects_paid_enabled_configuration(monkeypatch):
    monkeypatch.setattr(settings(), 'provisioning_enabled', True)
    with pytest.raises(RuntimeError, match='Isolated real experiment'):
        audit('123-1')
