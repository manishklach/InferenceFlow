"""GET-only RunPod catalog collection for an unattended, separately scoped key.

No resource-management API is implemented. Fetch/validate all catalogs before
appending history. Provider errors never print response bodies or credentials.
"""
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from scripts import cpu_rate_history, gpu_rate_history


BASE = "https://api.runpod.io/v2/catalog/"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def catalog_get(key, path, params):
    if path not in ("gpus", "cpus"):
        raise ValueError("Only read-only compute catalogs are permitted")
    request = urllib.request.Request(BASE + path + "?" + urllib.parse.urlencode(params),
                                     headers={"Authorization": "Bearer " + key,
                                              "Accept": "application/json"}, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    for attempt in range(3):
        try:
            with opener.open(request, timeout=20) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if attempt == 2 or error.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"RunPod catalog GET failed (HTTP {error.code})") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                raise RuntimeError("RunPod catalog GET transport failed") from None
        time.sleep(2 ** attempt)
    raise RuntimeError("Catalog retries exhausted")


def price(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid catalog price")


def entries(data, field):
    if not isinstance(data, dict) or not isinstance(data.get(field), list) or not data[field]:
        raise ValueError("Empty or invalid compute catalog")
    if data.get("pagination", {}).get("hasNextPage"):
        raise ValueError("Catalog now paginates; update collector before claiming a complete snapshot")
    identifiers = [row["id"] for row in data[field]]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate catalog identities")
    return data[field]


def collect(key, fetch=catalog_get):
    gpus = []
    for cloud in ("COMMUNITY", "SECURE"):
        data = fetch(key, "gpus", {"include": "AVAILABILITY", "product": "POD", "count": 1, "cloud": cloud})
        for item in entries(data, "gpus"):
            price(item["price"][cloud.lower()])
            if not item.get("name") or not isinstance(item["memory"], (int, float)):
                raise ValueError("Invalid GPU identity/memory")
            if item.get("availability") not in ("NONE", "LOW", "MEDIUM", "HIGH"):
                raise ValueError("Unknown GPU availability")
            gpus.append({**item, "cloud": cloud})
    cpus = entries(fetch(key, "cpus", {"include": "AVAILABILITY", "product": "POD", "vcpuCount": 2}), "cpus")
    for item in cpus:
        price(item["price"]["securePerVcpu"])
        if not item.get("name") or not item.get("group") or item["ramGbPerVcpu"] <= 0:
            raise ValueError("Invalid CPU identity/memory")
        if not 0 < item["vcpu"]["min"] <= 2 <= item["vcpu"]["max"]:
            raise ValueError("Two-vCPU availability no longer fits this family")
        if item.get("availability") not in ("NONE", "LOW", "MEDIUM", "HIGH"):
            raise ValueError("Unknown CPU availability")
    return {"observed_at_utc": datetime.now(timezone.utc).isoformat(), "gpus": gpus, "cpus": cpus}


def persist(snapshot):
    observed = snapshot["observed_at_utc"]
    gpu_rate_history.record_snapshot(snapshot["gpus"], observed, "RunPod REST v2 catalog")
    cpu_rate_history.record_snapshot(snapshot["cpus"], observed, "RunPod REST v2 catalog")


def main():
    key = os.environ.get("RUNPOD_PRICING_API_KEY", "").strip()
    if not key:
        raise SystemExit("Missing RUNPOD_PRICING_API_KEY: configure the separate read-only repository secret")
    try:
        snapshot = collect(key)
        # Public catalog data only, retained as a failure artifact if Git push fails.
        path = Path(".runtime/pricing-snapshot.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, sort_keys=True), encoding="utf-8")
        persist(snapshot)
    except Exception as error:
        raise SystemExit("Pricing collection failed: " + type(error).__name__) from None
    print(json.dumps({"observed_at_utc": snapshot["observed_at_utc"],
                      "gpu_cloud_quotes": len(snapshot["gpus"]), "cpu_families": len(snapshot["cpus"]),
                      "provider_operations": "GET catalogs only"}))


if __name__ == "__main__":
    main()
