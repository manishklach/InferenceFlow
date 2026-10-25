"""Retry a committed-but-lost finalization against the real API and test database."""
import asyncio
import json
import httpx
from sqlalchemy import func, select
from apps.worker.engines import MockInferenceEngine
from apps.worker.main import control_post
from packages.common.db import Session, Usage, Ledger, Worker
from packages.common.service import reconcile, schedule
from tests.test_platform import body, register


def test_lost_finalize_response_retries_without_duplicate_customer_charge(client, headers):
    job = client.post('/v1/jobs', headers=headers, json=body()).json()
    worker_headers = register(client)
    with Session.begin() as session:
        generation = session.get(Worker, 'worker').generation
        schedule(session)
    item = client.post('/internal/workers/poll', headers=worker_headers).json()['items'][0]
    output = asyncio.run(MockInferenceEngine().execute(item))
    calls = []

    def transport(request):
        payload = json.loads(request.content)
        calls.append(payload)
        response = client.post(request.url.path, headers=worker_headers, json=payload)
        assert response.status_code == (200 if len(calls) == 1 else 409), response.text
        if len(calls) == 1:
            # The transaction committed, but the worker did not receive its response.
            raise httpx.ReadError('connection lost after commit', request=request)
        return httpx.Response(response.status_code, json=response.json())

    async def retry():
        async with httpx.AsyncClient(base_url='https://control.invalid', transport=httpx.MockTransport(transport)) as http:
            await control_post(http, '/internal/workers/requests/'+item['id']+'/finalize',
                               json={'epoch': item['epoch'], **output}, accepted_statuses=(404, 409))
    asyncio.run(retry())
    assert len(calls) == 2 and calls[0] == calls[1]
    finished = client.get('/v1/jobs/'+job['id'], headers=headers).json()
    assert finished['status'] == 'succeeded' and finished['reserved_micro_usd'] == 0
    with Session.begin() as session:
        assert session.scalar(select(func.count()).select_from(Usage)) == 1
        assert session.scalar(select(func.count()).select_from(Ledger).where(Ledger.kind == 'capture')) == 1
        assert session.get(Worker, 'worker').generation == generation
        assert reconcile(session) == []
