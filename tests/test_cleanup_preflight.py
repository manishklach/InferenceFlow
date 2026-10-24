import httpx
import pytest

from scripts.cleanup_preflight import verify_read_access


def test_cleanup_preflight_only_reads_and_does_not_claim_delete_permission():
    calls = []

    def respond(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={"pods": [{"id": "unrelated-secret-id"}]})

    with httpx.Client(base_url="https://unit.invalid", transport=httpx.MockTransport(respond)) as client:
        result = verify_read_access(client)
    assert calls == [("GET", "/pods")]
    assert result == {
        "authenticated_pod_read": True,
        "delete_permission_verified": False,
        "watchdog_armed": False,
        "gpu_creation_authorized": False,
    }
    assert "unrelated-secret-id" not in str(result)


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_failed_authentication_or_provider_failure_cannot_pass(status):
    with httpx.Client(
        base_url="https://unit.invalid",
        transport=httpx.MockTransport(lambda request: httpx.Response(status)),
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            verify_read_access(client)


@pytest.mark.parametrize("body", [{}, {"pods": None}, [], {"pods": {}}])
def test_unexpected_inventory_schema_cannot_pass(body):
    with httpx.Client(
        base_url="https://unit.invalid",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
    ) as client:
        with pytest.raises(ValueError):
            verify_read_access(client)
