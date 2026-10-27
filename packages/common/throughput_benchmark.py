"""Bounded direct-engine benchmark. Does not provision, price, bill or tune an engine."""
import asyncio
import math
import time
from typing import Callable

import httpx
from pydantic import Field, FiniteFloat

from packages.common.throughput import Identity, Observation, Strict, Tuning, digest
from packages.common.receipt_format import text_sha256


class Input(Strict):
    custom_id: str = Field(min_length=1, max_length=200)
    messages: list[dict[str, str]] = Field(min_length=1, max_length=100)
    max_output_tokens: int = Field(ge=1, le=16384)
    expected_text: str | None = Field(default=None, max_length=16384)


class Study(Strict):
    identity: Identity
    tuning: Tuning
    served_model: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
    pair_id: str = Field(min_length=1, max_length=200)
    execution_mode: str = Field(pattern=r"^(real|mock)$")
    temperature: FiniteFloat = Field(default=0.0, ge=0, le=2)
    top_p: FiniteFloat = Field(default=1.0, gt=0, le=1)
    requests: list[Input] = Field(min_length=1, max_length=1000)


async def measure(study: Study, client: httpx.AsyncClient, *, timeout_seconds: float = 120,
                  record_sink: Callable[[dict], None] | None = None):
    """Caller owns client/endpoint; measured wall span includes client queueing and failures.

    Server model ID is checked, but pinned weights/configuration are operator assertions,
    not remotely attested by the OpenAI-compatible models endpoint.
    """
    if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 600:
        raise ValueError("Finite deadline <=600 seconds required")
    if len({item.custom_id for item in study.requests}) != len(study.requests):
        raise ValueError("Duplicate workload IDs")
    if any(item.max_output_tokens > study.identity.output_max for item in study.requests):
        raise ValueError("Output limit exceeds workload bucket")
    if any(message.get("role") not in {"system", "user", "assistant"}
           or set(message) != {"role", "content"} or not message["content"]
           for item in study.requests for message in item.messages):
        raise ValueError("Only explicit text chat messages are supported by this harness")
    models = await client.get("/v1/models", timeout=10)
    models.raise_for_status()
    if study.served_model not in {row["id"] for row in models.json()["data"]}:
        raise ValueError("Server model ID mismatch")
    semaphore = asyncio.Semaphore(study.tuning.concurrency)
    records: list[dict] = []
    started = time.perf_counter_ns()

    async def request(item):
        result: dict = {"custom_id": item.custom_id, "successful": False, "quality": None,
                  "input_tokens": 0, "reported_generated_tokens": 0,
                  "final_output_tokens": None, "reasoning_tokens": None}
        try:
            async with semaphore:
                response = await client.post("/v1/chat/completions", json={
                    "model": study.served_model, "messages": item.messages,
                    "max_tokens": item.max_output_tokens, "temperature": study.temperature,
                    "top_p": study.top_p, "stream": False},
                    timeout=min(timeout_seconds, 60))
                response.raise_for_status()
                data = response.json()
                choice = data["choices"][0]
                message, usage = choice["message"], data["usage"]
                content = message.get("content")
                prompt, generated = usage["prompt_tokens"], usage["completion_tokens"]
                if type(generated) is int and generated > 0:
                    result["reported_generated_tokens"] = generated
                if (type(prompt) is not int or type(generated) is not int or prompt <= 0 or generated <= 0
                        or generated > item.max_output_tokens
                        or not isinstance(content, str) or not content.strip()
                        or choice.get("finish_reason") != "stop"
                        or not study.identity.prompt_min <= prompt <= study.identity.prompt_max
                        or prompt+item.max_output_tokens > study.identity.context_limit):
                    raise ValueError("Invalid, truncated or out-of-bucket response")
                reasoning = usage.get("completion_tokens_details", {}).get("reasoning_tokens")
                # Missing detail remains unknown, even without visible reasoning text.
                if reasoning is not None and (type(reasoning) is not int or not 0 <= reasoning < generated):
                    raise ValueError("Invalid reasoning-token accounting")
                if message.get("reasoning_content") and reasoning == 0:
                    raise ValueError("Reasoning text conflicts with reported zero reasoning tokens")
                result.update(successful=True, input_tokens=prompt, reasoning_tokens=reasoning,
                              final_output_tokens=generated-reasoning if reasoning is not None else None,
                              output_sha256=text_sha256(content),
                              quality=content.strip() == item.expected_text.strip()
                              if item.expected_text is not None else None)
        except asyncio.CancelledError:
            result["error"] = "deadline_or_cancellation"
            raise
        except Exception as error:
            result["error"] = type(error).__name__  # Never response body, URL, auth or prompt.
        finally:
            result["completion_seconds"] = (time.perf_counter_ns()-started)/1_000_000_000
            records.append(result)
            if record_sink is not None:
                record_sink(result)

    tasks = [asyncio.create_task(request(item)) for item in study.requests]
    try:
        async with asyncio.timeout(timeout_seconds):
            await asyncio.gather(*tasks)
    except TimeoutError:
        pass  # All canceled tasks record unfinished requests before gather unwinds.
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = (time.perf_counter_ns()-started)/1_000_000_000
    successful = [row for row in records if row["successful"]]
    latencies = sorted(float(row["completion_seconds"]) for row in records)
    tokens_known = all(row["final_output_tokens"] is not None for row in successful)
    quality_known = all(row["quality"] is not None for row in records)
    observation = Observation(identity=study.identity, tuning=study.tuning, run_id=study.run_id,
        pair_id=study.pair_id, workload_sha256=digest({"requests": [r.model_dump() for r in study.requests],
            "temperature": study.temperature, "top_p": study.top_p, "served_model": study.served_model}),
        execution_mode=study.execution_mode, scope="direct_engine", total_requests=len(study.requests),
        successful_requests=len(successful), successful_output_tokens=sum(
            row["final_output_tokens"] or 0 for row in successful), elapsed_seconds=elapsed,
        p95_seconds=latencies[max(0, math.ceil(.95*len(latencies))-1)],
        final_token_counts_known=tokens_known and bool(successful),
        quality_score=sum(row["quality"] is True for row in records)/len(records) if quality_known else None,
        telemetry_coverage=0.0, evidence_sha256=digest({"records": records}))
    return {"observation": observation.model_dump(), "records": records,
            "scope": "direct engine only; no InferenceFlow queue, metering or billing validation",
            "identity_provenance": "Operator manifest plus checked served model ID; no remote attestation",
            "tuning_provenance": "Only client concurrency enforced; engine flags and resident budget are operator declarations",
            "missing_evidence": ["external telemetry/memory evidence", "fully loaded provider invoice"],
            "live_scheduler_enabled": False}
