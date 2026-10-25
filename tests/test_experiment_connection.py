import unittest

from scripts.experiment_connection import connection_payload


class ConnectionTests(unittest.TestCase):
    def test_only_minimal_approved_fields(self):
        value = connection_payload("https://staging.example/", "a"*40, "b"*40, "c"*40)
        self.assertEqual(set(value), {"CONTROL_PLANE_URL", "WORKER_BOOTSTRAP_TOKEN", "METRICS_TOKEN",
                                      "INFERENCEFLOW_API_KEY"})
        self.assertEqual(value["CONTROL_PLANE_URL"], "https://staging.example")

    def test_rejects_embedded_credentials_non_https_and_weak_keys(self):
        for url in ("http://staging.example", "https://user:password@staging.example", "https://staging.example/?key=x"):
            with self.assertRaises(ValueError):
                connection_payload(url, "a"*40, "b"*40, "c"*40)
        with self.assertRaises(ValueError):
            connection_payload("https://staging.example", "short", "b"*40, "c"*40)
