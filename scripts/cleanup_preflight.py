"""Read-only authentication check for the independent cleanup runner.

Never treats authenticated inventory reads as proof of termination authority.
No resource mutation, inventory details or response bodies are logged.
"""

import json
import os

import httpx


def verify_read_access(client):
    response = client.get("/pods", params={"limit": 1})
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("pods"), list):
        raise ValueError("Unexpected provider inventory schema")
    return {
        "authenticated_pod_read": True,
        "delete_permission_verified": False,
        "watchdog_armed": False,
        "gpu_creation_authorized": False,
    }


def main():
    key = os.environ.get("RUNPOD_CLEANUP_API_KEY", "").strip()
    if not key:
        raise SystemExit("Missing protected environment cleanup secret")
    try:
        with httpx.Client(
            base_url="https://api.runpod.io/v2",
            headers={"Authorization": "Bearer " + key},
            timeout=15,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            print(json.dumps(verify_read_access(client)), flush=True)
    except Exception as error:
        # HTTP exceptions can contain request URLs; never emit provider bodies.
        raise SystemExit("Cleanup preflight failed: " + type(error).__name__) from None


if __name__ == "__main__":
    main()
