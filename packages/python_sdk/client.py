import time
import uuid
import httpx


class InferenceFlowClient:
    def __init__(self, api_key: str, base_url: str = "http://localhost:8080", timeout: float = 30):
        self.client = httpx.Client(base_url=base_url, headers={"Authorization": "Bearer " + api_key}, timeout=timeout)

    def _call(self, method, path, **kwargs):
        for attempt in range(4):
            try:
                response = self.client.request(method, path, **kwargs)
                if response.status_code not in (429, 502, 503, 504):
                    response.raise_for_status()
                    return response.json()
            except httpx.TransportError:
                if attempt == 3:
                    raise
            time.sleep(min(8, 2**attempt))
        response.raise_for_status()

    def create_job(self, requests, model="qwen3-4b", tier="standard", idempotency_key=None, experiment_readiness=None, **kwargs):
        headers = {"Idempotency-Key": idempotency_key or str(uuid.uuid4())}
        if experiment_readiness:
            headers["X-Experiment-Readiness"] = experiment_readiness
        return self._call(
            "POST",
            "/v1/jobs",
            headers=headers,
            json={"model": model, "tier": tier, "requests": requests, **kwargs},
        )

    def get_job(self, job_id):
        return self._call("GET", "/v1/jobs/" + job_id)

    def wait_for_job(self, job_id, timeout=300, poll_interval=1):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.get_job(job_id)
            if job["status"] in ("succeeded", "failed", "partially_succeeded", "canceled", "expired"):
                return job
            if "usage_mismatch" in job["error_summary"]:
                raise RuntimeError("Billing reconciliation required")
            time.sleep(poll_interval)
        raise TimeoutError(job_id)

    def get_results(self, job_id, cursor=0, limit=100):
        return self._call("GET", f"/v1/jobs/{job_id}/results", params={"cursor": cursor, "limit": limit})

    def cancel_job(self, job_id):
        return self._call("POST", f"/v1/jobs/{job_id}/cancel")

    def get_models(self):
        return self._call("GET", "/v1/models")

    def get_wallet(self):
        return self._call("GET", "/v1/wallet")

    def get_performance(self):
        return self._call("GET", "/v1/performance")

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
