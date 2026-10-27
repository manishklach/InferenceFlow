"""Actual emitted-token accounting; never imports DeepInfer or executes GPU code."""
from typing import Literal
from pydantic import Field, FiniteFloat, model_validator

from packages.common.throughput import Strict, digest


class Token(Strict):
    token_id: int = Field(ge=0)
    draft_tok: int = Field(default=0, ge=0)
    accept_tok: int = Field(default=0, ge=0)
    finished: bool = False
    finish_reason: str = ""

    @model_validator(mode="after")
    def acceptance(self):
        if self.accept_tok > self.draft_tok or (self.draft_tok > 0 and self.accept_tok < 1):
            raise ValueError("Invalid native verification counters")
        return self


class Request(Strict):
    request_id: str = Field(min_length=1, max_length=200)
    dp_rank: int = Field(ge=0)
    output: list[Token] = Field(max_length=262144)


class NativeRun(Strict):
    engine_commit: Literal["553741557a57df44a46fb3ab72b6aafeaf945337"]
    model_revision: Literal["1bae0e1088993b9b82de08f59de5be5a34e42170"]
    execution_mode: str = Field(pattern=r"^(real|mock)$")
    measurement_kind: str = Field(pattern=r"^actual_emitted_token_events$")
    expected_requests: int = Field(ge=1, le=100000)
    data_parallel_ranks: int = Field(ge=1, le=256)
    gpu_count: int = Field(ge=1, le=256)
    cohort_wall_seconds: FiniteFloat = Field(gt=0)
    requests: list[Request] = Field(min_length=1)

    @model_validator(mode="after")
    def completeness(self):
        if len(self.requests) != self.expected_requests:
            raise ValueError("Include every accepted request, including failures")
        keys = {(row.dp_rank, row.request_id) for row in self.requests}
        if len(keys) != len(self.requests) or any(row.dp_rank >= self.data_parallel_ranks for row in self.requests):
            raise ValueError("Duplicate or invalid rank/request identity")
        if any(any(token.finished for token in row.output[:-1]) for row in self.requests):
            raise ValueError("Output continues after a finished token")
        return self


def summarize(run: NativeRun):
    successful = [row for row in run.requests if row.output and row.output[-1].finished
                  and row.output[-1].finish_reason == "stop"]
    emitted = sum(len(row.output) for row in successful)
    all_tokens = [token for row in run.requests for token in row.output]
    rounds = sum(token.draft_tok > 0 for token in all_tokens)
    proposed = sum(token.draft_tok for token in all_tokens)-rounds
    accepted = sum(token.accept_tok for token in all_tokens)-rounds
    return {"schema": "inferenceflow.deepinfer-actual-token-summary.v1", "execution_mode": run.execution_mode,
            "engine_commit": run.engine_commit, "model_revision": run.model_revision,
            "successful_requests": len(successful), "accepted_requests": run.expected_requests,
            "unsuccessful_or_unfinished_requests": run.expected_requests-len(successful),
            "successful_emitted_tokens": emitted, "all_emitted_tokens": len(all_tokens),
            "successful_emitted_tokens_per_second": emitted/run.cohort_wall_seconds,
            "cohort_wall_seconds": run.cohort_wall_seconds, "gpu_count": run.gpu_count,
            "counter_marked_verification_rounds": rounds, "proposed_draft_tokens": proposed,
            "accepted_draft_tokens": accepted, "observed_draft_acceptance": accepted/proposed if proposed else None,
            "final_answer_tokens": None, "reasoning_tokens": None,
            "eligible_for_final_answer_throughput_profile": False,
            "evidence_sha256": digest(run),
            "semantics": "Counts actual emitted token IDs, including special/reasoning tokens. No 100%-acceptance multiplier. "
                         "Caller must measure one synchronized cohort wall span across ranks. Native counters and completion "
                         "flags are operator-supplied, not remote attestation. No billing or quality validation."}
