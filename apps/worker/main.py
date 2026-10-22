import asyncio
import os
import httpx
from apps.worker.engines import MockInferenceEngine, VllmInferenceEngine
from packages.common.config import settings


async def main():
    cfg = settings()
    if cfg.environment != "development" and not os.getenv("CONTROL_PLANE_URL", "").startswith("https://"):
        raise ValueError("Worker requires an HTTPS control plane")
    engine = MockInferenceEngine() if cfg.execution_mode == "mock" else VllmInferenceEngine()
    await engine.ready()
    async with httpx.AsyncClient(
        base_url=os.getenv("CONTROL_PLANE_URL", "http://localhost:8080"), timeout=30, trust_env=False
    ) as client:
        r = await client.post(
            "/internal/workers/register",
            headers={"Authorization": "Bearer " + cfg.worker_bootstrap_token},
            json={
                "id": os.getenv("WORKER_ID", "local-worker"),
                "model": "qwen3-4b",
                "capacity": 16,
                "revision": cfg.model_revision,
                "provider_instance_id": os.getenv("PROVIDER_INSTANCE_ID"),
            },
        )
        r.raise_for_status()
        client.headers["Authorization"] = "Bearer " + r.json()["worker_token"]

        async def execute(item):
            try:
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
            for attempt in range(3):
                try:
                    r = await client.post("/internal/workers/requests/" + item["id"] + "/finalize", json=payload)
                    if r.status_code == 409:
                        return
                    r.raise_for_status()
                    return
                except httpx.HTTPError:
                    await asyncio.sleep(2**attempt)

        async def heartbeats():
            while True:
                r = await client.post("/internal/workers/heartbeat", json=await engine.telemetry())
                r.raise_for_status()
                await asyncio.sleep(15)

        heartbeat = asyncio.create_task(heartbeats())
        tasks = set()
        try:
            while True:
                if heartbeat.done():
                    await heartbeat
                r = await client.post("/internal/workers/poll")
                r.raise_for_status()
                for item in r.json()["items"]:
                    task = asyncio.create_task(execute(item))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                await asyncio.sleep(0.25)
        finally:
            heartbeat.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
