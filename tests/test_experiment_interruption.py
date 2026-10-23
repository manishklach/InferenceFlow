import tempfile
import unittest
from pathlib import Path
from scripts.experiment_worker import Interruption


class InterruptionTests(unittest.TestCase):
    def test_opt_in_prefix_threshold_and_one_shot_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "fired"
            policy = Interruption("gpu-test-recovery", 2, marker)
            self.assertFalse(policy.success({"payload": {"custom_id": "unrelated"}}))
            item = {"payload": {"custom_id": "gpu-test-recovery-0001"}}
            self.assertFalse(policy.success(item))
            self.assertTrue(policy.success(item))
            self.assertFalse(policy.success(item))
            restarted = Interruption("gpu-test-recovery", 1, marker)
            self.assertFalse(restarted.success(item))

    def test_arbitrary_customer_prefix_and_invalid_count_refused(self):
        with self.assertRaises(ValueError):
            Interruption("customer", 1, "unused")
        with self.assertRaises(ValueError):
            Interruption("gpu-test-only", 0, "unused")


if __name__ == "__main__":
    unittest.main()
