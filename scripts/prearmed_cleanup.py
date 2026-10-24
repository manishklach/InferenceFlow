"""Independent, bounded, exact-experiment cleanup. Contains no provisioning calls.

Only run after review of a cleanup plan. Provider permissions and runner
availability are external prerequisites, not guarantees made by this program.
"""

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import signal
import time

import httpx

from scripts.experiment_guard import terminate_verified


def utc(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Timezone required")
    return stamp.astimezone(timezone.utc)


def validate_plan(plan):
    required = {"pod_name", "experiment_id", "all_in_hourly_usd", "fixed_cost_usd",
                "budget_usd", "cleanup_approved", "all_in_cost_confirmed"}
    if set(plan) != required:
        raise ValueError("Exact cleanup plan schema required; no credentials allowed")
    if plan["cleanup_approved"] is not True or plan["all_in_cost_confirmed"] is not True:
        raise ValueError("Reviewed cleanup authority and full costs required")
    if not re.fullmatch(r"[a-f0-9]{32}", plan["experiment_id"]):
        raise ValueError("Unique random 128-bit experiment identifier required")
    if plan["pod_name"] != "inferenceflow-experiment-" + plan["experiment_id"]:
        raise ValueError("Exact experiment pod name required")
    rate, fixed, budget = (Decimal(str(plan[k])) for k in
                           ("all_in_hourly_usd", "fixed_cost_usd", "budget_usd"))
    if not all(v.is_finite() for v in (rate, fixed, budget)):
        raise ValueError("Finite costs required")
    if rate <= 0 or fixed < 0 or not 0 < budget <= 10 or fixed >= budget * Decimal(".7"):
        raise ValueError("Costs must allow reserve within budget <=10")
    if fixed + 2 * rate >= budget * Decimal(".7"):
        raise ValueError("Two-hour all-in estimate must stay below 70% of budget")
    return rate, fixed, budget


def inventory(client):
    rows, cursor, seen = [], None, set()
    for _ in range(20):
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        response = client.get("/pods", params=params)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data.get("pods"), list) or not isinstance(data.get("pagination"), dict):
            raise ValueError("Invalid inventory")
        rows.extend(data["pods"])
        pagination = data["pagination"]
        if pagination.get("hasNextPage") is False:
            return rows
        cursor = pagination.get("nextCursor")
        if not cursor or cursor in seen:
            raise ValueError("Incomplete inventory")
        seen.add(cursor)
    raise ValueError("Inventory page bound exceeded")


def bind_pod(rows, plan, armed_at):
    candidates = [pod for pod in rows if pod.get("name") == plan["pod_name"]]
    if len(candidates) > 1:
        raise ValueError("Ambiguous experiment identity; manual intervention required")
    if not candidates:
        return None
    pod = candidates[0]
    metadata = pod.get("env", {})
    created = utc(pod["createdAt"])
    if (not isinstance(metadata, dict)
            or metadata.get("IF_EXPERIMENT_ID") != plan["experiment_id"]
            or metadata.get("IF_OWNER") != "inferenceflow"
            or not armed_at <= created <= armed_at + timedelta(minutes=10)
            or not re.fullmatch(r"[A-Za-z0-9_-]+", pod.get("id", ""))):
        raise ValueError("Pod does not match approved identity and creation window")
    return {"pod_id": pod["id"], "pod_name": pod["name"],
            "provider_created_at": created.isoformat(), "experiment_id": plan["experiment_id"]}


def verify_bound(pod, receipt):
    if (pod.get("id") != receipt["pod_id"] or pod.get("name") != receipt["pod_name"]
            or pod.get("env", {}).get("IF_EXPERIMENT_ID") != receipt["experiment_id"]
            or utc(pod["createdAt"]) != utc(receipt["provider_created_at"])):
        raise ValueError("Bound pod identity changed")


def state(plan, armed_at, stamp, receipt=None):
    rate, fixed, budget = validate_plan(plan)
    if stamp < armed_at:
        raise ValueError("Clock moved backwards")
    created = utc(receipt["provider_created_at"]) if receipt else armed_at
    seconds = max(0, (stamp - created).total_seconds())
    # Round elapsed compute/disk time up to a full hour for conservative reserve.
    hours = (Decimal(str(seconds)) / 3600).to_integral_value(rounding="ROUND_CEILING")
    estimate = fixed + rate * max(Decimal(1), hours)
    return {"estimated_cost_upper_usd": str(estimate),
            "stop_admissions_required": estimate >= budget * Decimal(".7"),
            "terminate": estimate >= budget * Decimal(".8")
            or stamp >= armed_at + timedelta(minutes=110)}


def cleanup(client, receipt):
    response = client.get("/pods/" + receipt["pod_id"])
    if response.status_code == 404:
        return True
    response.raise_for_status()
    verify_bound(response.json(), receipt)
    return terminate_verified(client, receipt)


def emit(**values):
    print(json.dumps({"observed_at": datetime.now(timezone.utc).isoformat(), **values}), flush=True)


def run(client, plan, armed_at, receipt_path, clock=None, sleep=time.sleep, stopping=lambda: False):
    clock = clock or (lambda: datetime.now(timezone.utc))
    validate_plan(plan)
    # Successful authentication before reporting armed. No read implies DELETE proof.
    rows = inventory(client)
    if any(p.get("name") == plan["pod_name"] for p in rows):
        raise ValueError("Experiment name already exists before arming")
    (receipt_path.parent / "armed.json").write_text(
        json.dumps({"armed_at": armed_at.isoformat()}), encoding="utf-8")
    emit(armed=True, delete_permission_verified=False,
         creation_window_ends=(armed_at + timedelta(minutes=10)).isoformat(),
         terminate_by=(armed_at + timedelta(minutes=110)).isoformat())
    receipt = None
    while clock() < armed_at + timedelta(minutes=119):
        stamp = clock()
        try:
            if receipt is None:
                receipt = bind_pod(inventory(client), plan, armed_at)
                if receipt:
                    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
                    emit(bound=True)
                elif stopping() or stamp >= armed_at + timedelta(minutes=10):
                    emit(armed=False, no_pod_found=True)
                    return
            if receipt:
                response = client.get("/pods/" + receipt["pod_id"])
                if response.status_code == 404:
                    emit(termination_confirmed=True)
                    return
                response.raise_for_status()
                verify_bound(response.json(), receipt)
                current = state(plan, armed_at, stamp, receipt)
                emit(**current)
                if current["terminate"] or stopping() or current["stop_admissions_required"]:
                    # There is no remote admission-pause endpoint. Delete instead
                    # of claiming a log flag prevents further customer execution.
                    if cleanup(client, receipt):
                        emit(termination_confirmed=True)
                        return
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            emit(error_type=type(error).__name__, termination_confirmed=False)
        sleep(10)
    raise RuntimeError("Cleanup deadline reached without verified termination; intervene immediately")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    plan = json.loads(os.environ["CLEANUP_PLAN_JSON"])
    validate_plan(plan)
    key = os.environ.get("RUNPOD_CLEANUP_API_KEY", "")
    if not key:
        raise ValueError("Protected cleanup secret required")
    directory = Path(".runtime/independent-cleanup")
    directory.mkdir(parents=True, exist_ok=True)
    armed_file, receipt_path = directory / "armed.json", directory / "receipt.json"
    stopping = [False]
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *unused: stopping.__setitem__(0, True))
    with httpx.Client(base_url="https://api.runpod.io/v2",
                      headers={"Authorization": "Bearer " + key}, timeout=15,
                      trust_env=False, follow_redirects=False) as client:
        if args.finalize:
            if not armed_file.exists():
                return
            armed = utc(json.loads(armed_file.read_text())["armed_at"])
            receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else bind_pod(
                inventory(client), plan, armed)
            if receipt:
                for _ in range(6):
                    try:
                        if cleanup(client, receipt):
                            emit(termination_confirmed=True)
                            return
                    except httpx.HTTPError as error:
                        emit(error_type=type(error).__name__)
                    time.sleep(10)
                raise RuntimeError("Final cleanup unverified; immediate manual intervention required")
            emit(no_pod_found=True)
            return
        armed = datetime.now(timezone.utc)
        run(client, plan, armed, receipt_path, stopping=lambda: stopping[0])


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Provider response bodies may contain environment credentials.
        raise SystemExit("Independent cleanup failed: " + type(error).__name__) from None
