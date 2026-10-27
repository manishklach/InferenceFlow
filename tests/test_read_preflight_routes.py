import unittest
from unittest.mock import patch
import httpx
from scripts.experiment_telemetry import PodReader
from scripts.experiment_read_preflight import probe_absent_pod, probe_github


class ReadPreflightTests(unittest.TestCase):
    def test_missing_pod_checks_both_routes_but_does_not_claim_stream_proof(self):
        seen = []
        def respond(request):
            seen.append(request)
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.host, 'api.runpod.io')
            return httpx.Response(404)
        reader = PodReader('test-only-key', httpx.MockTransport(respond))
        result = probe_absent_pod(reader, 'previous-owned')
        self.assertEqual(len(seen), 2)
        self.assertEqual(result['pod_logs_status'], 404)
        self.assertFalse(result['live_log_stream_verified'])
        with self.assertRaises(ValueError):
            probe_absent_pod(reader, '../other')
        reader.close()

    def test_forbidden_route_is_a_failure_not_a_missing_resource(self):
        reader = PodReader('test-only-key', httpx.MockTransport(lambda _: httpx.Response(403)))
        with self.assertRaises(httpx.HTTPStatusError):
            probe_absent_pod(reader, 'previous-owned')
        reader.close()

    def test_github_probe_never_receives_provider_authorization(self):
        def respond(request):
            self.assertEqual(request.url.host, 'api.github.com')
            self.assertNotIn('authorization', request.headers)
            return httpx.Response(200, json={'id':123})
        client = httpx.Client(transport=httpx.MockTransport(respond))
        with patch('scripts.experiment_read_preflight.httpx.Client', return_value=client):
            self.assertEqual(probe_github('123')['anonymous_github_status'], 200)


if __name__ == '__main__':
    unittest.main()
