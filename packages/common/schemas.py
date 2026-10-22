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
    provider_instance_id: str | None = None
    id: str = Field(min_length=1, max_length=100)
    model: Literal["qwen3-4b"] = "qwen3-4b"
    capacity: int = Field(default=16, ge=1, le=16)


class NamedKey(Strict):
    name: str = Field(default="default", max_length=100)


class Checkout(Strict):
    amount_usd: Literal[10, 25, 100]


class Telemetry(Strict):
    kv_cache_usage: float | None = Field(default=None, ge=0, le=1)
    gpu_utilization: float | None = Field(default=None, ge=0, le=1)
    engine_running: int | None = Field(default=None, ge=0)
    engine_waiting: int | None = Field(default=None, ge=0)
