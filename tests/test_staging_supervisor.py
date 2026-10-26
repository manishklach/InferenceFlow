import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.staging_supervisor import HealthReadFailed, main, monitor, running_services
from scripts.second_gpu_experiment import prepare


class SupervisionTests(unittest.TestCase):
    def test_cli_persistent_read_failure_still_stops_services_and_records_outcome(self):
        with tempfile.TemporaryDirectory() as folder:
            compose = Path(folder)/"compose.yml"
            compose.touch()
            diagnostics = Path(folder)/"diagnostics"
            with patch("sys.argv", ["supervisor", "--compose-file", str(compose),
                                    "--diagnostics", str(diagnostics)]), \
                    patch("scripts.staging_supervisor.monitor", side_effect=HealthReadFailed("failed")), \
                    patch("scripts.staging_supervisor.subprocess.run", return_value=
                          subprocess.CompletedProcess([], 0, "", "")) as run:
                with self.assertRaises(SystemExit):
                    main()
            self.assertEqual(run.call_args.args[0][-3:], ["stop", "--timeout", "15"])
            self.assertEqual(json.loads((diagnostics/"stopped.json").read_text())["stop_returncode"], 0)

    def test_maintenance_is_bounded_and_never_ignores_postgres(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/"maintenance.json").write_text(json.dumps({"expires_at_epoch": 150}))
            with patch("scripts.staging_supervisor.time.time", return_value=100):
                elapsed = [0]
                monitor([], root, 10, {"postgres", "api"}, root/"STOP",
                        clock=lambda: elapsed[0], sleep=lambda _: elapsed.__setitem__(0, 10),
                        read=Mock(return_value={"postgres"}))
                with self.assertRaisesRegex(RuntimeError, "postgres"):
                    monitor([], root, 10, {"postgres", "api"}, root/"STOP", clock=lambda: 0,
                            read=Mock(return_value=set()))
            with patch("scripts.staging_supervisor.time.time", return_value=151):
                with self.assertRaisesRegex(RuntimeError, "api"):
                    monitor([], root, 10, {"postgres", "api"}, root/"STOP", clock=lambda: 0,
                            read=Mock(return_value={"postgres"}))
    def test_prepares_real_500_request_workloads_without_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/"third"
            plan = prepare(output, validation_count=500)
            self.assertFalse(plan["paid_execution_authorized"])
            for name in ("comparison-500", "interruption-500"):
                self.assertEqual(plan["workloads"][name]["count"], 500)
                self.assertEqual(len(json.loads((output/(name+".json")).read_text())), 500)

    def test_transient_cli_failure_recovers_and_retains_stderr(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Mock(side_effect=[subprocess.CompletedProcess([], 1, "", "daemon temporarily unavailable"),
                                   subprocess.CompletedProcess([], 0, "postgres\napi\nscheduler\n", "")])
            services = running_services(["docker", "compose"], Path(folder), run=run, sleep=lambda _: None)
            self.assertEqual(services, {"postgres", "api", "scheduler"})
            record = json.loads(next(Path(folder).glob("docker-read-*.json")).read_text())
            self.assertEqual(record["stderr"], "daemon temporarily unavailable")
            self.assertEqual(run.call_count, 2)

    def test_persistent_failure_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Mock(return_value=subprocess.CompletedProcess([], 1, "", "unavailable"))
            with self.assertRaises(HealthReadFailed):
                running_services([], Path(folder), run=run, sleep=lambda _: None)
            self.assertEqual(run.call_count, 3)

    def test_timeout_recovers(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Mock(side_effect=[subprocess.TimeoutExpired("docker", 10, stderr=b"timed out"),
                                   subprocess.CompletedProcess([], 0, "api", "")])
            self.assertEqual(running_services([], Path(folder), run=run, sleep=lambda _: None), {"api"})

    def test_missing_service_is_not_treated_as_transient_read_error(self):
        with tempfile.TemporaryDirectory() as folder:
            read = Mock(return_value={"postgres"})
            with self.assertRaisesRegex(RuntimeError, "api"):
                monitor([], Path(folder), 20, {"postgres", "api"}, Path(folder)/"STOP",
                        clock=lambda: 0, sleep=lambda _: None, read=read)
            self.assertEqual(read.call_count, 1)

    def test_deadline_and_stop_prevent_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            read = Mock()
            monitor([], Path(folder), 10, {"api"}, Path(folder)/"STOP", clock=lambda: 10, read=read)
            (Path(folder)/"STOP").touch()
            monitor([], Path(folder), 10, {"api"}, Path(folder)/"STOP", clock=lambda: 0, read=read)
            read.assert_not_called()

    def test_policy_command_stop_prevents_following_health_read(self):
        with tempfile.TemporaryDirectory() as folder:
            stop = Path(folder)/"STOP"
            read = Mock()
            monitor([], Path(folder), 10, {"api"}, stop, clock=lambda: 0, read=read, tick=stop.touch)
            read.assert_not_called()

    def test_deadline_during_retry_prevents_next_query(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Mock(return_value=subprocess.CompletedProcess([], 1, "", "unavailable"))
            with self.assertRaises(HealthReadFailed):
                running_services([], Path(folder), run=run, sleep=lambda _: None,
                                 permitted=Mock(side_effect=[True, False]))
            self.assertEqual(run.call_count, 1)
