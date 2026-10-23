import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine,
    String,
    Integer,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from packages.common.config import settings


def now():
    return datetime.now(timezone.utc)


def uid():
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    subject: Mapped[str] = mapped_column(String, unique=True)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    webhook_url: Mapped[str | None] = mapped_column(Text)
    webhook_ips: Mapped[str | None] = mapped_column(Text)
    webhook_secret: Mapped[str | None] = mapped_column(Text)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    subject: Mapped[str] = mapped_column(String, unique=True)


class Membership(Base):
    __tablename__ = "tenant_memberships"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String, default="owner")


class Wallet(Base):
    __tablename__ = "wallets"
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    available: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved: Mapped[int] = mapped_column(BigInteger, default=0)
    debt: Mapped[int] = mapped_column(BigInteger, default=0)
    schedule_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (CheckConstraint("available >= 0 AND reserved >= 0"),)


class Ledger(Base):
    __tablename__ = "wallet_ledger"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    source: Mapped[str] = mapped_column(String, unique=True)
    kind: Mapped[str] = mapped_column(String)
    available_delta: Mapped[int] = mapped_column(BigInteger)
    reserved_delta: Mapped[int] = mapped_column(BigInteger)
    debt_delta: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Key(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    prefix: Mapped[str] = mapped_column(String)
    digest: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: "job_" + uid())
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String)
    body_hash: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    tier: Mapped[str] = mapped_column(String)
    cancel: Mapped[bool] = mapped_column(Boolean, default=False)
    target: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    admission: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    public_id: Mapped[str] = mapped_column(String)
    repo: Mapped[str] = mapped_column(String)
    revision: Mapped[str] = mapped_column(String)
    tokenizer_revision: Mapped[str] = mapped_column(String)
    execution_mode: Mapped[str] = mapped_column(String)


class ModelPrice(Base):
    __tablename__ = "model_prices"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"))
    input_rate: Mapped[int] = mapped_column(BigInteger)
    output_rate: Mapped[int] = mapped_column(BigInteger)
    test_only: Mapped[bool] = mapped_column(Boolean)


class Work(Base):
    __tablename__ = "job_requests"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    custom_id: Mapped[str] = mapped_column(String)
    payload: Mapped[str | None] = mapped_column(Text)
    output: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="queued", index=True)
    model_revision: Mapped[str] = mapped_column(String, default="mock-v1")
    price_id: Mapped[str | None] = mapped_column(ForeignKey("model_prices.id"))
    prompt_tokens: Mapped[int] = mapped_column(Integer)
    max_output: Mapped[int] = mapped_column(Integer)
    input_rate: Mapped[int] = mapped_column(BigInteger)
    output_rate: Mapped[int] = mapped_column(BigInteger)
    reservation: Mapped[int] = mapped_column(BigInteger)
    captured: Mapped[int] = mapped_column(BigInteger, default=0)
    released: Mapped[int] = mapped_column(BigInteger, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    epoch: Mapped[int] = mapped_column(Integer, default=0)
    worker_id: Mapped[str | None] = mapped_column(String, index=True)
    worker_generation: Mapped[str | None] = mapped_column(String)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    eligible_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finish_reason: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(String)
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    first_dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("job_id", "ordinal"), UniqueConstraint("job_id", "custom_id"))


class Worker(Base):
    __tablename__ = "worker_nodes"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    model: Mapped[str] = mapped_column(String)
    capacity: Mapped[int] = mapped_column(Integer)
    heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    token_hash: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generation: Mapped[str] = mapped_column(String, default=uid)
    revision: Mapped[str] = mapped_column(String, default="unverified")
    repo: Mapped[str] = mapped_column(String, default="unverified")
    tokenizer_revision: Mapped[str] = mapped_column(String, default="unverified")
    execution_mode: Mapped[str] = mapped_column(String, default="unverified")
    served: Mapped[int] = mapped_column(Integer, default=0)
    provider_instance_id: Mapped[str | None] = mapped_column(String)
    telemetry: Mapped[str | None] = mapped_column(Text)
    telemetry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    adaptive_limit: Mapped[int] = mapped_column(Integer, default=2)
    adaptive_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model_loading_seconds: Mapped[int] = mapped_column(Integer, default=0)


class Usage(Base):
    __tablename__ = "usage_records"
    request_id: Mapped[str] = mapped_column(ForeignKey("job_requests.id"), primary_key=True)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    charge: Mapped[int] = mapped_column(BigInteger)


class Payment(Base):
    __tablename__ = "payment_events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    intent: Mapped[str] = mapped_column(String, unique=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    reversed_amount: Mapped[int] = mapped_column(BigInteger, default=0)


class Delivery(Base):
    __tablename__ = "webhook_deliveries"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), unique=True)
    body: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    due: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    claim: Mapped[str | None] = mapped_column(String)
    claim_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Instance(Base):
    __tablename__ = "provider_instances"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, unique=True)
    hourly_micro_usd: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_busy: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    terminated: Mapped[bool] = mapped_column(Boolean, default=False)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RateBucket(Base):
    __tablename__ = "rate_buckets"
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    window: Mapped[int] = mapped_column(BigInteger)
    hits: Mapped[int] = mapped_column(Integer)


class ExecutionAttempt(Base):
    """Operational observations, never a source of customer charges."""
    __tablename__ = "execution_attempts"
    request_id: Mapped[str] = mapped_column(ForeignKey("job_requests.id"), primary_key=True)
    epoch: Mapped[int] = mapped_column(Integer, primary_key=True)
    worker_id: Mapped[str] = mapped_column(String, index=True)
    instance_id: Mapped[str | None] = mapped_column(String)
    identity: Mapped[str] = mapped_column(String, index=True)
    mode: Mapped[str] = mapped_column(String)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)


class GpuObservation(Base):
    __tablename__ = "gpu_observations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    worker_id: Mapped[str] = mapped_column(String, index=True)
    instance_id: Mapped[str | None] = mapped_column(String, index=True)
    mode: Mapped[str] = mapped_column(String)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    active_seconds: Mapped[int] = mapped_column(Integer)
    idle_seconds: Mapped[int] = mapped_column(Integer)


class GpuCostProfile(Base):
    __tablename__ = "gpu_cost_profiles"
    instance_id: Mapped[str] = mapped_column(ForeignKey("provider_instances.id"), primary_key=True)
    provider: Mapped[str] = mapped_column(String)
    gpu_type: Mapped[str] = mapped_column(String)
    billing_increment_seconds: Mapped[int] = mapped_column(Integer)
    startup_seconds: Mapped[int] = mapped_column(Integer, default=0)
    invoiced_micro_usd: Mapped[int | None] = mapped_column(BigInteger)
    invoice_reference: Mapped[str | None] = mapped_column(String)
    invoiced_through: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("billing_increment_seconds > 0 AND startup_seconds >= 0 AND (invoiced_micro_usd IS NULL OR invoiced_micro_usd >= 0)"),)


class Audit(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String)
    reference: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


engine = create_engine(
    settings().database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5}, pool_size=20, max_overflow=30
)
Session = sessionmaker(engine, expire_on_commit=False)
