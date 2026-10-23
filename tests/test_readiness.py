import unittest
from dataclasses import replace
from datetime import datetime, timezone
from packages.common.provider_discovery import Offer, instance_state
from packages.common.provider_selection import WorkloadProfile, compare_workload
from packages.common.config import Settings


class ReadinessTests(unittest.TestCase):
    def test_private_experiment_does_not_require_public_beta(self):
        c = Settings(
            _env_file=None,
            execution_mode="vllm",
            model_revision="a" * 40,
            reviewed_gpu_experiment_enabled=True,
            public_beta_enabled=False,
        )
        c.validate_runtime()
        self.assertFalse(c.public_beta_enabled)
        self.assertFalse(c.provisioning_enabled)
        self.assertFalse(c.stripe_enabled)
        c.reviewed_gpu_experiment_enabled = False
        with self.assertRaises(ValueError):
            c.validate_runtime()
        c.reviewed_gpu_experiment_enabled = True
        c.model_revision = "z" * 40
        with self.assertRaises(ValueError):
            c.validate_runtime()

    def test_workload_cost_can_favor_higher_hourly_rate(self):
        stamp = datetime.now(timezone.utc)
        offer = Offer("vast", "slow", "gpu", "region", 1, 100000, stamp.isoformat(), "synthetic", True, 10000, 0, 1)
        slow = WorkloadProfile(offer, True, 100, 10, 60, 0.99, "synthetic-fixture")
        fast = replace(
            slow,
            offer=replace(offer, provider="lambda", offer_id="fast", compute_micro_usd_per_hour=200000),
            input_tokens_per_second=1000,
            output_tokens_per_second=100,
        )
        report = compare_workload([slow, fast], 10000, 1000, 1000, stamp)
        self.assertEqual(report["ranked"][0]["offer_id"], "fast")
        self.assertFalse(report["automatic_provisioning"])
        self.assertEqual(report, compare_workload([fast, slow], 10000, 1000, 1000, stamp))
        for bad in [
            replace(slow, compatible=None),
            replace(slow, reliability=0),
            replace(slow, startup_seconds=None),
            replace(slow, offer=replace(offer, other_micro_usd_per_hour=None)),
        ]:
            self.assertFalse(compare_workload([bad], 10000, 1000, 1000, stamp)["ranked"])
        self.assertFalse(compare_workload([slow], 10000, 1000, 1, stamp)["ranked"])

    def test_inventory_is_not_engine_health(self):
        self.assertEqual(
            instance_state("vast", {"id": 1, "actual_status": "running"})["application_health"], "unverified"
        )
        self.assertEqual(instance_state("lambda", {"id": "a", "status": "booting"})["phase"], "starting")
        self.assertEqual(instance_state("lambda", {"status": "new-vendor-status"})["phase"], "unknown")


class EngineMetricsTests(unittest.IsolatedAsyncioTestCase):
    async def test_pinned_engine_counter_aliases_and_gpu_memory(self):
        import httpx
        from unittest.mock import patch, AsyncMock
        from apps.worker.engines import VllmInferenceEngine

        engine = VllmInferenceEngine()
        await engine.client.aclose()
        engine.client = httpx.AsyncClient(
            base_url="http://unit.invalid",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    text="vllm:num_requests_running 3\nvllm:num_requests_waiting 1\nvllm:gpu_cache_usage_perc 0.4\nvllm:prompt_tokens_total 1000\nvllm:generation_tokens_total 200\n",
                )
            ),
        )
        process = AsyncMock()
        process.returncode = 0
        process.communicate.return_value = (b"42, 1024, 24576\n", b"")
        with patch("asyncio.create_subprocess_exec", return_value=process):
            values = await engine.telemetry()
        self.assertEqual(values["engine_running"], 3)
        self.assertEqual(values["engine_prompt_tokens_total"], 1000)
        self.assertEqual(values["engine_output_tokens_total"], 200)
        self.assertEqual(values["gpu_memory_used_mib"], 1024)
        self.assertEqual(values["gpu_utilization"], 0.42)
        self.assertIn("worker_http_idle_seconds", values)
        await engine.client.aclose()
