import asyncio
import hashlib
import os
import time
import json
from datetime import datetime, timezone
from pathlib import Path
from collections import deque
from statistics import median
import httpx
from packages.common.identity import served_model_name
from packages.common.config import settings


class OverlapTracker:
    """HTTP overlap is observable here; GPU sequence batching must come from vLLM."""
    def __init__(self):
        self.started = self.changed = time.monotonic()
        self.active = self.peak = self.completed = self.errors = self.trace_errors = 0
        self.request_seconds = self.overlap_seconds = 0.0
        self.idle_seconds = 0.0

    def observe(self):
        stamp = time.monotonic()
        elapsed = max(0, stamp - self.changed)
        self.request_seconds += elapsed * self.active
        self.overlap_seconds += elapsed if self.active > 1 else 0
        self.idle_seconds += elapsed if self.active == 0 else 0
        self.changed = stamp
        return stamp

    def snapshot(self):
        stamp = self.observe()
        return {"worker_http_inflight": self.active, "worker_http_peak_inflight": self.peak,
                "worker_http_completed": self.completed, "worker_http_errors": self.errors,
                "worker_http_overlap_seconds": self.overlap_seconds,
                "worker_http_request_seconds": self.request_seconds,
                "worker_http_observed_seconds": max(0, stamp - self.started),
                "worker_http_idle_seconds": self.idle_seconds,
                "worker_trace_write_errors": self.trace_errors}


class MockInferenceEngine:
    async def telemetry(self):
        return {}

    async def ready(self):
        return True

    async def execute(self, item):
        await asyncio.sleep(settings().mock_latency_seconds)
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
        self.samples: deque[tuple[float, float, int, int, int]] = deque(maxlen=128)
        self.overlap = OverlapTracker()
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

        values = self.overlap.snapshot()
        recent = [s for s in self.samples if time.monotonic() - s[0] <= 60]
        if recent:
            values["recent_error_rate"] = sum(s[2] for s in recent) / len(recent)
            values["observed_input_tokens_per_second"] = sum(s[3] for s in recent) / 60
            values["observed_output_tokens_per_second"] = sum(s[4] for s in recent) / 60
            if len(recent) >= 16:
                values["latency_ratio"] = median(s[1] for s in recent[-8:]) / max(.001, median(s[1] for s in recent[-16:-8]))
        try:
            response = await self.client.get("/metrics", timeout=5)
            response.raise_for_status()
            aliases = {
                "vllm:gpu_cache_usage_perc": "kv_cache_usage",
                "vllm:kv_cache_usage_perc": "kv_cache_usage",
                "vllm:num_requests_running": "engine_running",
                "vllm:num_requests_waiting": "engine_waiting",
                "vllm:prompt_tokens_total": "engine_prompt_tokens_total",
                "vllm:generation_tokens_total": "engine_output_tokens_total",
            }
            for family in text_string_to_metric_families(response.text):
                for sample in family.samples:
                    if sample.name in aliases:
                        values[aliases[sample.name]] = sample.value
        except Exception:
            pass
        try:
            process = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                output, _ = await asyncio.wait_for(process.communicate(), timeout=3)
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                raise
            if process.returncode == 0:
                rows = [[float(value.strip()) for value in line.split(",")] for line in output.decode().splitlines()]
                values["gpu_utilization"] = max(row[0] for row in rows) / 100
                values["gpu_memory_used_mib"] = sum(row[1] for row in rows)
                values["gpu_memory_total_mib"] = sum(row[2] for row in rows)
        except Exception:
            pass
        return values

    async def execute(self, item):
        start = time.monotonic()
        self.overlap.observe()
        self.overlap.active += 1
        self.overlap.peak = max(self.overlap.peak, self.overlap.active)
        self.trace("start", item)
        result = None
        outcome = "interrupted"
        try:
            result = await self._execute(item)
            outcome = "succeeded"
            self.overlap.completed += 1
        except Exception:
            outcome = "error"
            self.overlap.errors += 1
            self.samples.append((time.monotonic(), time.monotonic() - start, 1, 0, 0))
            raise
        finally:
            self.overlap.observe()
            self.overlap.active -= 1
            self.trace("end", item, outcome=outcome, elapsed_seconds=time.monotonic() - start,
                       input_tokens=(result or {}).get("input_tokens"),
                       output_tokens=(result or {}).get("output_tokens"))
        self.samples.append((time.monotonic(), time.monotonic() - start, 0,
                             result.get("input_tokens") or 0, result.get("output_tokens") or 0))
        return result

    def trace(self, event, item, **extra):
        path = settings().worker_trace_path
        if not path:
            return
        # No prompt, output, URL or credentials; hash request identity for correlation.
        record = {"event": event, "observed_at": datetime.now(timezone.utc).isoformat(),
                  "monotonic_seconds": time.monotonic(), "worker_http_inflight": self.overlap.active,
                  "request_hash": hashlib.sha256(str(item.get("id", "unknown")).encode()).hexdigest()[:24],
                  "epoch": item.get("epoch"), **extra}
        try:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as output:
                output.write(json.dumps(record) + "\n")
            print(json.dumps({"worker_request_trace": record}), flush=True)
        except OSError:
            self.overlap.trace_errors += 1

    async def _execute(self, item):
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
