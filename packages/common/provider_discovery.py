"""Optional read-only provider contracts. No rental, teardown or failover is enabled."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_CEILING
from typing import Any
from urllib.parse import quote
import httpx

from packages.common.providers import GpuSpec, NotConfigured, RunpodProvider


class ProviderReadError(RuntimeError):
    def __init__(self, provider, reason, retryable=False):
        super().__init__(f"{provider}: {reason}")  # Never include response body, URL query or credential.
        self.provider, self.reason, self.retryable = provider, reason, retryable


def micro_usd(value):
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError("Nonnegative finite USD quote required")
    return int((amount * 1000000).to_integral_value(rounding=ROUND_CEILING))


@dataclass(frozen=True)
class Offer:
    provider: str
    offer_id: str
    gpu_type: str
    region: str
    gpu_count: int
    compute_micro_usd_per_hour: int
    observed_at: str
    source: str
    available: bool
    storage_micro_usd_per_hour: int | None = None
    other_micro_usd_per_hour: int | None = None
    billing_increment_seconds: int | None = None
    currency: str = "USD"
    vram_mib_per_gpu: int | None = None
    host_cuda_version: str | None = None
    architecture: str | None = None


def compare_offers(offers, stamp=None, max_age_seconds=300):
    """Rank only complete compatible USD quotes. Never fills missing fees with zero."""
    stamp = stamp or datetime.now(timezone.utc)
    ranked, excluded = [], []
    for offer in offers:
        reason = None
        try:
            observed = datetime.fromisoformat(offer.observed_at)
            if observed.tzinfo is None or not timedelta(0) <= stamp - observed <= timedelta(seconds=max_age_seconds):
                reason = "stale_or_future_quote"
        except (ValueError, TypeError):
            reason = "invalid_quote_timestamp"
        costs = (offer.compute_micro_usd_per_hour, offer.storage_micro_usd_per_hour, offer.other_micro_usd_per_hour)
        if offer.currency != "USD" or offer.gpu_count != 1:
            reason = "incomparable_currency_or_gpu_count"
        elif any(v is None for v in costs) or not offer.billing_increment_seconds:
            reason = "incomplete_total_cost_or_billing_increment"
        elif offer.billing_increment_seconds < 1:
            reason = "invalid_billing_increment"
        elif any(not isinstance(v, int) or v < 0 for v in costs):
            reason = "invalid_cost"
        elif not offer.available:
            reason = "unavailable"
        if reason:
            excluded.append({"provider": offer.provider, "offer_id": offer.offer_id, "reason": reason})
        else:
            ranked.append({**asdict(offer), "total_micro_usd_per_hour": sum(v for v in costs if v is not None)})
    ranked.sort(key=lambda row: (row["total_micro_usd_per_hour"], row["provider"], row["offer_id"]))
    return {"mode": "recommendation_only", "ranked": ranked, "excluded": excluded,
            "operator_approval_required": True, "automatic_failover": False}


class ReadOnlyProvider:
    provider = "optional"
    base_url = ""

    def __init__(self, api_key="", client=None):
        self.api_key = api_key
        self.client = client or httpx.Client(base_url=self.base_url, timeout=15, trust_env=False,
                                             follow_redirects=False,
                                             headers={"Authorization": "Bearer " + api_key})

    def close(self):
        self.client.close()

    def capabilities(self):
        return {"provider": self.provider, "active": self.provider == "runpod", "configured": bool(self.api_key),
                "inventory_read": True, "catalog_read": True, "paid_mutations": False,
                "automatic_failover": False, "hardware_compatibility_verified": False,
                "startup_status": "inventory_only", "health_probe": False,
                "launch_interface": "blocked_stub", "termination_interface": "blocked_stub"}

    def read(self, method, path, **kwargs):
        allowed = ((method == "GET" and path.startswith("/instances"))
                   or (self.provider == "vast" and method == "POST" and path == "/bundles")
                   or (self.provider == "lambda" and method == "GET" and path == "/instance-types")
                   or (self.provider == "runpod" and method == "GET"
                       and (path.startswith("/pods") or path == "/catalog/gpus")))
        if not allowed:
            raise NotConfigured("Optional provider read allowlist forbids this operation")
        if not self.api_key:
            raise NotConfigured(f"{self.provider} discovery credential required")
        # These methods are called only by the fixed inventory/catalog paths below.
        # POST /bundles is Vast's read-only offer search, not instance creation.
        for attempt in range(2):
            try:
                response = self.client.request(method, path, **kwargs)
            except httpx.TransportError:
                if attempt == 0:
                    continue
                raise ProviderReadError(self.provider, "transport_unavailable", True) from None
            if response.status_code in (429, 502, 503, 504):
                if attempt == 0:
                    continue
                raise ProviderReadError(self.provider, "temporarily_unavailable", True)
            if response.status_code in (401, 403):
                raise ProviderReadError(self.provider, "unauthorized")
            if response.status_code >= 300:
                raise ProviderReadError(self.provider, "read_failed")
            try:
                body = response.json()
                if not isinstance(body, dict):
                    raise ValueError
                return body
            except ValueError:
                raise ProviderReadError(self.provider, "invalid_response") from None

    def create_instance(self, spec: GpuSpec, idempotency_key: str):
        raise NotConfigured(f"{self.provider} is discovery-only; paid creation disabled")

    def terminate_instance(self, provider_id: str):
        raise NotConfigured(f"{self.provider} is discovery-only; lifecycle mutations disabled")

    def _offers(self, rows, normalize):
        try:
            if not isinstance(rows, list):
                raise ValueError
            return [normalize(row) for row in rows]
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise ProviderReadError(self.provider, "invalid_catalog") from None


class VastProvider(ReadOnlyProvider):
    provider = "vast"
    base_url = "https://console.vast.ai/api/v0"

    def list_instances(self):
        data = self.read("GET", "/instances/").get("instances")
        if not isinstance(data, list):
            raise ProviderReadError(self.provider, "invalid_inventory")
        return data

    def get_instance(self, provider_id):
        return self.read("GET", "/instances/" + quote(provider_id, safe="") + "/")

    def get_price_quote(self, gpu_type, region):
        query: dict[str, Any] = {"gpu_name": {"eq": gpu_type}, "num_gpus": {"eq": 1},
                                 "verified": {"eq": True}, "rentable": {"eq": True},
                                 "rented": {"eq": False}, "type": "on-demand", "limit": 100}
        if region:
            query["geolocation"] = {"eq": region}
        body = self.read("POST", "/bundles", json=query)
        stamp = datetime.now(timezone.utc).isoformat()
        return self._offers(body.get("offers"), lambda row: Offer(
            "vast", str(row["id"]), row["gpu_name"], row.get("geolocation", "unknown"), row["num_gpus"],
            micro_usd(row["dph_total"]), stamp, "vast_search_offers_dph_total", row.get("rentable") is True,
            vram_mib_per_gpu=int(row["gpu_ram"]) if row.get("gpu_ram") else None,
            host_cuda_version=str(row["cuda_max_good"]) if row.get("cuda_max_good") else None,
            architecture=row.get("cpu_arch")))


class RunpodDiscovery(ReadOnlyProvider):
    """Normalize Runpod reads without changing its existing lifecycle adapter."""
    provider = "runpod"
    base_url = "https://api.runpod.io/v2"

    def __init__(self, api_key="", client=None, cloud="SECURE"):
        if cloud not in {"SECURE", "COMMUNITY"}:
            raise ValueError("Explicit Runpod cloud tier required")
        super().__init__(api_key, client)
        self.cloud = cloud

    def list_instances(self):
        rows, cursor, seen = [], None, set()
        while True:
            body = self.read("GET", "/pods", params={"cursor": cursor} if cursor else {})
            if not isinstance(body.get("pods"), list):
                raise ProviderReadError(self.provider, "invalid_inventory")
            rows.extend(body["pods"])
            page = body.get("pagination", {})
            if not page.get("hasNextPage"):
                return rows
            cursor = page.get("nextCursor")
            if not cursor or cursor in seen:
                raise ProviderReadError(self.provider, "invalid_pagination")
            seen.add(cursor)

    def get_instance(self, provider_id):
        return self.read("GET", "/pods/" + quote(provider_id, safe=""))

    def get_price_quote(self, gpu_type, region):
        body = self.read("GET", "/catalog/gpus", params={"include": "AVAILABILITY", "product": "POD",
                                                        "cloud": self.cloud, "count": 1})
        try:
            if not isinstance(body.get("gpus"), list):
                raise ValueError
            stamp = datetime.now(timezone.utc).isoformat()
            offers = []
            for row in body["gpus"]:
                if gpu_type not in (row["id"], row["name"]):
                    continue
                if region:
                    available = any(dc["id"] == region and dc["availability"] in {"LOW", "MEDIUM", "HIGH"}
                                    for dc in row.get("dataCenters", []))
                else:
                    available = row["availability"] in {"LOW", "MEDIUM", "HIGH"}
                offers.append(Offer("runpod", row["id"] + ":" + self.cloud, row["id"], region or "unplaced", 1,
                                    micro_usd(row["price"][self.cloud.lower()]), stamp,
                                    "runpod_catalog_" + self.cloud.lower(), available,
                                    vram_mib_per_gpu=int(row["memory"]) * 1024 if row.get("memory") else None))
            return offers
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise ProviderReadError(self.provider, "invalid_catalog") from None


class LambdaProvider(ReadOnlyProvider):
    provider = "lambda"
    base_url = "https://cloud.lambda.ai/api/v1"

    def list_instances(self):
        data = self.read("GET", "/instances").get("data")
        if not isinstance(data, list):
            raise ProviderReadError(self.provider, "invalid_inventory")
        return data

    def get_instance(self, provider_id):
        return self.read("GET", "/instances/" + quote(provider_id, safe=""))

    def get_price_quote(self, gpu_type, region):
        data = self.read("GET", "/instance-types").get("data")
        try:
            if not isinstance(data, dict):
                raise ValueError
            stamp = datetime.now(timezone.utc).isoformat()
            offers = []
            for name, entry in sorted(data.items()):
                instance = entry["instance_type"]
                if gpu_type not in (name, instance["gpu_description"]):
                    continue
                regions = [r["name"] for r in entry["regions_with_capacity_available"]]
                for location in ([region] if region else regions or ["unknown"]):
                    offers.append(Offer("lambda", name, instance["gpu_description"], location,
                                        instance["specs"]["gpus"],
                                        micro_usd(Decimal(str(instance["price_cents_per_hour"])) / 100),
                                        stamp, "lambda_instance_types_cents_per_instance_hour", location in regions,
                                        architecture=instance.get("architecture")))
            return offers
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise ProviderReadError(self.provider, "invalid_catalog") from None


def capability_discovery():
    """Local capabilities, not live availability. No client or network is initialized."""
    from packages.common.config import settings
    return {"active_provider": "runpod", "automatic_failover": False,
            "providers": [{"provider": "runpod", "active": True, "adapter": "existing_rest_v2",
                           "provisioning_enabled": settings().provisioning_enabled,
                           "discovery": "catalog_quote_requires_operator_confirmation"},
                          {"provider": "vast", "active": False, "adapter": "read_only"},
                          {"provider": "lambda", "active": False, "adapter": "read_only"}]}


def active_provider(name="runpod"):
    if name != "runpod":
        raise NotConfigured("Only Runpod is active; optional providers cannot be selected for execution")
    return RunpodProvider()


def instance_state(provider, raw):
    """Inventory state is not application health; absent/unknown states remain unknown."""
    if provider == "vast":
        status = raw.get("actual_status")
        phases = {"running": "running", "loading": "starting", "created": "starting", "exited": "stopped"}
    elif provider == "lambda":
        status = raw.get("status")
        phases = {"active": "running", "booting": "starting", "unhealthy": "unhealthy",
                  "terminating": "terminating", "terminated": "terminated"}
    else:
        raise ValueError("Optional provider state adapter required")
    return {"provider": provider, "id": str(raw.get("id", "")), "raw_status": status,
            "phase": phases.get(status, "unknown"), "application_health": "unverified"}
