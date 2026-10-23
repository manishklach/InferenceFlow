from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Message(Strict):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=100000)


class Item(Strict):
    custom_id: str = Field(min_length=1, max_length=200)
    messages: list[Message] = Field(min_length=1, max_length=100)
    max_output_tokens: int = Field(default=256, ge=1, le=2048)
    temperature: float = Field(default=0.2, ge=0, le=2)
    top_p: float = Field(default=1, gt=0, le=1)


class Submit(Strict):
    model: Literal["qwen3-4b"] = "qwen3-4b"
    tier: Literal["standard", "economy"] = "standard"
    deadline_seconds: int | None = Field(default=None, ge=1, le=86400)
    admission_policy: Literal["best_effort", "reject_if_at_risk"] = "best_effort"
    requests: list[Item] = Field(min_length=1, max_length=100)
    webhook_url: str | None = None

    @model_validator(mode="after")
    def unique_ids(self):
        if len({r.custom_id for r in self.requests}) != len(self.requests):
            raise ValueError("Duplicate custom_id")
        return self


class Completion(Strict):
    epoch: int
    output_text: str | None = Field(default=None, max_length=200000)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    finish_reason: str = "stop"
    error: Literal["transient", "permanent"] | None = None


class Registration(Strict):
    revision: str = "mock-v1"
    repo: str = "Qwen/Qwen3-4B"
    tokenizer_revision: str = "mock-v1"
    execution_mode: Literal["mock", "vllm"] = "mock"
    provider_instance_id: str | None = None
    id: str = Field(min_length=1, max_length=100)
    model: Literal["qwen3-4b"] = "qwen3-4b"
    capacity: int = Field(default=16, ge=1, le=16)
    model_loading_seconds: float = Field(default=0, ge=0, le=86400)


class NamedKey(Strict):
    name: str = Field(default="default", max_length=100)


class Checkout(Strict):
    amount_usd: Literal[10, 25, 100]


class Poll(Strict):
    available_slots: int = Field(default=16, ge=0, le=16)


class ActiveLease(Strict):
    id: str
    epoch: int


class Telemetry(Strict):
    active: list[ActiveLease] = Field(default_factory=list, max_length=16)
    kv_cache_usage: float | None = Field(default=None, ge=0, le=1)
    gpu_utilization: float | None = Field(default=None, ge=0, le=1)
    engine_running: int | None = Field(default=None, ge=0)
    engine_waiting: int | None = Field(default=None, ge=0)
    recent_error_rate: float | None = Field(default=None, ge=0, le=1)
    latency_ratio: float | None = Field(default=None, ge=0)
    observed_input_tokens_per_second: float | None = Field(default=None, ge=0)
    observed_output_tokens_per_second: float | None = Field(default=None, ge=0)
