import unittest

from scripts.github_real_host import real_configuration, REVISION


class RealControlHostTests(unittest.TestCase):
    def test_real_mode_keeps_paid_and_public_features_disabled(self):
        config, database = real_configuration({"OIDC_ISSUER": "https://tenant.us.auth0.com/",
            "OIDC_AUDIENCE": "unit-audience", "OIDC_JWKS_URL": "https://tenant.us.auth0.com/jwks"})
        self.assertEqual(config["EXECUTION_MODE"], "vllm")
        self.assertEqual(config["MODEL_REVISION"], REVISION)
        self.assertEqual(config["REVIEWED_GPU_EXPERIMENT_ENABLED"], "true")
        for name in ("PUBLIC_BETA_ENABLED", "PROVISIONING_ENABLED", "STRIPE_ENABLED",
                     "SCHEDULER_V2_ENABLED", "ADAPTIVE_DISPATCH_ENABLED", "ESTIMATOR_CALIBRATED"):
            self.assertEqual(config[name], "false")
        self.assertEqual(config["RUNPOD_API_KEY"], "")
        self.assertEqual(config["MAX_INFLIGHT"], "4")
        self.assertEqual(database["POSTGRES_DB"], "if_hosted_staging")
