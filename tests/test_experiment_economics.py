import unittest
from scripts.experiment_economics import report, sensitivity


class ExperimentEconomicsTests(unittest.TestCase):
    def data(self):
        return dict(
            input_tokens=3000000,
            output_tokens=1000000,
            successful_jobs=9,
            accepted_jobs=10,
            jobs_within_deadline=8,
            paid_seconds=7200,
            startup_seconds=120,
            cost_kind="estimate",
            cost_reference="synthetic-unit-fixture",
            compute_usd="2.4",
            storage_usd=".1",
            ancillary_usd="0",
        )

    def test_full_cost_denominators_coverage_and_unknown_idle(self):
        d = self.data()
        r = report(d)
        self.assertEqual(r["blended_cost_per_million_usd"], "0.625")
        self.assertEqual(r["deadline_attainment_all_accepted"], 0.8)
        self.assertIsNone(r["sampled_zero_utilization_seconds"])
        d["hardware_intervals"] = [
            dict(seconds=10, gpu_utilization_fraction=0),
            dict(seconds=30, gpu_utilization_fraction=0.8),
        ]
        r = report(d)
        self.assertAlmostEqual(r["effective_utilization_over_observed_fraction"], 0.6)
        self.assertEqual(r["unobserved_gpu_seconds"], 7160)
        d["storage_usd"] = None
        with self.assertRaises(Exception):
            report(d)

    def test_zero_tokens_provenance_and_equivalence(self):
        d = self.data()
        d.update(input_tokens=0, output_tokens=0)
        self.assertIsNone(report(d)["blended_cost_per_million_usd"])
        d["cost_kind"] = "unknown"
        with self.assertRaises(ValueError):
            report(d)
        d = self.data()
        d["hosted_alternative"] = dict(equivalent_model_and_workload=False, source="fixture")
        with self.assertRaises(ValueError):
            report(d)

    def test_sensitivity_idle_retries_startup_and_volume(self):
        baseline = sensitivity(1, 100, 1000000, 1, 0, 0)
        for args in [(1, 100, 1000000, 0.5, 0, 0), (1, 100, 1000000, 1, 100, 0), (1, 100, 1000000, 1, 0, 0.2)]:
            self.assertGreater(sensitivity(*args)["cost_micro_usd"], baseline["cost_micro_usd"])
        with self.assertRaises(ValueError):
            sensitivity(1, 0, 1, 1, 0, 0)
