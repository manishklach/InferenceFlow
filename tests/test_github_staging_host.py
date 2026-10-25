import tempfile
import unittest
from pathlib import Path

from scripts.github_staging_host import configuration, write_env


class HostedStagingTests(unittest.TestCase):
    def test_configuration_isolated_mock_and_never_contains_provider_authority(self):
        oidc = {"OIDC_ISSUER": "https://tenant.us.auth0.com/", "OIDC_AUDIENCE": "test-audience",
                "OIDC_JWKS_URL": "https://tenant.us.auth0.com/.well-known/jwks.json",
                "OIDC_CLIENT_SECRET": "unit-secret-"*5}
        first, first_db = configuration(oidc)
        second, second_db = configuration(oidc)
        self.assertEqual(first["ENVIRONMENT"], "staging")
        self.assertEqual(first["EXECUTION_MODE"], "mock")
        for key in ("PROVISIONING_ENABLED", "PUBLIC_BETA_ENABLED", "STRIPE_ENABLED",
                    "REVIEWED_GPU_EXPERIMENT_ENABLED"):
            self.assertEqual(first[key], "false")
        self.assertEqual(first["RUNPOD_API_KEY"], "")
        self.assertNotEqual(first_db["POSTGRES_PASSWORD"], second_db["POSTGRES_PASSWORD"])
        self.assertNotEqual(first["ENCRYPTION_KEYS"], second["ENCRYPTION_KEYS"])
        self.assertNotEqual(first["SECRET_KEY"], first["CREDENTIAL_HASH_KEY"])

    def test_environment_file_rejects_multiline_or_quoted_values(self):
        with tempfile.TemporaryDirectory() as folder:
            for value in ("bad\nvalue", "bad\rvalue", "bad'value"):
                with self.assertRaises(ValueError):
                    write_env(Path(folder)/"control.env", {"KEY": value})
