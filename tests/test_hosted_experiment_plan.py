from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from scripts.experiment_plan import Stage, run_plan
from scripts.experiment_telemetry import PodReader, Collector, events
from scripts.hosted_experiment import child_environment, validate_session, verify_pod
from scripts.github_real_host import experiment_evidence


class PlanTests(unittest.TestCase):
    def execute(self, folder, *, audit_pass=True, coverage_pass=True, deadline=1000):
        calls = []
        stages = (Stage("smoke", "baseline", 10, 30), Stage("next", "adaptive", 100, 30))

        def stage_run(stage, seconds):
            calls.append(stage.name)
            # Intent must be durable before this admission callback runs.
            checkpoint = json.loads((folder/"checkpoint.json").read_text())
            self.assertEqual(checkpoint["in_progress"]["phase"], "admission_intent")
            return {"successful_requests": stage.count}

        try:
            result = run_plan(folder, deadline, transition=lambda _: None, execute=stage_run,
                audit=lambda *_: {"passed": audit_pass}, coverage=lambda *_: {"passed": coverage_pass},
                stages=stages, clock=lambda: 0)
        except RuntimeError:
            result = json.loads((folder/"checkpoint.json").read_text())
        return result, calls

    def test_full_plan_and_ambiguous_replay_refusal(self):
        with TemporaryDirectory() as folder:
            result, calls = self.execute(Path(folder))
            self.assertEqual(result["status"], "completed")
            self.assertEqual(calls, ["smoke", "next"])
            with self.assertRaises(RuntimeError):
                run_plan(Path(folder), 1000, transition=lambda _: None, execute=lambda *_: None,
                         audit=lambda *_: None, coverage=lambda *_: None)

    def test_failed_audit_or_coverage_prevents_next_admission(self):
        for options in ({"audit_pass": False}, {"coverage_pass": False}):
            with TemporaryDirectory() as folder:
                result, calls = self.execute(Path(folder), **options)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(calls, ["smoke"])

    def test_insufficient_time_never_admits(self):
        with TemporaryDirectory() as folder:
            result, calls = self.execute(Path(folder), deadline=100)
            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(calls, [])


class ProviderReadTests(unittest.TestCase):
    def test_authenticated_provider_surface_is_get_only(self):
        requests = []

        def respond(request):
            requests.append(request)
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.host, "api.runpod.io")
            return httpx.Response(200, json={"pods": []} if request.url.path.endswith("/pods") else {"id": "owned"})

        reader = PodReader("test-read-only", httpx.MockTransport(respond))
        reader.authenticate()
        self.assertEqual(reader.pod("owned")["id"], "owned")
        with self.assertRaises(ValueError):
            reader.pod("../other")
        reader.close()
        self.assertEqual(len(requests), 2)

    def test_sse_cursor_and_deduplication(self):
        record = {"source": "container", "ts": "2026-10-26T00:00:00Z", "line": "engine starting"}
        parsed = list(events(["id: opaque/001", "data: "+json.dumps(record), ""]))
        self.assertEqual(parsed, [("opaque/001", record)])
        with TemporaryDirectory() as folder:
            collector = Collector(None, "owned", Path(folder))
            output = io.StringIO()
            collector.accept(*parsed[0], output)
            collector.accept(*parsed[0], output)
            self.assertEqual(len(output.getvalue().splitlines()), 1)
            self.assertEqual(collector.cursor, "opaque/001")
            with self.assertRaises(RuntimeError):
                collector.healthy()


class SessionTests(unittest.TestCase):
    def test_pre_session_failure_diagnostics_are_preserved_without_connection(self):
        with TemporaryDirectory() as folder:
            runtime = Path(folder)
            (runtime / "experiment-error.json").write_text('{"error_type":"RuntimeError"}')
            (runtime / "experiment-driver.log").write_text("Hosted experiment failed")
            (runtime / "runner-connection.json").write_text("private connection")
            files = experiment_evidence(runtime)
            self.assertIn("diagnostics/experiment-error.json", files)
            self.assertIn("diagnostics/experiment-driver.log", files)
            self.assertNotIn("private connection", files.values())

    def session(self):
        return {"experiment_id": "ab"*16, "gpu_id": "NVIDIA H100 80GB HBM3", "data_center_id": "CA-MTL-1",
                "disk_gb": 80, "all_in_hourly_usd": "4.01", "budget_usd": "6", "max_runtime_minutes": 45}

    def pod(self):
        now = datetime.now(timezone.utc)
        return {"id": "owned", "name": "inferenceflow-experiment-"+"ab"*16, "cloud": "SECURE",
            "dataCenterId": "CA-MTL-1", "gpu": {"id": "NVIDIA H100 80GB HBM3", "count": 1},
            "disk": 80, "ports": [], "mounts": {}, "globalNetworking": False, "cost": 3.99,
            "createdAt": now.isoformat(), "env": {"IF_EXPERIMENT_ID": "ab"*16, "IF_OWNER": "inferenceflow",
                "IF_CREATED_BY": "explicit-operator-approval", "IF_CONTROL_RUN_ID": "123-1",
                "IF_WATCHDOG_RUN_ID": "456", "IF_WATCHDOG_RUN_ATTEMPT": "1",
                "IF_TERMINATE_BY": (now+timedelta(minutes=40)).isoformat()}}

    def test_wrong_run_overquote_or_cutoff_cannot_execute(self):
        session = self.session()
        validate_session(session)
        self.assertGreater(verify_pod(self.pod(), session, "123-1"), 0)
        for mutate in (lambda p: p["env"].update(IF_CONTROL_RUN_ID="123-2"),
                       lambda p: p.update(cost=5), lambda p: p.update(ports=["8000/http"]),
                       lambda p: p["env"].pop("IF_TERMINATE_BY")):
            pod = self.pod()
            mutate(pod)
            with self.assertRaises((RuntimeError, KeyError)):
                verify_pod(pod, session, "123-1")

    def test_api_child_never_receives_provider_or_oidc_keys(self):
        with patch.dict(os.environ, {"RUNPOD_EXPERIMENT_READ_KEY": "private", "AUTH0_STAGING_CLIENT_SECRET": "private",
                                    "HOST_COMMAND_GITHUB_TOKEN": "private"}):
            env = child_environment({"CONTROL_PLANE_URL": "https://example.invalid", "INFERENCEFLOW_API_KEY": "synthetic",
                                     "METRICS_TOKEN": "metrics", "WORKER_BOOTSTRAP_TOKEN": "bootstrap"})
        self.assertNotIn("private", env.values())
        self.assertNotIn("WORKER_BOOTSTRAP_TOKEN", env)

    def test_provider_networking_readback_requires_explicitly_disabled(self):
        for value in (False, {"enabled": False}):
            pod = self.pod()
            pod["globalNetworking"] = value
            self.assertGreater(verify_pod(pod, self.session(), "123-1"), 0)
        for value in (True, {"enabled": True}, {}, None, "false", {"enabled": 0}):
            pod = self.pod()
            pod["globalNetworking"] = value
            with self.assertRaises(RuntimeError):
                verify_pod(pod, self.session(), "123-1")


if __name__ == "__main__":
    unittest.main()
