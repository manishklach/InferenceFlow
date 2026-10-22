import asyncio
import hashlib
import os
import httpx
from packages.common.identity import served_model_name


class MockInferenceEngine:
    async def telemetry(self):
        return {}

    async def ready(self):
        return True

    async def execute(self, item):
        await asyncio.sleep(0.01)
        data = item["payload"]
        content = " ".join(m["content"] for m in data["messages"])
        text = ("MOCK " + hashlib.sha256(content.encode()).hexdigest())[: data["max_output_tokens"]]
        return {
            "output_text": text,
            "input_tokens": item["prompt_tokens"],
            "output_tokens": len(text.encode()),
            "finish_reason": "stop",
        }


class VllmInferenceEngine:
    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=os.getenv("VLLM_URL", "http://127.0.0.1:8000"),
            headers={"Authorization": "Bearer " + os.getenv("VLLM_API_KEY", "")},
            timeout=600,
            trust_env=False,
        )

    async def ready(self):
        r = await self.client.get("/health")
        r.raise_for_status()
        models = await self.client.get("/v1/models")
        models.raise_for_status()
        if served_model_name() not in {model["id"] for model in models.json()["data"]}:
            raise RuntimeError("vLLM served identity does not match the configured immutable artifact")
        # Canary proves the engine can actually generate before accepting customer work.
        r = await self.client.post(
            "/v1/chat/completions",
            json={
                "model": served_model_name(),
                "messages": [{"role": "user", "content": "Say ready"}],
                "max_tokens": 4,
                "stream": False,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        r.raise_for_status()
        return bool(r.json()["choices"])

    async def telemetry(self):
        from prometheus_client.parser import text_string_to_metric_families

        values = {}
        try:
            response = await self.client.get("/metrics", timeout=5)
            response.raise_for_status()
            aliases = {
                "vllm:gpu_cache_usage_perc": "kv_cache_usage",
                "vllm:kv_cache_usage_perc": "kv_cache_usage",
                "vllm:num_requests_running": "engine_running",
                "vllm:num_requests_waiting": "engine_waiting",
            }
            for family in text_string_to_metric_families(response.text):
                for sample in family.samples:
                    if sample.name in aliases:
                        values[aliases[sample.name]] = sample.value
            process = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            output, _ = await asyncio.wait_for(process.communicate(), timeout=3)
            if process.returncode == 0:
                values["gpu_utilization"] = max(float(x.strip()) for x in output.decode().splitlines()) / 100
        except Exception:
            pass
        return values

    async def execute(self, item):
        p = item["payload"]
        r = await self.client.post(
            "/v1/chat/completions",
            json={
                "model": served_model_name(),
                "messages": p["messages"],
                "max_tokens": p["max_output_tokens"],
                "temperature": p["temperature"],
                "top_p": p["top_p"],
                "stream": False,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        r.raise_for_status()
        data = r.json()
        choice = data["choices"][0]
        usage = data.get("usage", {})
        return {
            "output_text": choice["message"]["content"],
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "finish_reason": choice["finish_reason"],
        }
