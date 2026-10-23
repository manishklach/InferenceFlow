from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://inferenceflow:localdev@localhost:55432/inferenceflow"
    environment: str = "development"
    secret_key: str = "development-only-change-before-deployment"
    worker_bootstrap_token: str = "local-worker-only"
    metrics_token: str = ""
    credential_hash_key: str = ""
    credential_hash_previous_keys: list[str] = []
    encryption_keys: dict[str, str] = {}
    encryption_active_key: str = ""
    encryption_legacy_secret: str = ""
    execution_mode: str = "mock"
    mock_latency_seconds: float = Field(default=0.01, ge=0, le=30)
    worker_trace_path: str = ""
    worker_capacity: int = Field(default=16, ge=1, le=16)
    model_revision: str = "mock-v1"
    model_repo: str = "Qwen/Qwen3-4B"
    input_rate: int = 100000
    output_rate: int = 300000
    max_pending: int = 2000
    max_inflight: int = 16
    lease_seconds: int = 60
    max_attempts: int = 3
    scheduler_v2_enabled: bool = False
    adaptive_dispatch_enabled: bool = False
    default_completion_target_seconds: int = Field(default=3600, ge=1, le=86400)
    estimator_input_tokens_per_second: float = Field(default=100, gt=0)
    estimator_output_tokens_per_second: float = Field(default=20, gt=0)
    estimator_uncertainty_margin: float = Field(default=1.5, ge=1, le=10)
    estimator_calibrated: bool = False
    estimator_min_samples: int = Field(default=20, ge=1)
    gpu_startup_seconds: int = Field(default=180, ge=0)
    model_loading_seconds: int = Field(default=120, ge=0)
    telemetry_stale_seconds: int = Field(default=45, ge=1, le=90)
    adaptive_initial_slots: int = Field(default=2, ge=1, le=16)
    adaptive_cooldown_seconds: int = Field(default=30, ge=1)
    planning_hourly_micro_usd: int = Field(default=1000000, ge=0)
    provider_billing_increment_seconds: int = Field(default=60, ge=1)
    retention_days: int = 7
    provisioning_enabled: bool = False
    max_active_gpus: int = 1
    max_daily_gpu_spend_usd: int = 25
    max_gpu_session_minutes: int = 120
    idle_shutdown_seconds: int = 900
    runpod_api_key: str = ""
    stripe_enabled: bool = False
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    dashboard_url: str = "http://localhost:3000"
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    oidc_authorization_url: str = ""
    oidc_token_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = "http://localhost:3000/api/auth/oidc/callback"
    otel_exporter_otlp_endpoint: str = ""
    public_beta_enabled: bool = False
    reviewed_gpu_experiment_enabled: bool = False

    def validate_runtime(self):
        if any(not key or ":" in key for key in self.encryption_keys):
            raise ValueError("Encryption key IDs must be nonempty and contain no colons")
        if self.execution_mode not in {"mock", "vllm"}:
            raise ValueError("Unsupported execution mode")
        if self.environment != "development":
            if len(self.worker_bootstrap_token) < 32 or self.worker_bootstrap_token == "local-worker-only":
                raise ValueError("Configure a strong WORKER_BOOTSTRAP_TOKEN")
            if len(self.metrics_token) < 32:
                raise ValueError("Configure a strong METRICS_TOKEN")
            if len(self.credential_hash_key) < 32 or self.credential_hash_key == self.secret_key:
                raise ValueError("Configure an independent CREDENTIAL_HASH_KEY")
            if not self.encryption_active_key or self.encryption_active_key not in self.encryption_keys:
                raise ValueError("Configure versioned ENCRYPTION_KEYS and ENCRYPTION_ACTIVE_KEY")
            from cryptography.fernet import Fernet

            for value in self.encryption_keys.values():
                Fernet(value.encode())
            if len(self.secret_key) < 32 or self.secret_key.startswith("development"):
                raise ValueError("Configure a high entropy SECRET_KEY")
            if not self.oidc_issuer or not self.oidc_audience or not self.oidc_jwks_url:
                raise ValueError("OIDC configuration required")
        if self.execution_mode != "mock" and (
            len(self.model_revision) != 40
            or any(ch not in "0123456789abcdef" for ch in self.model_revision)
            or not (self.public_beta_enabled or self.reviewed_gpu_experiment_enabled)
        ):
            raise ValueError("Real mode requires exact model SHA and reviewed private experiment or beta gate")
        if self.stripe_enabled and not self.stripe_secret_key.startswith("sk_test_"):
            raise ValueError("Only Stripe test credentials accepted")


@lru_cache
def settings():
    return Settings()
