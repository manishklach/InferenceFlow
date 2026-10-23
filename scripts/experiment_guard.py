"""Independent single-pod budget/time guard. Inert unless --execute is supplied after approval."""

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
import time
from pathlib import Path
import httpx


def decision(created_at, stamp, hourly_usd, total_budget_usd=Decimal("10"), max_seconds=7200):
    elapsed = Decimal(str((stamp - created_at).total_seconds()))
    rate = Decimal(str(hourly_usd))
    budget = Decimal(str(total_budget_usd))
    if elapsed < 0 or not rate.is_finite() or rate <= 0 or not budget.is_finite() or not 0 < budget <= 10:
        raise ValueError("Valid full hourly cost, creation time and budget <=10 required")
    if not 0 < max_seconds <= 7200:
        raise ValueError("Maximum 120 minutes")
    estimate = elapsed * rate / 3600
    return {
        "elapsed_seconds": float(elapsed),
        "estimated_total_usd": str(estimate),
        "stop_admissions": estimate >= budget * Decimal(".7"),
        "terminate": estimate >= budget * Decimal(".8") or elapsed >= max_seconds,
    }


def verify_owned(pod, receipt):
    # Receipt is supplied by the operator AFTER a separately approved create read-back.
    if pod.get("id") != receipt["pod_id"] or pod.get("name") != receipt["pod_name"]:
        raise ValueError("Pod identity mismatch; manual investigation required")


def terminate_verified(client, receipt):
    pid = receipt["pod_id"]
    if not pid or any(x not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for x in pid):
        raise ValueError("Invalid exact Pod ID")
    r = client.get("/pods/" + pid)
    if r.status_code == 404:
        return True
    r.raise_for_status()
    verify_owned(r.json(), receipt)
    deleted = client.delete("/pods/" + pid)
    if deleted.status_code != 404:
        deleted.raise_for_status()
    confirm = client.get("/pods/" + pid)
    return confirm.status_code == 404


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("No termination action authorized; --execute required")
    receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    if receipt.get("operator_approved") is not True or not receipt.get("all_in_hourly_cost_confirmed"):
        raise SystemExit("Explicit approved exact-pod receipt and full cost confirmation required")
    key = os.getenv("RUNPOD_API_KEY", "")
    if not key:
        raise SystemExit("Independent supervisor requires securely supplied RUNPOD_API_KEY")
    created = datetime.fromisoformat(receipt["provider_created_at"].replace("Z", "+00:00"))
    if created.tzinfo is None:
        raise SystemExit("Timezone-aware actual provider creation time required")
    with httpx.Client(
        base_url="https://api.runpod.io/v2",
        headers={"Authorization": "Bearer " + key},
        timeout=15,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        while True:
            state = decision(created, datetime.now(timezone.utc), receipt["all_in_hourly_usd"])
            try:
                r = client.get("/pods/" + receipt["pod_id"])
                if r.status_code == 404:
                    break
                r.raise_for_status()
                verify_owned(r.json(), receipt)
                if state["terminate"]:
                    state["termination_confirmed"] = terminate_verified(client, receipt)
            except Exception as error:
                # No response bodies, request URLs or credentials in evidence.
                state["error_type"] = type(error).__name__
            with Path(args.log).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"observed_at": datetime.now(timezone.utc).isoformat(), **state}) + "\n")
            print(json.dumps(state), flush=True)
            if state.get("termination_confirmed"):
                break
            time.sleep(10 if state["terminate"] else 30)


if __name__ == "__main__":
    main()
