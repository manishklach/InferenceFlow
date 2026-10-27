from datetime import timedelta
from sqlalchemy import select

from packages.common.db import Session, Work, Usage, now
from packages.common.receipt_format import canonical_sha256, text_sha256
from packages.python_sdk import verify_receipt
from packages.common.service import purge
from tests.test_platform import body, register, drain


def test_receipts_are_tenant_scoped_paginated_and_read_only(client, headers, tenant):
    submitted = client.post('/v1/jobs', json=body(2), headers=headers).json()
    path = '/v1/jobs/'+submitted['id']+'/receipts'
    assert client.get(path, headers=headers).status_code == 409
    drain(client, register(client))
    before_wallet = client.get('/v1/wallet', headers=headers).json()
    page = client.get(path+'?limit=1', headers=headers).json()
    assert page['next_cursor'] == 1
    envelope = page['items'][0]
    assert verify_receipt(envelope)
    receipt = envelope['receipt']
    assert receipt['billing']['request_settlement_reconciled'] is True
    assert receipt['billing']['usage_records'] == receipt['billing']['capture_records'] == 1
    assert receipt['model']['execution_mode'] == 'mock'
    assert receipt['hashes']['prompt_sha256'] == canonical_sha256(body()['requests'][0]['messages'])
    output = client.get('/v1/jobs/'+submitted['id']+'/results', headers=headers).json()['items'][0]['output_text']
    assert receipt['hashes']['output_sha256'] == text_sha256(output)
    assert output not in str(envelope)
    assert client.get(path, headers={'Authorization':'Bearer invalid'}).status_code == 401
    from packages.common.service import account, new_key
    with Session.begin() as session:
        other = account(session, 'test:receipt-other')
        key = new_key(session, other.id, 'other')['key']
    assert client.get(path, headers={'Authorization':'Bearer '+key}).status_code == 404
    repeat = client.get(path+'?limit=1', headers=headers).json()['items'][0]
    assert repeat == envelope
    after_wallet = client.get('/v1/wallet', headers=headers).json()
    assert {k:v for k,v in before_wallet.items() if k!='request_id'} == {
        k:v for k,v in after_wallet.items() if k!='request_id'}
    receipt['usage']['output_tokens'] += 1
    assert not verify_receipt(envelope)


def test_receipts_survive_content_purge_and_detect_settlement_mismatch(client, headers):
    jid = client.post('/v1/jobs', json=body(), headers=headers).json()['id']
    drain(client, register(client))
    with Session.begin() as session:
        work = session.scalar(select(Work).where(Work.job_id == jid))
        work.completed_at = now()-timedelta(days=30)
        rid = work.id
    path = '/v1/jobs/'+jid+'/receipts'
    before = client.get(path, headers=headers).json()['items']
    with Session.begin() as session:
        purge(session)
    assert client.get(path, headers=headers).json()['items'] == before
    with Session.begin() as session:
        work = session.get(Work, rid)
        assert work.payload is None and work.output is None
        session.get(Usage, rid).charge += 1
    receipt = client.get(path, headers=headers).json()['items'][0]
    assert verify_receipt(receipt)
    assert receipt['receipt']['billing']['request_settlement_reconciled'] is False


def test_canceled_receipt_has_no_billable_usage(client, headers):
    jid = client.post('/v1/jobs', json=body(), headers=headers).json()['id']
    client.post('/v1/jobs/'+jid+'/cancel', headers=headers)
    receipt = client.get('/v1/jobs/'+jid+'/receipts', headers=headers).json()['items'][0]['receipt']
    assert receipt['status'] == 'canceled'
    assert receipt['billing']['captured'] == receipt['billing']['usage_records'] == 0
    assert receipt['billing']['request_settlement_reconciled'] is True
    assert receipt['hashes']['output_sha256'] is None
