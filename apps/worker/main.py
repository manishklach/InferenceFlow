import asyncio
import os
import time
import httpx
from apps.worker.engines import MockInferenceEngine, VllmInferenceEngine
from packages.common.config import settings
from packages.common.identity import model_identity


async def control_post(client, path, *, retry_seconds=120, accepted_statuses=(), **kwargs):
    """Retry temporary outages with the same credential, lease epoch and payload.

    Never re-enroll on an authorization failure: registration changes the worker
    generation and could invalidate in-flight work. The provider watchdog remains
    responsible for terminating a paid resource if this bounded recovery fails.
    """
    deadline = time.monotonic() + retry_seconds
    attempt = 0
    failure: BaseException | None = None
    while True:
        if attempt and time.monotonic() >= deadline:
            raise RuntimeError("Control-plane recovery deadline exceeded") from failure
        try:
            remaining = max(0.001, deadline - time.monotonic())
            async with asyncio.timeout(remaining):
                response = await client.post(path, timeout=min(30, remaining), **kwargs)
            if response.status_code in accepted_statuses:
                return response
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429 and exc.response.status_code < 500:
                raise
            failure = exc
        except (httpx.TransportError, asyncio.TimeoutError) as exc:
            failure = exc
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Control-plane recovery deadline exceeded") from failure
        # Deliberately omit URL, credentials, response body and request content.
        print('{"event":"worker_control_retry"}', flush=True)
        await asyncio.sleep(min(15, 2 ** min(attempt, 4), remaining))
        attempt += 1


async def main():
    cfg = settings()
    if cfg.execution_mode not in {"mock", "vllm"}:
        raise ValueError("Unsupported execution mode")
    if cfg.environment != "development" and not os.getenv("CONTROL_PLANE_URL", "").startswith("https://"):
        raise ValueError("Worker requires an HTTPS control plane")
    engine = MockInferenceEngine() if cfg.execution_mode == "mock" else VllmInferenceEngine()
    if not await engine.ready():
        raise RuntimeError("Inference engine readiness canary failed")
    async with httpx.AsyncClient(
        base_url=os.getenv("CONTROL_PLANE_URL", "http://localhost:8080"), timeout=30, trust_env=False
    ) as client:
        r = await control_post(client,
            "/internal/workers/register",
            headers={"Authorization": "Bearer " + cfg.worker_bootstrap_token},
            json={
                "id": os.getenv("WORKER_ID", "local-worker"),
                "model": "qwen3-4b",
                "capacity": cfg.worker_capacity,
                # Operator records actual engine load time from startup logs; canary time is not model load time.
                "model_loading_seconds": float(os.getenv("WORKER_MODEL_LOADING_SECONDS", "0")),
                **model_identity(),
                "provider_instance_id": os.getenv("PROVIDER_INSTANCE_ID"),
            },
        )
        r.raise_for_status()
        client.headers["Authorization"] = "Bearer " + r.json()["worker_token"]

        active: dict[tuple[str, int], dict] = {}
        failures: asyncio.Queue[BaseException] = asyncio.Queue()

        async def execute(item):
            try:
                if item["identity"] != model_identity():
                    raise ValueError("Control plane assigned an incompatible model identity")
                payload = await engine.execute(item)
            except httpx.HTTPStatusError as exc:
                payload = {
                    "error": "transient"
                    if exc.response.status_code >= 500 or exc.response.status_code == 429
                    else "permanent"
                }
            except Exception:
                payload = {"error": "transient"}
            payload["epoch"] = item["epoch"]
            # A lost finalization response is safe: retries are fenced; recovery never double bills.
            await control_post(client, "/internal/workers/requests/" + item["id"] + "/finalize",
                               json=payload, accepted_statuses=(404, 409))
            active.pop((item["id"], item["epoch"]), None)

        async def heartbeats():
            while True:
                await control_post(client,
                    "/internal/workers/heartbeat", json={**await engine.telemetry(), "active": list(active.values())}
                )
                await asyncio.sleep(15)

        heartbeat = asyncio.create_task(heartbeats())
        tasks: set[asyncio.Task] = set()
        try:
            while True:
                if not failures.empty():
                    raise await failures.get()
                if heartbeat.done():
                    await heartbeat
                free = cfg.worker_capacity - len(tasks)
                if free <= 0:
                    await asyncio.sleep(0.25)
                    continue
                r = await control_post(client, "/internal/workers/poll", json={"available_slots": free})
                for item in r.json()["items"]:
                    active[(item["id"], item["epoch"])] = {"id": item["id"], "epoch": item["epoch"]}
                    task = asyncio.create_task(execute(item))
                    tasks.add(task)

                    def finished(task, identity=(item["id"], item["epoch"])):
                        tasks.discard(task)
                        active.pop(identity, None)
                        error = None if task.cancelled() else task.exception()
                        if error is not None:
                            failures.put_nowait(error)
                            print('{"alert":"worker_task_failed"}', flush=True)

                    task.add_done_callback(finished)
                await asyncio.sleep(0.25)
        finally:
            heartbeat.cancel()
            for task in tasks:
                task.cancel()
            await asyncio.gather(heartbeat, *tasks, return_exceptions=True)
            if isinstance(engine, VllmInferenceEngine):
                await engine.client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
