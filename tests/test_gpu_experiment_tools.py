"""CPU-only checks: run with unittest to avoid the platform pytest DB fixtures."""
import argparse
import json
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from scripts.gpu_experiment import batches, collect, live_run, main, poll_interval, summarize, workload


class ExperimentTools(unittest.TestCase):
    def test_polling_respects_existing_tenant_rate_limit(self):
        for jobs in (1, 10):
            self.assertLessEqual((jobs + 1) * 60 / poll_interval(jobs), 60)

    def test_request_counts_and_api_batch_limit(self):
        for count in (10, 100, 1000):
            rows = workload(count, "fixture")
            self.assertEqual(len(rows), count)
            self.assertEqual(len({r["custom_id"] for r in rows}), count)
            self.assertTrue(all(len(batch) <= 100 for batch in batches(rows)))
            self.assertEqual(len(batches(rows)), (count + 99) // 100)
            self.assertTrue(all(r["max_output_tokens"] <= 256 for r in rows))
        with self.assertRaises(ValueError):
            workload(1001, "fixture")

    def test_explicit_execution_gate_before_network(self):
        for function in (live_run, collect):
            with self.assertRaisesRegex(SystemExit, "No execution authorized"):
                function(argparse.Namespace(execute=False))

    def test_denominators_include_failed_jobs(self):
        jobs = [{"total": 10, "status": "succeeded", "created_at": "2026-10-23T00:00:00Z",
                 "completed_at": "2026-10-23T00:01:00Z"}, {"total": 10, "status": "failed"}]
        rows = [{"status": "succeeded", "usage": {"input_tokens": 10, "output_tokens": 10}} for _ in range(10)]
        report = summarize(jobs, rows, 100, Decimal("0.01"))
        self.assertEqual(report["all_accepted_jobs_successful_within_hour"], .5)
        self.assertEqual(report["all_accepted_requests_successful_within_hour_lower_bound"], .5)
        self.assertEqual(report["unsuccessful_or_unfinished_requests"], 10)
        self.assertEqual(Decimal(report["provided_cost_per_million_total_tokens_usd"]), Decimal(50))
        self.assertEqual(report["successful_job_seconds"]["p95"], 60)

    def test_no_samples_is_unknown(self):
        report = summarize([], [], 0)
        self.assertIsNone(report["output_tokens_per_second"])
        self.assertIsNone(report["provided_cost_per_million_total_tokens_usd"])
        self.assertIsNone(report["all_accepted_jobs_successful_within_hour"])

    def test_telemetry_failure_preserves_missing_data(self):
        import httpx
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "samples.jsonl"
            with patch.object(httpx.Client, "get", side_effect=RuntimeError("unavailable")), \
                    patch("scripts.gpu_experiment.subprocess.run", side_effect=FileNotFoundError), \
                    patch("scripts.gpu_experiment.time.monotonic", side_effect=[0, 0, 2]), \
                    patch("scripts.gpu_experiment.time.sleep"), patch("builtins.print"):
                collect(argparse.Namespace(execute=True, output=str(path), seconds=1, interval=1))
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["metrics_error"], "RuntimeError")
            self.assertEqual(data["hardware_error"], "FileNotFoundError")
            self.assertNotIn("gpu_utilization", data)

    def test_thousand_request_driver_against_mock_api(self):
        self.driver_case("baseline", 4)

    def test_sequential_driver_requires_one_slot(self):
        self.driver_case("sequential", 1)

    def driver_case(self, policy, cap):
        import httpx
        import packages.python_sdk
        from packages.python_sdk import InferenceFlowClient

        submitted = []
        revision = "1cfa9a7208912126459214e8b04321603b3df60c"

        def view(index):
            return {"id": str(index), "status": "succeeded", "total": len(submitted[index]),
                    "error_summary": [], "created_at": "2026-10-23T00:00:00Z",
                    "completed_at": "2026-10-23T00:01:00Z"}

        def respond(request):
            path = request.url.path
            if path == "/v1/models":
                return httpx.Response(200, json={"models": [{"execution_mode": "vllm", "revision": revision,
                                                             "tokenizer_revision": revision}]})
            if path == "/v1/jobs" and request.method == "POST":
                rows = json.loads(request.content)["requests"]
                submitted.append(rows)
                self.assertTrue(request.headers["Idempotency-Key"].startswith("gpu-experiment-"))
                return httpx.Response(202, json=view(len(submitted) - 1))
            if path.startswith("/v1/jobs/"):
                index = int(path.split("/")[3])
                if path.endswith("/results"):
                    return httpx.Response(200, json={"next_cursor": None, "items": [
                        {"custom_id": row["custom_id"], "status": "succeeded", "output_text": "Test response",
                         "usage": {"input_tokens": 10, "output_tokens": 2}} for row in submitted[index]]})
                return httpx.Response(200, json=view(index))
            if path == "/v1/wallet/transactions":
                return httpx.Response(200, json={"items": [], "next_cursor": None})
            if path == "/internal/scheduling/report":
                return httpx.Response(200, json={"workers": [{"id": "unit", "mode": "vllm", "hard_limit": 4,
                    "provider_instance_id": "unit-instance", "telemetry_fresh": True}],
                    "configuration": {"public_beta_enabled": False, "stripe_enabled": False, "scheduler_v2_enabled": False,
                    "max_inflight": cap, "estimator_calibrated": False,
                    "adaptive_dispatch_enabled": False, "provisioning_enabled": False, "execution_mode": "vllm"}})
            return httpx.Response(200, json={})

        def make_client(key, origin):
            client = InferenceFlowClient(key, origin)
            client.client.close()
            client.client = httpx.Client(base_url=origin, transport=httpx.MockTransport(respond))
            return client

        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {"CONTROL_PLANE_URL": "https://experiment.invalid", "INFERENCEFLOW_API_KEY": "unit-only", "METRICS_TOKEN": "unit-only"}), \
                patch.object(packages.python_sdk, "InferenceFlowClient", side_effect=make_client), patch("builtins.print"):
            target = Path(directory) / "run"
            live_run(argparse.Namespace(execute=True, output=str(target), count=1000,
                                       run_id="unit", timeout=30, cost_usd=None, policy=policy))
            report = json.loads((target / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(report["accepted_requests"], 1000)
            self.assertEqual(report["successful_requests"], 1000)
            self.assertEqual(len(submitted), 10)
            self.assertTrue(all(len(rows) == 100 for rows in submitted))
            cost_report = Path(directory) / "cost.json"
            with patch("sys.argv", ["gpu_experiment", "report", "--directories", str(target),
                                    "--cost-usd", "0.70", "--cost-kind", "actual_invoice",
                                    "--cost-reference", "unit-test-coverage-only", "--output", str(cost_report)]):
                main()
            costs = json.loads(cost_report.read_text(encoding="utf-8"))
            self.assertEqual(costs["cost_kind"], "actual_invoice")
            self.assertEqual(Decimal(costs["provided_cost_per_million_total_tokens_usd"]), Decimal("0.70") * 1000000 / 12000)
            with patch("sys.argv", ["gpu_experiment", "report", "--directories", str(target), str(target),
                                    "--cost-usd", "0.70", "--cost-kind", "estimate",
                                    "--cost-reference", "unit-only", "--output", str(cost_report)]):
                with self.assertRaisesRegex(SystemExit, "Duplicate job coverage"):
                    main()

    def test_mock_mode_refused_before_submission(self):
        import packages.python_sdk
        from unittest.mock import MagicMock

        client = MagicMock()
        client.get_models.return_value = {"models": [{"execution_mode": "mock"}]}
        client.__enter__.return_value = client
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {"CONTROL_PLANE_URL": "https://experiment.invalid", "INFERENCEFLOW_API_KEY": "unit-only"}), \
                patch.object(packages.python_sdk, "InferenceFlowClient", return_value=client):
            with self.assertRaisesRegex(SystemExit, "Refusing a mock"):
                live_run(argparse.Namespace(execute=True, output=str(Path(directory) / "run"), count=10,
                                           run_id="unit", timeout=30, cost_usd=None, policy="baseline"))
            client.create_job.assert_not_called()


if __name__ == "__main__":
    unittest.main()
