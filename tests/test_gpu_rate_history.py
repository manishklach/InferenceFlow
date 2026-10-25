"""Offline history integrity checks; unittest does not require a database."""
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

from scripts import cpu_rate_history, gpu_rate_history


class GpuRateHistoryTests(unittest.TestCase):
    def test_cpu_history_retains_per_vcpu_units_and_previous_observations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = {"id": "cpu3c", "name": "Compute-Optimized", "group": "CPU3",
                       "ramGbPerVcpu": 2, "vcpu": {"min": 2, "max": 32},
                       "price": {"securePerVcpu": .03}, "availability": "HIGH"}
            with patch.object(cpu_rate_history, "__file__", str(root / "scripts/collector.py")), patch("builtins.print"):
                for _ in range(2):
                    with patch("sys.stdin", io.StringIO(json.dumps([fixture]))):
                        cpu_rate_history.main()
            folder = root / "docs/cpu-rates"
            history = [json.loads(line) for line in (folder / "observations.jsonl").read_text().splitlines()]
            self.assertEqual(len(history), 2)
            self.assertEqual(history[0]["usd_per_vcpu_hour"], .03)
            self.assertEqual(history[0]["availability_vcpu_count"], 2)
            with (folder / "daily.csv").open() as stream:
                self.assertEqual(int(list(csv.DictReader(stream))[0]["samples"]), 2)

    def test_repeated_collection_preserves_old_quotes_and_daily_range(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docs").mkdir()
            fixture = {"cloud": "SECURE", "name": "L4", "id": "NVIDIA L4", "memory": 24,
                       "secure": True, "availability": "LOW", "price": {"secure": .59}}
            with patch.object(gpu_rate_history, "__file__", str(root / "scripts/collector.py")), patch("builtins.print"):
                for price in (.59, .61):
                    fixture["price"]["secure"] = price
                    with patch("sys.stdin", io.StringIO(json.dumps([fixture]))):
                        gpu_rate_history.main()
            folder = root / "docs/gpu-rates"
            history = [json.loads(line) for line in (folder / "observations.jsonl").read_text().splitlines()]
            self.assertEqual([row["gpu_usd_per_hour"] for row in history], [.59, .61])
            with (folder / "daily.csv").open() as stream:
                daily = list(csv.DictReader(stream))[0]
            self.assertEqual(int(daily["samples"]), 2)
            self.assertEqual(float(daily["min_gpu_usd_per_hour"]), .59)
            self.assertEqual(float(daily["max_gpu_usd_per_hour"]), .61)
            ElementTree.parse(folder / "rates.svg")

    def test_invalidated_replay_remains_raw_but_not_in_exports(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "docs/gpu-rates"
            folder.mkdir(parents=True)
            invalid = {"invalidated": True, "reason": "not an independent provider observation"}
            (folder / "observations.jsonl").write_text(json.dumps(invalid) + "\n")
            fixture = {"cloud": "COMMUNITY", "name": "L4", "id": "NVIDIA L4", "memory": 24,
                       "community": False, "availability": "NONE", "price": {"community": .44}}
            with patch.object(gpu_rate_history, "__file__", str(root / "scripts/collector.py")), \
                    patch("sys.stdin", io.StringIO(json.dumps([fixture]))), patch("builtins.print"):
                gpu_rate_history.main()
            self.assertEqual(len((folder / "observations.jsonl").read_text().splitlines()), 2)
            with (folder / "hourly.csv").open() as stream:
                exported = list(csv.DictReader(stream))
            self.assertEqual(len(exported), 1)
            self.assertEqual(exported[0]["availability"], "NONE")
