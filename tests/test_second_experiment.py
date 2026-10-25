"""Second-run readiness race, timing and coverage regressions; no paid resources."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from sqlalchemy import func, select
from apps.worker.main import main as worker_main
from packages.common.config import settings
from packages.common.db import Session, WorkerProbe, Ledger, Job, Work, ExecutionAttempt, now
from packages.common.experiment_timing import components
from packages.common.identity import model_identity
from scripts.experiment_phases import cold_start, extract_events
from scripts.second_gpu_experiment import coverage, prepare
from tests.test_platform import body
from packages.common.service import schedule
from scripts.audit_gpu_run import audit_run


def setup_worker(client, monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, 'reviewed_gpu_experiment_enabled', True)
    monkeypatch.setattr(cfg, 'execution_mode', 'vllm')
    monkeypatch.setattr(cfg, 'metrics_token', 'unit-metrics')
    monkeypatch.setattr('packages.common.service.count_prompt', lambda messages: 5)
    def register():
        r = client.post('/internal/workers/register', headers={'Authorization': 'Bearer local-worker-only'},
                        json={'id': 'live-test', 'capacity': 4, **model_identity()})
        assert r.status_code == 200, r.text
        return {'Authorization': 'Bearer '+r.json()['worker_token']}
    return register, register(), {'Authorization': 'Bearer unit-metrics'}


def challenge(client, operator):
    r = client.post('/internal/experiments/readiness', headers=operator, json={'worker_id': 'live-test'})
    assert r.status_code == 200, r.text
    return r.json()['challenge']


def test_cached_heartbeat_not_ready_and_proof_consumed_before_reserving(client, headers, monkeypatch):
    register, worker, operator = setup_worker(client, monkeypatch)
    assert client.post('/v1/jobs', headers=headers, json=body()).status_code == 503
    assert client.post('/internal/experiments/readiness', json={'worker_id': 'live-test'}).status_code == 401
    proof = challenge(client, operator)
    assert client.get('/internal/experiments/readiness/'+proof, headers=operator).json()['ready'] is False
    assert client.post('/internal/workers/readiness', headers=worker, json={'challenge': proof}).status_code == 409
    assert client.post('/v1/jobs', headers={**headers, 'X-Experiment-Readiness': proof}, json=body()).status_code == 503
    poll = client.post('/internal/workers/poll', headers=worker).json()
    assert poll['readiness_challenge'] == proof
    assert client.post('/internal/workers/readiness', headers=worker, json={'challenge': proof}).status_code == 200
    marked = {**headers, 'X-Experiment-Readiness': proof}
    accepted = client.post('/v1/jobs', headers=marked, json=body())
    assert accepted.status_code == 202, accepted.text
    assert client.post('/v1/jobs', headers=marked, json=body()).json()['id'] == accepted.json()['id']
    assert client.post('/v1/jobs', headers={**marked, 'Idempotency-Key': 'second'}, json=body()).status_code == 503
    with Session.begin() as s:
        assert s.scalar(select(func.count()).select_from(Ledger).where(Ledger.kind == 'reservation')) == 1


def test_probe_invalid_after_worker_reregistration_or_expiry(client, headers, monkeypatch):
    register, worker, operator = setup_worker(client, monkeypatch)
    proof = challenge(client, operator)
    client.post('/internal/workers/poll', headers=worker)
    client.post('/internal/workers/readiness', headers=worker, json={'challenge': proof})
    worker = register()
    assert client.get('/internal/experiments/readiness/'+proof, headers=operator).json()['ready'] is False
    assert client.post('/internal/workers/readiness', headers=worker, json={'challenge': proof}).status_code == 409
    proof = challenge(client, operator)
    client.post('/internal/workers/poll', headers=worker)
    client.post('/internal/workers/readiness', headers=worker, json={'challenge': proof})
    original_revision = settings().model_revision
    monkeypatch.setattr(settings(), 'model_revision', 'changed-model')
    assert client.get('/internal/experiments/readiness/'+proof, headers=operator).json()['ready'] is False
    assert client.post('/v1/jobs', headers={**headers, 'X-Experiment-Readiness': proof}, json=body()).status_code == 503
    monkeypatch.setattr(settings(), 'model_revision', original_revision)
    with Session.begin() as s:
        s.get(WorkerProbe, proof).expires_at = now()-timedelta(seconds=1)
    assert client.post('/v1/jobs', headers={**headers, 'X-Experiment-Readiness': proof}, json=body()).status_code == 503
    with Session.begin() as s:
        assert s.scalar(select(func.count()).select_from(Ledger).where(Ledger.kind == 'reservation')) == 0


def test_live_api_records_admission_dispatch_and_worker_timing(client, headers, monkeypatch):
    _, worker, operator = setup_worker(client, monkeypatch)
    proof = challenge(client, operator)
    client.post('/internal/workers/poll', headers=worker)
    client.post('/internal/workers/readiness', headers=worker, json={'challenge': proof})
    accepted = client.post('/v1/jobs', headers={**headers, 'X-Experiment-Readiness': proof}, json=body())
    jid = accepted.json()['id']
    with Session.begin() as s:
        schedule(s)
    item = client.post('/internal/workers/poll', headers=worker).json()['items'][0]
    result = client.post('/internal/workers/requests/'+item['id']+'/finalize', headers=worker,
                         json={'epoch': item['epoch'], 'input_tokens': 5, 'output_tokens': 2, 'output_text': 'fixture',
                               'worker_start_delay_seconds': .02, 'worker_engine_seconds': .1})
    assert result.status_code == 200, result.text
    with Session.begin() as s:
        job, row, attempt = s.get(Job,jid), s.get(Work,item['id']), s.get(ExecutionAttempt,(item['id'],item['epoch']))
        timing = components(job,row,attempt)
        assert all(value is not None and value >= 0 for value in timing.values())
        assert abs(sum(list(timing.values())[:6])-(attempt.started_at-job.received_at).total_seconds()) < 1e-9
        report = audit_run(s,[jid])
        assert report['passed'] and report['first_dispatch_components_seconds']['admission']['measured'] == 1


def test_readiness_proof_cannot_admit_two_concurrent_jobs(client, headers, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    _, worker, operator = setup_worker(client, monkeypatch)
    proof = challenge(client, operator)
    client.post('/internal/workers/poll', headers=worker)
    client.post('/internal/workers/readiness', headers=worker, json={'challenge': proof})
    def submit(index):
        return client.post('/v1/jobs', headers={**headers, 'Idempotency-Key': 'race-'+str(index),
                           'X-Experiment-Readiness': proof}, json=body()).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, range(2))) == [202,503]


def test_worker_runs_new_canary_before_acknowledging_poll_challenge(monkeypatch):
    async def scenario():
        ready_calls = 0
        done = asyncio.Event()
        async def ready():
            nonlocal ready_calls
            ready_calls += 1
            return True
        def control(request):
            if request.url.path.endswith('/register'):
                return httpx.Response(200, json={'worker_token': 'unit'})
            if request.url.path.endswith('/poll'):
                return httpx.Response(200, json={'items': [], 'readiness_challenge': 'fresh'})
            if request.url.path.endswith('/readiness'):
                assert ready_calls == 2
                assert json.loads(request.content) == {'challenge': 'fresh'}
                done.set()
            return httpx.Response(200, json={})
        original = httpx.AsyncClient
        def factory(*args, **kwargs):
            return original(*args, **kwargs, transport=httpx.MockTransport(control))
        with patch('httpx.AsyncClient', side_effect=factory), patch('apps.worker.engines.MockInferenceEngine.ready', side_effect=ready):
            task = asyncio.create_task(worker_main())
            try:
                await asyncio.wait_for(done.wait(), 3)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    monkeypatch.setattr(settings(), 'execution_mode', 'mock')
    monkeypatch.setenv('CONTROL_PLANE_URL', 'https://control.invalid')
    asyncio.run(scenario())


def test_dispatch_components_are_disjoint_and_legacy_unknown():
    t = datetime(2026, 10, 25, tzinfo=timezone.utc)
    def point(n):
        return t+timedelta(seconds=n)
    job = SimpleNamespace(received_at=point(0), accepted_at=point(1))
    row = SimpleNamespace(initial_eligible_at=point(2), eligibility_observed_at=point(4), lease_decision_at=point(7), first_dispatched_at=point(8))
    attempt = SimpleNamespace(started_at=point(10), worker_start_delay_seconds=.2, worker_engine_seconds=1)
    result = components(job, row, attempt)
    assert sum(result[name] for name in list(result)[:6]) == 10
    assert result['queue_until_scheduler_observation'] == 2
    job.received_at = job.accepted_at = None
    assert components(job, row, None)['admission'] is None


def test_compact_coverage_fails_gaps_and_deduplicates():
    def sample(second):
        return {'schema_version': 1, 'event': 'engine_sample', 'observed_at': f'2026-10-25T00:00:{second:02d}+00:00',
                'engine_metrics': {'vllm:num_requests_running': 4, 'vllm:num_requests_waiting': 0,
                                   'vllm:prompt_tokens_total': second*10, 'vllm:generation_tokens_total': second},
                'nvidia_smi_csv': 'name, utilization.gpu [%]\nL4, 80 %\n'}
    start = datetime(2026, 10, 25, tzinfo=timezone.utc).timestamp()
    rows = [sample(i) for i in range(10)]
    assert coverage(rows+rows, start, start+10)['coverage_fraction'] == 1
    bad = coverage(rows[:2]+rows[-2:], start, start+10)
    assert bad['passed'] is False and bad['unknown_seconds'] > 0
    assert coverage([], start, start+10)['gpu_utilization_percent_covered_intervals_only'] is None


def test_identical_workloads_and_cold_start_missing_data(tmp_path):
    plan = prepare(tmp_path/'prepared')
    assert plan['paid_execution_authorized'] is False
    assert plan['matched_100_policies'] == ['sequential', 'baseline', 'adaptive']
    rows = json.loads((tmp_path/'prepared/comparison-100.json').read_text())
    assert len(rows) == 100
    assert cold_start([])['phases']['pod_allocation']['seconds'] is None
    events = extract_events([{'ts': '2026-10-25T00:01:00Z', 'source': 'container',
                              'line': 'torch.compile takes 12.5 s in total'}])
    assert cold_start(events)['phases']['compilation']['seconds'] == 12.5
