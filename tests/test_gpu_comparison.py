import json
import tempfile
import unittest
from pathlib import Path
from scripts.compare_gpu_runs import compare


class ComparisonTests(unittest.TestCase):
    def fixtures(self, root):
        paths = []
        for count in (10, 100, 1000):
            for policy in ("baseline", "adaptive"):
                folder = root / f"{policy}-{count}"
                folder.mkdir()
                summary = {"policy": policy, "accepted_requests": count, "elapsed_seconds": 10,
                           "output_tokens_per_second": 20 if policy == "adaptive" else 10,
                           "model": {"revision": "synthetic-unit-revision"},
                           "workers": [{"provider_instance_id": "synthetic-unit-instance"}]}
                audit = {"passed": True, "measurement_modes": ["vllm"],
                         "accepted_to_last_terminal_seconds": 8,
                         "request_e2e_seconds_successful_only": {"p95": 1},
                         "all_accepted_requests_successful_within_60_minutes": 1,
                         "statuses": {"succeeded": count}, "retried_attempts": 0, "captured_micro_usd": 1}
                # Entire test is a fabricated fixture, not real GPU evidence.
                for name, value in (("summary", summary), ("audit", audit),
                                    ("workload", [{"custom_id": policy, "messages": ["same synthetic input"]}])):
                    (folder / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
                paths.append(str(folder))
        return paths

    def test_matched_pairs_and_missing_cost_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.fixtures(Path(directory))
            report = compare(paths)
            self.assertEqual(len(report["rows"]), 3)
            self.assertEqual(report["rows"][0]["output_throughput_speedup"], 2)
            self.assertIsNone(report["rows"][0]["baseline"]["provider_cost_per_million_tokens_usd"])
            with self.assertRaisesRegex(ValueError, "Missing matched pair"):
                compare(paths[:-1])

    def test_three_policy_comparison_requires_matched_sequential_arms(self):
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            paths = self.fixtures(Path(directory))
            with self.assertRaisesRegex(ValueError, "Missing sequential"):
                compare(paths, include_sequential=True)
            for source in list(paths)[::2]:
                target = Path(source.replace("baseline", "sequential"))
                shutil.copytree(source, target)
                summary = json.loads((target / "summary.json").read_text(encoding="utf-8"))
                summary["policy"] = "sequential"
                (target / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
                paths.append(str(target))
            self.assertIn("sequential", compare(paths, include_sequential=True)["rows"][0])
            subset = [p for p in paths if Path(p).name.endswith('-100')]
            self.assertEqual(len(compare(subset, include_sequential=True, counts=(100,))["rows"]), 1)

    def test_unmatched_inputs_and_failed_audits_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.fixtures(Path(directory))
            folder = Path(paths[1])
            (folder / "workload.json").write_text(json.dumps([{"messages": ["different input"]}]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unmatched"):
                compare(paths)
            (folder / "audit.json").write_text(json.dumps({"passed": False}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Passing real-mode"):
                compare(paths)


if __name__ == "__main__":
    unittest.main()
