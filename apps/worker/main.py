import asyncio
import os
import httpx
from apps.worker.engines import MockInferenceEngine, VllmInferenceEngine
from packages.common.config import settings
from packages.common.identity import model_identity


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
        r = await client.post(
            "/internal/workers/register",
            headers={"Authorization": "Bearer " + cfg.worker_bootstrap_token},
            json={
                "id": os.getenv("WORKER_ID", "local-worker"),
                "model": "qwen3-4b",
                "capacity": 16,
                **model_identity(),
                "provider_instance_id": os.getenv("PROVIDER_INSTANCE_ID"),
            },
        )
        r.raise_for_status()
        client.headers["Authorization"] = "Bearer " + r.json()["worker_token"]

        active: dict[tuple[str, int], dict] = {}

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
            attempt = 0
            while True:
                try:
                    r = await client.post("/internal/workers/requests/" + item["id"] + "/finalize", json=payload)
                    if r.status_code in (404, 409):
                        active.pop((item["id"], item["epoch"]), None)
                        return
                    r.raise_for_status()
                    active.pop((item["id"], item["epoch"]), None)
                    return
                except httpx.HTTPError:
                    await asyncio.sleep(min(15, 2 ** min(attempt, 4)))
                    attempt += 1

        async def heartbeats():
            while True:
                r = await client.post(
                    "/internal/workers/heartbeat", json={**await engine.telemetry(), "active": list(active.values())}
                )
                r.raise_for_status()
                await asyncio.sleep(15)

        heartbeat = asyncio.create_task(heartbeats())
        tasks: set[asyncio.Task] = set()
        try:
            while True:
                if heartbeat.done():
                    await heartbeat
                free = 16 - len(tasks)
                if free <= 0:
                    await asyncio.sleep(0.25)
                    continue
                r = await client.post("/internal/workers/poll", json={"available_slots": free})
                r.raise_for_status()
                for item in r.json()["items"]:
                    active[(item["id"], item["epoch"])] = {"id": item["id"], "epoch": item["epoch"]}
                    task = asyncio.create_task(execute(item))
                    tasks.add(task)

                    def finished(task, identity=(item["id"], item["epoch"])):
                        tasks.discard(task)
                        active.pop(identity, None)
                        if not task.cancelled() and task.exception() is not None:
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
