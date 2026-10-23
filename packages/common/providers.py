"""Runpod REST v2 adapter. No provider calls occur at import or during normal dispatch."""

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
import httpx
from sqlalchemy import select, text, func
from packages.common.config import settings
from packages.common.db import Instance, Audit, Session, GpuCostProfile, now
from packages.common.economics import quoted_cost


@dataclass
class GpuSpec:
    gpu_type: str
    region: str
    image: str
    hourly_micro_usd: int
    environment: str = "development"
    created_by: str = "operator"
    job_group: str = "manual"


class GpuProvider(Protocol):
    def create_instance(self, spec: GpuSpec, idempotency_key: str): ...
    def get_instance(self, provider_id: str): ...
    def list_instances(self): ...
    def terminate_instance(self, provider_id: str): ...
    def get_price_quote(self, gpu_type: str, region: str): ...


class NotConfigured(RuntimeError):
    pass


class FakeProvider:
    def __init__(self):
        self.instances = {}

    def create_instance(self, spec, idempotency_key):
        key = hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]
        self.instances.setdefault(
            key, {"id": key, "name": "inferenceflow-" + key, "cost": spec.hourly_micro_usd / 1000000}
        )
        return self.instances[key]

    def get_instance(self, provider_id):
        return self.instances[provider_id]

    def list_instances(self):
        return list(self.instances.values())

    def terminate_instance(self, provider_id):
        self.instances.pop(provider_id, None)

    def get_price_quote(self, gpu_type, region):
        return {"hourly_micro_usd": 1000000, "test_only": True, "quoted_at": now().isoformat()}


class AttachedWorkerProvider:
    def create_instance(self, spec, idempotency_key):
        raise NotConfigured("Rent manually and register outbound worker; automatic creation disabled")

    def get_instance(self, provider_id):
        return {"id": provider_id, "managed": False}

    def list_instances(self):
        return []

    def terminate_instance(self, provider_id):
        raise NotConfigured("Manually attached capacity must be shut down at provider")

    def get_price_quote(self, gpu_type, region):
        raise NotConfigured("Operator must supply provider quote")


class RunpodProvider:
    def __init__(self, client=None):
        self.client = client or httpx.Client(
            base_url="https://api.runpod.io/v2",
            headers={"Authorization": "Bearer " + settings().runpod_api_key},
            timeout=30,
            trust_env=False,
        )

    def call(self, method, path, **kwargs):
        r = self.client.request(method, path, **kwargs)
        r.raise_for_status()
        return r.json() if r.content else {}

    def list_instances(self):
        rows = []
        cursor = None
        while True:
            data = self.call("GET", "/pods", params={"cursor": cursor} if cursor else {})
            rows.extend(data["pods"])
            cursor = data.get("pagination", {}).get("nextCursor")
            if not data.get("pagination", {}).get("hasNextPage"):
                return rows

    def get_instance(self, provider_id):
        return self.call("GET", "/pods/" + provider_id)

    def terminate_instance(self, provider_id):
        return self.call("DELETE", "/pods/" + provider_id)

    def get_price_quote(self, gpu_type, region):
        # Return the official catalog verbatim, never invent/flatten a price schema.
        return {
            "catalog": self.call("GET", "/catalog/gpus"),
            "gpu_type": gpu_type,
            "region": region,
            "quoted_at": now().isoformat(),
            "requires_operator_confirmation": True,
        }

    def create_instance(self, spec, idempotency_key):
        cfg = settings()
        if not cfg.provisioning_enabled:
            raise NotConfigured("PROVISIONING_ENABLED=false")
        if not cfg.runpod_api_key:
            raise NotConfigured("RUNPOD_API_KEY required")
        if spec.hourly_micro_usd <= 0:
            raise ValueError("Confirmed positive price required")
        # No blind retry after an ambiguous POST. A persistent intent and inventory name fence retries.
        source = hashlib.sha256(idempotency_key.encode()).hexdigest()[:24]
        name = "inferenceflow-" + source
        with Session.begin() as s:
            s.execute(text("SELECT pg_advisory_xact_lock(1081843)"))
            old = s.scalar(select(Instance).where(Instance.source == source))
            if old:
                if old.id.startswith("intent_"):
                    raise NotConfigured("Ambiguous create intent: reconcile provider inventory before retry")
                return self.get_instance(old.id)
            tracked_active = s.scalar(select(func.count()).select_from(Instance).where(Instance.terminated.is_(False)))
            if tracked_active >= cfg.max_active_gpus:
                raise NotConfigured("GPU cap reached including pending creation intents")
            inventory = self.list_instances()
            if len(inventory) >= cfg.max_active_gpus:
                raise NotConfigured("GPU cap reached (dedicated provider account required)")
            tracked = list(s.scalars(select(Instance)))
            day = now().replace(hour=0, minute=0, second=0, microsecond=0)
            spend = sum(
                quoted_cost(max(0, ((i.terminated_at or now()) - max(i.created_at, day)).total_seconds()),
                            i.hourly_micro_usd, cfg.provider_billing_increment_seconds)
                for i in tracked
            )
            worst = quoted_cost(cfg.max_gpu_session_minutes * 60, spec.hourly_micro_usd, cfg.provider_billing_increment_seconds)
            if spend + worst > cfg.max_daily_gpu_spend_usd * 1000000:
                raise NotConfigured("Daily budget admission cap")
            s.add(Instance(id="intent_" + source, source=source, hourly_micro_usd=spec.hourly_micro_usd))
        payload = {
            "name": name,
            "image": spec.image,
            "gpu": {"id": spec.gpu_type, "count": 1},
            "dataCenterIds": [spec.region],
            "disk": 50,
            "env": {
                "IF_OWNER": "inferenceflow",
                "IF_ENVIRONMENT": spec.environment,
                "IF_CREATED_BY": spec.created_by,
                "IF_JOB_GROUP": spec.job_group,
            },
        }
        pod = self.call("POST", "/pods", json=payload)
        with Session.begin() as s:
            s.execute(text("SELECT pg_advisory_xact_lock(1081843)"))
            i = s.scalar(select(Instance).where(Instance.source == source))
            assert i is not None
            if i.terminated:
                raise NotConfigured("Creation expired during provisioning; reconcile provider inventory")
            i.id = pod["id"]
            s.flush()
            s.add(GpuCostProfile(instance_id=i.id, provider="runpod", gpu_type=spec.gpu_type,
                                 billing_increment_seconds=cfg.provider_billing_increment_seconds))
        return pod


def watchdog(provider):
    inventory = provider.list_instances()
    with Session.begin() as s:
        s.execute(text("SELECT pg_advisory_xact_lock(1081843)"))
        history = list(s.scalars(select(Instance)))
        tracked = {i.id: i for i in history if not i.terminated}
        intents = {"inferenceflow-" + i.source: i for i in tracked.values() if i.id.startswith("intent_")}
        cfg = settings()
        stamp = now()
        day = stamp.replace(hour=0, minute=0, second=0, microsecond=0)
        spend = sum(
            quoted_cost(max(0, ((i.terminated_at or stamp) - max(i.created_at, day)).total_seconds()),
                        i.hourly_micro_usd, cfg.provider_billing_increment_seconds)
            for i in history
        )
        for pod in inventory:
            pid = pod["id"]
            i = tracked.get(pid) or intents.get(pod.get("name"))
            if i and i.id.startswith("intent_"):
                i.id = pid
            if not pod.get("name", "").startswith("inferenceflow-"):
                continue
            if not i:
                s.add(Audit(kind="orphan_instance", reference=pid))
                # A shared name prefix is not proof of ownership. Only tracked
                # instance IDs or persistent create intents authorize cleanup.
                continue
            elif (
                stamp - i.created_at > timedelta(minutes=cfg.max_gpu_session_minutes)
                or stamp - i.last_busy > timedelta(seconds=cfg.idle_shutdown_seconds)
                or spend >= cfg.max_daily_gpu_spend_usd * 1000000
            ):
                provider.terminate_instance(pid)
                i.terminated = True
                i.terminated_at = stamp
                s.add(Audit(kind="instance_terminated", reference=pid))
        present = {pod["id"] for pod in inventory}
        for i in tracked.values():
            if i.id.startswith("intent_"):
                # Retain ambiguous intent admission fences until an operator reconciles it.
                continue
            if i.id not in present and not i.terminated:
                i.terminated = True
                i.terminated_at = stamp
                s.add(Audit(kind="instance_missing", reference=i.id))
        if spend >= cfg.max_daily_gpu_spend_usd * 800000:
            s.add(Audit(kind="provider_budget_alert", reference=str(spend)))
