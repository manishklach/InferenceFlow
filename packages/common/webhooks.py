import hashlib
import hmac
import json
import time
from datetime import timedelta
from urllib.parse import urlsplit
import httpx
from sqlalchemy import select, or_
from packages.common.db import Job, Tenant, Delivery, Session, now, uid
from packages.common.service import works, status, TERMINAL
from packages.common.security import validate_url, decrypt


def signature(secret, stamp, body):
    return "v1=" + hmac.new(secret.encode(), str(stamp).encode() + b"." + body, hashlib.sha256).hexdigest()


def verify(secret, stamp, body, sig):
    return abs(time.time() - int(stamp)) <= 300 and hmac.compare_digest(signature(secret, stamp, body), sig)


def enqueue(s):
    for j in s.scalars(select(Job).where(Job.notified.is_(False)).with_for_update(skip_locked=True)):
        state = status(j, works(s, j.id))
        tenant = s.get(Tenant, j.tenant_id)
        if state not in TERMINAL | {"partially_succeeded"}:
            continue
        j.notified = True
        if not tenant.webhook_url:
            continue
        eid = "evt_" + uid()
        body = json.dumps(
            {
                "event_id": eid,
                "type": "job.completed",
                "created_at": now().isoformat(),
                "job_id": j.id,
                "status": state,
            },
            separators=(",", ":"),
        )
        s.add(Delivery(id=eid, tenant_id=tenant.id, job_id=j.id, body=body))


def send(url, ips, body, headers):
    # Connect to the validated, registered IP with original TLS SNI/Host: DNS cannot rebind between validation/connect.
    current = validate_url(url)
    allowed = set(json.loads(ips))
    if not set(current) <= allowed:
        raise ValueError("DNS destination changed; re-register endpoint")
    u = urlsplit(url)
    ip = current[0]
    host = "[" + ip + "]" if ":" in ip else ip
    target = "https://" + host + (u.path or "/") + ("?" + u.query if u.query else "")
    with httpx.Client(follow_redirects=False, trust_env=False, timeout=10) as c:
        req = c.build_request("POST", target, content=body, headers={**headers, "Host": u.hostname})
        req.extensions["sni_hostname"] = u.hostname.encode()
        response = c.send(req)
        if not 200 <= response.status_code < 300:
            raise ValueError("Delivery failed")


def deliver():
    # Claim with a lease, commit, then do network I/O without holding database locks.
    for _ in range(10):
        with Session.begin() as s:
            d = s.scalar(
                select(Delivery)
                .where(
                    Delivery.delivered.is_(False),
                    Delivery.due <= now(),
                    or_(Delivery.claim_until.is_(None), Delivery.claim_until < now()),
                )
                .order_by(Delivery.due, Delivery.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if not d:
                return
            claim = uid()
            d.claim = claim
            d.claim_until = now() + timedelta(minutes=2)
            did, body = d.id, d.body.encode()
            t = s.get(Tenant, d.tenant_id)
            assert t is not None
            url, ips, secret = t.webhook_url, t.webhook_ips, t.webhook_secret
        stamp = str(int(time.time()))
        delivered = False
        try:
            send(
                url,
                ips,
                body,
                {
                    "Content-Type": "application/json",
                    "X-IF-Timestamp": stamp,
                    "X-IF-Signature": signature(decrypt(secret), stamp, body),
                },
            )
            delivered = True
        except Exception:
            pass
        with Session.begin() as s:
            d = s.scalar(select(Delivery).where(Delivery.id == did).with_for_update())
            if d is None or d.claim != claim:
                continue
            d.claim = None
            d.claim_until = None
            if delivered:
                d.delivered = True
            else:
                d.attempts += 1
                d.due = now() + timedelta(seconds=min(3600, 2 ** min(d.attempts, 12)))
                if now() - d.created_at > timedelta(hours=24):
                    d.due = now() + timedelta(days=36500)
