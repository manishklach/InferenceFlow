"""No network, database, provider credentials or billable resources required."""
import io
import json
import unittest
import urllib.error
from unittest.mock import Mock, patch

from scripts import collect_compute_prices as collector


GPU = {"id": "NVIDIA B300 SXM6 AC", "name": "B300", "memory": 288,
       "availability": "LOW", "price": {"community": 6.94, "secure": 8.99}}
CPU = {"id": "cpu3c", "name": "Compute-Optimized", "group": "CPU3", "ramGbPerVcpu": 2,
       "vcpu": {"min": 2, "max": 32}, "availability": "HIGH", "price": {"securePerVcpu": .03}}


class ComputeCollectionTests(unittest.TestCase):
    def test_all_clouds_cpu_units_and_no_capacity_filters(self):
        fetch = Mock(side_effect=[{"gpus": [GPU]}, {"gpus": [GPU]}, {"cpus": [CPU]}])
        result = collector.collect("unit-test-not-a-credential", fetch)
        self.assertEqual([r["cloud"] for r in result["gpus"]], ["COMMUNITY", "SECURE"])
        self.assertEqual(result["cpus"][0]["price"]["securePerVcpu"], .03)
        self.assertEqual([call.args[1] for call in fetch.call_args_list], ["gpus", "gpus", "cpus"])
        for call in fetch.call_args_list:
            self.assertNotIn("minCudaVersion", call.args[2])
            self.assertNotIn("countryCodes", call.args[2])
        self.assertEqual(fetch.call_args_list[-1].args[2]["vcpuCount"], 2)

    def test_collection_failure_does_not_append_partial_history(self):
        with patch.object(collector, "collect", side_effect=RuntimeError("unavailable")), \
                patch.object(collector, "persist") as persist, \
                patch.dict("os.environ", {"RUNPOD_PRICING_API_KEY": "not-a-real-key"}):
            with self.assertRaisesRegex(SystemExit, "Pricing collection failed"):
                collector.main()
            persist.assert_not_called()

    def test_bad_prices_empty_or_paginated_catalog_fail_closed(self):
        for value in (float("nan"), float("inf"), -1, True, None):
            with self.assertRaises(ValueError):
                collector.price(value)
        for data in ({"gpus": []}, {"gpus": [GPU], "pagination": {"hasNextPage": True}}, {"gpus": [GPU, GPU]}):
            with self.assertRaises(ValueError):
                collector.entries(data, "gpus")

    def test_transport_is_get_only_and_bearer_not_query_parameter(self):
        response = Mock()
        response.__enter__ = Mock(return_value=io.StringIO(json.dumps({"gpus": [GPU]})))
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with patch("urllib.request.build_opener", return_value=opener):
            result = collector.catalog_get("fixture-secret", "gpus", {"cloud": "SECURE"})
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.host, "api.runpod.io")
        self.assertNotIn("fixture-secret", request.full_url)
        self.assertEqual(result["gpus"][0]["name"], "B300")
        with self.assertRaises(ValueError):
            collector.catalog_get("fixture-secret", "pods", {})
        self.assertIsNone(collector.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com"))

    def test_auth_failure_never_retries_or_logs_provider_body(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError("https://api.runpod.io/v2/catalog/gpus", 401, "private-body", {}, None)
        with patch("urllib.request.build_opener", return_value=opener), patch("time.sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, r"HTTP 401"):
                collector.catalog_get("fixture-secret", "gpus", {})
        self.assertEqual(opener.open.call_count, 1)
        sleep.assert_not_called()

    def test_shared_collection_timestamp_and_honest_rest_provenance(self):
        snapshot = {"observed_at_utc": "2026-10-25T14:17:00+00:00", "gpus": [GPU], "cpus": [CPU]}
        with patch.object(collector.gpu_rate_history, "record_snapshot") as gpu, \
                patch.object(collector.cpu_rate_history, "record_snapshot") as cpu:
            collector.persist(snapshot)
        self.assertEqual(gpu.call_args.args[1:], (snapshot["observed_at_utc"], "RunPod REST v2 catalog"))
        self.assertEqual(cpu.call_args.args[1:], gpu.call_args.args[1:])
