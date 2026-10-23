"""Actual asyncio worker/HTTP overlap against fake endpoints, never GPU evidence."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from apps.worker.engines import VllmInferenceEngine
from packages.common.config import settings
from packages.common.identity import served_model_name, model_identity


class WorkerOverlap(unittest.TestCase):
    def test_worker_dispatch_reaches_four_overlapping_vllm_http_calls(self):
        from apps.worker.main import main
        async def scenario(trace_path):
            entered, finished = asyncio.Event(), asyncio.Event()
            requests = completions = 0
            sent = False
            async def engine_api(request):
                nonlocal requests
                if request.url.path == "/health":
                    return httpx.Response(200)
                if request.url.path == "/v1/models":
                    return httpx.Response(200, json={"data": [{"id": served_model_name()}]})
                if request.url.path == "/metrics":
                    return httpx.Response(200, text="vllm:num_requests_running 4\nvllm:num_requests_waiting 0\nvllm:kv_cache_usage_perc 0.3\n")
                body = json.loads(request.content)
                if body["messages"][0]["content"] != "Say ready":
                    requests += 1
                    if requests == 4:
                        entered.set()
                    await asyncio.wait_for(entered.wait(), timeout=3)
                    await asyncio.sleep(.02)
                return httpx.Response(200, json={"choices": [{"message": {"content": "test"}, "finish_reason": "stop"}],
                                                "usage": {"prompt_tokens": 5, "completion_tokens": 1}})
            async def control_api(request):
                nonlocal sent, completions
                if request.url.path.endswith("register"):
                    self.assertEqual(json.loads(request.content)["capacity"], 4)
                    return httpx.Response(200, json={"worker_token": "unit-only"})
                if request.url.path.endswith("poll"):
                    items = [] if sent else [{"id": f"r-{i}", "epoch": 1, "identity": model_identity(),
                                               "payload": {"messages": [{"role": "user", "content": "PRIVATE_SENTINEL"}],
                                                           "max_output_tokens": 4, "temperature": 0, "top_p": 1}} for i in range(4)]
                    sent = True
                    return httpx.Response(200, json={"items": items})
                if request.url.path.endswith("finalize"):
                    completions += 1
                    if completions == 4:
                        finished.set()
                    return httpx.Response(200, json={"accepted": True})
                return httpx.Response(200, json={})
            real_client = httpx.AsyncClient
            def client_factory(*args, **kwargs):
                handler = control_api if "control" in str(kwargs.get("base_url", "")) else engine_api
                return real_client(*args, **kwargs, transport=httpx.MockTransport(handler))
            with patch.object(settings(), "execution_mode", "vllm"), patch.object(settings(), "worker_capacity", 4), \
                    patch.object(settings(), "worker_trace_path", str(trace_path)), \
                    patch.dict("os.environ", {"CONTROL_PLANE_URL": "https://control.invalid"}), \
                    patch("httpx.AsyncClient", side_effect=client_factory), patch("builtins.print"):
                task = asyncio.create_task(main())
                try:
                    await asyncio.wait_for(finished.wait(), timeout=5)
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
            self.assertEqual(requests, 4)
            self.assertEqual(completions, 4)
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "overlap.jsonl"
            asyncio.run(scenario(trace))
            text = trace.read_text(encoding="utf-8")
            self.assertNotIn("PRIVATE_SENTINEL", text)
            rows = [json.loads(line) for line in text.splitlines()]
            self.assertEqual(max(r["worker_http_inflight"] for r in rows), 4)
            self.assertEqual(sum(r["event"] == "end" for r in rows), 4)

    def test_cancelled_http_request_releases_overlap_slot(self):
        async def scenario():
            engine = VllmInferenceEngine()
            async def pending(item):
                await asyncio.sleep(60)
            with patch.object(engine, "_execute", side_effect=pending):
                task = asyncio.create_task(engine.execute({"id": "cancelled"}))
                await asyncio.sleep(0)
                self.assertEqual(engine.overlap.active, 1)
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            self.assertEqual(engine.overlap.snapshot()["worker_http_inflight"], 0)
            await engine.client.aclose()
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
