"""Deterministic contracts only; no provider account or paid resources required."""
import unittest
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import httpx
from packages.common.provider_discovery import (
    VastProvider, LambdaProvider, RunpodDiscovery, Offer, ProviderReadError, compare_offers, micro_usd,
    capability_discovery, active_provider,
)
from packages.common.providers import GpuSpec, NotConfigured


class DiscoveryContracts(unittest.TestCase):
    def test_runpod_cloud_quote_region_and_pagination_contract(self):
        def handle(request):
            if request.url.path.endswith("/gpus"):
                self.assertEqual(request.url.params["cloud"], "COMMUNITY")
                return httpx.Response(200, json={"gpus": [{"id": "unit-gpu", "name": "unit", "availability": "LOW",
                    "price": {"community": .34, "secure": .89}, "dataCenters": [{"id": "unit-dc", "availability": "LOW"}]}]})
            return httpx.Response(200, json={"pods": [{"id": "unit-1"}], "pagination": {"hasNextPage": False}})
        with httpx.Client(base_url=RunpodDiscovery.base_url, transport=httpx.MockTransport(handle)) as client:
            discovery = RunpodDiscovery("unit-only", client, cloud="COMMUNITY")
            self.assertEqual(discovery.get_price_quote("unit-gpu", "unit-dc")[0].compute_micro_usd_per_hour, 340000)
            self.assertFalse(discovery.get_price_quote("unit-gpu", "other-dc")[0].available)
            self.assertEqual(discovery.list_instances(), [{"id": "unit-1"}])
            with self.assertRaises(NotConfigured):
                discovery.terminate_instance("unit-1")

    def test_optional_mutations_and_credentials_fail_before_network(self):
        def forbidden(request):
            self.fail("No request should be issued")
        for provider_type in (VastProvider, LambdaProvider):
            with httpx.Client(base_url=provider_type.base_url, transport=httpx.MockTransport(forbidden)) as client:
                provider = provider_type(client=client)
                for operation in (lambda: provider.list_instances(),
                                  lambda: provider.create_instance(GpuSpec("gpu", "region", "image", 1), "stable"),
                                  lambda: provider.terminate_instance("owned")):
                    with self.assertRaises(NotConfigured):
                        operation()
                self.assertFalse(provider.capabilities()["paid_mutations"])
                provider.api_key = "unit-only"
                with self.assertRaises(NotConfigured):
                    provider.read("DELETE", "/instances/owned")
                with self.assertRaises(NotConfigured):
                    provider.read("POST", "/instance-operations/launch")
        with self.assertRaises(NotConfigured):
            active_provider("vast")
        self.assertEqual(capability_discovery()["active_provider"], "runpod")

    def test_vast_search_inventory_and_unknown_extras(self):
        calls = []
        def handle(request):
            calls.append((request.method, request.url.path))
            if request.method == "POST":
                return httpx.Response(200, json={"offers": [{"id": 23, "gpu_name": "RTX 4090", "num_gpus": 1,
                                                            "geolocation": "test-region", "rentable": True,
                                                            "dph_total": .3412345}]})
            return httpx.Response(200, json={"instances": []})
        with httpx.Client(base_url=VastProvider.base_url, transport=httpx.MockTransport(handle)) as client:
            provider = VastProvider("unit-only", client)
            offer = provider.get_price_quote("RTX 4090", "test-region")[0]
            self.assertEqual(offer.compute_micro_usd_per_hour, 341235)
            self.assertIsNone(offer.storage_micro_usd_per_hour)
            self.assertEqual(provider.list_instances(), [])
            provider.get_instance("id-1")
        self.assertEqual(calls, [("POST", "/api/v0/bundles"), ("GET", "/api/v0/instances/"),
                                 ("GET", "/api/v0/instances/id-1/")])

    def test_lambda_cents_are_per_instance_and_capacity_is_regional(self):
        def handle(request):
            return httpx.Response(200, json={"data": {"gpu_test": {
                "instance_type": {"gpu_description": "Test NVIDIA", "price_cents_per_hour": 123,
                                  "specs": {"gpus": 2}},
                "regions_with_capacity_available": [{"name": "region-a"}]}}})
        with httpx.Client(base_url=LambdaProvider.base_url, transport=httpx.MockTransport(handle)) as client:
            provider = LambdaProvider("unit-only", client)
            offers = provider.get_price_quote("gpu_test", "region-a")
            self.assertTrue(offers[0].available)
            self.assertEqual(offers[0].compute_micro_usd_per_hour, 1230000)
            self.assertEqual(offers[0].gpu_count, 2)
            self.assertFalse(provider.get_price_quote("gpu_test", "region-b")[0].available)
            self.assertEqual(provider.get_price_quote("not-in-catalog", "region-a"), [])

    def test_retry_only_bounded_discovery_and_sanitized_errors(self):
        for status, expected_calls in ((401, 1), (403, 1), (429, 2), (503, 2), (302, 1)):
            calls = []
            def handle(request):
                calls.append(request)
                return httpx.Response(status, text="secret-provider-body", headers={"location": "https://other.invalid"})
            with httpx.Client(base_url=LambdaProvider.base_url, transport=httpx.MockTransport(handle)) as client:
                provider = LambdaProvider("unit-only", client)
                with self.assertRaises(ProviderReadError) as error:
                    provider.list_instances()
                self.assertNotIn("secret-provider-body", str(error.exception))
                self.assertEqual(len(calls), expected_calls)
                self.assertEqual(error.exception.retryable, status in (429, 503))

    def test_malformed_catalog_transport_and_invalid_money(self):
        for provider_type, payload in ((VastProvider, {"offers": [{"id": 1}]}), (LambdaProvider, {"data": []})):
            with httpx.Client(base_url=provider_type.base_url,
                              transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))) as client:
                with self.assertRaises(ProviderReadError):
                    provider_type("unit-only", client).get_price_quote("gpu", "region")
        def unavailable(request):
            raise httpx.ConnectError("unit-network-failure", request=request)
        with httpx.Client(base_url=LambdaProvider.base_url, transport=httpx.MockTransport(unavailable)) as client:
            with self.assertRaises(ProviderReadError) as error:
                LambdaProvider("unit-only", client).list_instances()
            self.assertTrue(error.exception.retryable)
        for value in ("NaN", "Infinity", -1):
            with self.assertRaises(ValueError):
                micro_usd(value)

    def test_comparison_complete_fresh_quotes_only_and_deterministic_ties(self):
        stamp = datetime.now(timezone.utc)
        base = Offer("vast", "a", "same-gpu", "same-region", 1, 340000, stamp.isoformat(), "synthetic", True,
                     10000, 0, 1)
        other = replace(base, provider="lambda", offer_id="b")
        rows = [base, other, replace(base, offer_id="incomplete", storage_micro_usd_per_hour=None),
                replace(base, offer_id="stale", observed_at=(stamp - timedelta(minutes=10)).isoformat()),
                replace(base, offer_id="unavailable", available=False), replace(base, offer_id="multi", gpu_count=2)]
        report = compare_offers(rows, stamp)
        self.assertEqual([r["provider"] for r in report["ranked"]], ["lambda", "vast"])
        self.assertEqual(report["ranked"][0]["total_micro_usd_per_hour"], 350000)
        self.assertEqual(len(report["excluded"]), 4)
        self.assertFalse(report["automatic_failover"])


if __name__ == "__main__":
    unittest.main()
