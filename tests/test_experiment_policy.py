from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from scripts.experiment_policy import expected, switch, verify
from scripts.github_staging_host import write_env


class PolicyTests(unittest.TestCase):
    def test_unknown_policy_and_safety_mismatch(self):
        with self.assertRaises(KeyError):
            expected("arbitrary-command")
        with self.assertRaises(RuntimeError):
            verify({**expected("adaptive"), "provisioning_enabled": True}, "adaptive", "vllm")

    def exercise(self, fail_at=None, idle="IDLE", fetch_bad=False):
        with TemporaryDirectory() as folder:
            runtime = Path(folder)
            write_env(runtime / "control.env", {"ENVIRONMENT": "staging", "EXECUTION_MODE": "vllm",
                "PUBLIC_BETA_ENABLED": "false", "STRIPE_ENABLED": "false", "PROVISIONING_ENABLED": "false",
                "RUNPOD_API_KEY": "", "METRICS_TOKEN": "test-only"})
            calls = []

            def docker(*args):
                calls.append(args)
                if args[0] == fail_at:
                    raise RuntimeError("Injected Compose failure")
                return SimpleNamespace(stdout=idle)

            config = {**expected("adaptive"), "execution_mode": "vllm", "public_beta_enabled": False,
                "stripe_enabled": False, "provisioning_enabled": False, "estimator_calibrated": False}
            if fetch_bad:
                config["max_inflight"] = 1
            try:
                switch("adaptive", runtime, "https://unused.invalid", docker=docker, fetch=lambda: config)
                success = True
            except RuntimeError:
                success = False
            return success, calls, (runtime / "STOP").exists(), (runtime / "maintenance.json").exists()

    def test_stop_admission_then_repeat_idle_before_recreation(self):
        success, calls, stopped, maintenance = self.exercise()
        self.assertTrue(success)
        self.assertEqual([c[0] for c in calls], ["exec", "stop", "run", "up"])
        self.assertFalse(stopped or maintenance)

    def test_busy_boundary_does_not_stop_services(self):
        success, calls, stopped, maintenance = self.exercise(idle="BUSY")
        self.assertFalse(success)
        self.assertEqual(len(calls), 1)
        self.assertFalse(stopped or maintenance)

    def test_restart_or_effective_configuration_failure_stops_host(self):
        for kwargs in ({"fail_at": "up"}, {"fetch_bad": True}, {"fail_at": "run"}):
            with self.subTest(**kwargs):
                success, _, stopped, maintenance = self.exercise(**kwargs)
                self.assertFalse(success)
                self.assertTrue(stopped)
                self.assertFalse(maintenance)


if __name__ == "__main__":
    unittest.main()
