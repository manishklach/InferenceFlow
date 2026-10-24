from copy import deepcopy
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from scripts.prearmed_cleanup import bind_pod, cleanup, inventory, run, state, validate_plan


START = datetime(2026, 10, 24, 20, 0, tzinfo=timezone.utc)
IDENTITY = "ab" * 16


def plan():
    return {"pod_name": "inferenceflow-experiment-" + IDENTITY, "experiment_id": IDENTITY,
            "all_in_hourly_usd": "0.61", "fixed_cost_usd": "0.05", "budget_usd": "10",
            "cleanup_approved": True, "all_in_cost_confirmed": True}


def pod():
    return {"id": "exact-pod", "name": plan()["pod_name"],
            "createdAt": (START + timedelta(minutes=1)).isoformat(),
            "env": {"IF_OWNER": "inferenceflow", "IF_EXPERIMENT_ID": IDENTITY}}


@pytest.mark.parametrize("field,value", [
    ("experiment_id", "short"), ("pod_name", "inferenceflow-unrelated"),
    ("cleanup_approved", False), ("all_in_cost_confirmed", False),
    ("all_in_hourly_usd", "NaN"), ("all_in_hourly_usd", "0"),
    ("all_in_hourly_usd", "5"), ("fixed_cost_usd", "-1"), ("budget_usd", "11"),
])
def test_plan_rejects_unsafe_identity_authority_and_cost(field, value):
    candidate = plan()
    candidate[field] = value
    with pytest.raises(ValueError):
        validate_plan(candidate)


def test_plan_disallows_extra_fields_including_credentials():
    candidate = plan()
    candidate["api_key"] = "not-a-real-key"
    with pytest.raises(ValueError):
        validate_plan(candidate)


def test_budget_includes_fixed_cost_hour_rounding_and_early_deadline():
    candidate = plan()
    assert state(candidate, START, START)["estimated_cost_upper_usd"] == "0.66"
    assert state(candidate, START, START + timedelta(minutes=61))["estimated_cost_upper_usd"] == "1.27"
    assert not state(candidate, START, START + timedelta(minutes=109))["terminate"]
    assert state(candidate, START, START + timedelta(minutes=110))["terminate"]


def test_binding_ignores_unrelated_and_rejects_ambiguous_preexisting_or_missing_marker():
    assert bind_pod([{"name": "another-project"}], plan(), START) is None
    assert bind_pod([pod()], plan(), START)["pod_id"] == "exact-pod"
    for rows in ([pod(), pod()], [{**pod(), "env": {}}],
                 [{**pod(), "createdAt": (START - timedelta(seconds=1)).isoformat()}],
                 [{**pod(), "createdAt": (START + timedelta(minutes=11)).isoformat()}]):
        with pytest.raises(ValueError):
            bind_pod(rows, plan(), START)


def test_inventory_requires_complete_pagination():
    calls = []

    def respond(request):
        calls.append(request.url.params.get("cursor"))
        page = 1 if len(calls) == 1 else 2
        return httpx.Response(200, json={"pods": [{"name": str(page)}], "pagination": {
            "hasNextPage": page == 1, "nextCursor": "second" if page == 1 else None}})

    with httpx.Client(base_url="https://unit.invalid", transport=httpx.MockTransport(respond)) as client:
        assert len(inventory(client)) == 2
    assert calls == [None, "second"]


def test_cleanup_rechecks_identity_and_requires_fresh_404():
    calls = []
    active = pod()
    deleted = False

    def respond(request):
        nonlocal deleted
        calls.append(request.method)
        if request.method == "DELETE":
            deleted = True
            return httpx.Response(204)
        return httpx.Response(404) if deleted else httpx.Response(200, json=active)

    receipt = bind_pod([pod()], plan(), START)
    with httpx.Client(base_url="https://unit.invalid", transport=httpx.MockTransport(respond)) as client:
        active = deepcopy(pod())
        active["env"]["IF_EXPERIMENT_ID"] = "foreign"
        with pytest.raises(ValueError):
            cleanup(client, receipt)
        assert "DELETE" not in calls
        active = pod()
        assert cleanup(client, receipt)
        assert calls[-2:] == ["DELETE", "GET"]


def test_prearmed_controller_binds_future_pod_and_terminates_at_deadline(tmp_path):
    stamp = [START]
    calls = []
    lists = 0
    deleted = False

    def respond(request):
        nonlocal lists, deleted
        calls.append(request.method)
        if request.url.path == "/pods":
            lists += 1
            return httpx.Response(200, json={"pods": [] if lists == 1 else [pod()],
                                            "pagination": {"hasNextPage": False}})
        if request.method == "DELETE":
            deleted = True
            return httpx.Response(204)
        return httpx.Response(404) if deleted else httpx.Response(200, json=pod())

    def advance(seconds):
        stamp[0] = START + timedelta(minutes=110)

    with httpx.Client(base_url="https://unit.invalid", transport=httpx.MockTransport(respond)) as client:
        run(client, plan(), START, tmp_path / "receipt.json", clock=lambda: stamp[0], sleep=advance)
    assert deleted
    assert (tmp_path / "receipt.json").exists()
    assert calls.count("DELETE") == 1
    assert set(calls) <= {"GET", "DELETE"}


def test_preexisting_pod_cannot_arm_or_write_heartbeat(tmp_path):
    with httpx.Client(base_url="https://unit.invalid", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"pods": [pod()], "pagination": {"hasNextPage": False}})
    )) as client:
        with pytest.raises(ValueError):
            run(client, plan(), START, tmp_path / "receipt.json")
    assert not (tmp_path / "armed.json").exists()


def test_delete_denial_is_not_reported_as_termination():
    receipt = bind_pod([pod()], plan(), START)

    def respond(request):
        return httpx.Response(403) if request.method == "DELETE" else httpx.Response(200, json=pod())

    with httpx.Client(base_url="https://unit.invalid", transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            cleanup(client, receipt)


def test_unconfirmed_delete_is_not_success():
    with httpx.Client(base_url="https://unit.invalid", transport=httpx.MockTransport(
        lambda request: httpx.Response(204) if request.method == "DELETE"
        else httpx.Response(200, json=pod())
    )) as client:
        assert not cleanup(client, bind_pod([pod()], plan(), START))


def test_empty_creation_window_expires_without_mutation(tmp_path):
    stamp = [START]
    calls = []

    def respond(request):
        calls.append(request.method)
        return httpx.Response(200, json={"pods": [], "pagination": {"hasNextPage": False}})

    def advance(seconds):
        stamp[0] += timedelta(minutes=10)

    with httpx.Client(base_url="https://unit.invalid", transport=httpx.MockTransport(respond)) as client:
        run(client, plan(), START, tmp_path / "receipt.json", clock=lambda: stamp[0], sleep=advance)
    assert set(calls) == {"GET"}
    assert not (tmp_path / "receipt.json").exists()


def test_interruption_requests_cleanup_and_retries_provider_failure(tmp_path):
    stamp = [START + timedelta(minutes=1)]
    lists = deletes = 0
    deleted = False

    def respond(request):
        nonlocal lists, deletes, deleted
        if request.url.path == "/pods":
            lists += 1
            return httpx.Response(200, json={"pods": [] if lists == 1 else [pod()],
                                            "pagination": {"hasNextPage": False}})
        if request.method == "DELETE":
            deletes += 1
            if deletes == 1:
                return httpx.Response(503)
            deleted = True
            return httpx.Response(204)
        return httpx.Response(404) if deleted else httpx.Response(200, json=pod())

    def advance(seconds):
        stamp[0] += timedelta(seconds=seconds)

    with httpx.Client(base_url="https://unit.invalid", transport=httpx.MockTransport(respond)) as client:
        run(client, plan(), START, tmp_path / "receipt.json", clock=lambda: stamp[0],
            sleep=advance, stopping=lambda: True)
    assert deleted and deletes == 2
