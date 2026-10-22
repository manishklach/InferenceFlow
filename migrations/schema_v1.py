import uuid
from datetime import datetime, timezone
from sqlalchemy import (
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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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


class Wallet(Base):
    __tablename__ = "wallets"
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    available: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved: Mapped[int] = mapped_column(BigInteger, default=0)
    __table_args__ = (CheckConstraint("available >= 0 AND reserved >= 0"),)


class Ledger(Base):
    __tablename__ = "wallet_ledger"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    source: Mapped[str] = mapped_column(String, unique=True)
    kind: Mapped[str] = mapped_column(String)
    available_delta: Mapped[int] = mapped_column(BigInteger)
    reserved_delta: Mapped[int] = mapped_column(BigInteger)
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
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    eligible_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finish_reason: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(String)
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("job_id", "ordinal"), UniqueConstraint("job_id", "custom_id"))


class Worker(Base):
    __tablename__ = "worker_nodes"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    model: Mapped[str] = mapped_column(String)
    capacity: Mapped[int] = mapped_column(Integer)
    heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    token_hash: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    served: Mapped[int] = mapped_column(Integer, default=0)
    provider_instance_id: Mapped[str | None] = mapped_column(String)


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


class Instance(Base):
    __tablename__ = "provider_instances"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, unique=True)
    hourly_micro_usd: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_busy: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    terminated: Mapped[bool] = mapped_column(Boolean, default=False)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Audit(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String)
    reference: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
