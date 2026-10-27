"""Offline profile qualification/replay; optional bounded calls to an existing engine."""
import argparse
import asyncio
import ipaddress
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

import httpx
from pydantic import Field, FiniteFloat

from packages.common.throughput import (Identity, Observation, Pending, Profile,
                                        Snapshot, Strict, Tuning, digest, qualify, recommend)
from packages.common.throughput_benchmark import Study, measure
from packages.common.throughput_evidence import Review, attach


class Replay(Strict):
    identity: Identity
    baseline: Tuning
    engine_tuning: Tuning
    snapshot: Snapshot | None
    queue: list[Pending] = Field(max_length=4096)
    now: FiniteFloat = Field(ge=0)
    hard_limit: int = Field(ge=1, le=128)
    tenant_remaining: dict[str, int]


def read(path):
    if path.stat().st_size > 8*1024*1024:
        raise ValueError("Input exceeds 8 MiB")
    return path.read_text(encoding="utf-8")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite retained experiment intent or evidence.
    with path.open("x", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+"\n")


def endpoint(url):
    parsed = urlsplit(url)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"} or parsed.scheme not in {"http", "https"}):
        raise ValueError("Bare HTTP(S) engine origin required; no credentials, path or query")
    local = parsed.hostname == "localhost"
    try:
        local = local or ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        pass
    if parsed.scheme != "https" and not local:
        raise ValueError("Non-loopback engine requires HTTPS")
    return url.rstrip("/")


def demo(folder):
    folder.mkdir(parents=True, exist_ok=False)
    identity = Identity(model="synthetic/mock-throughput", revision="0"*40, tokenizer_revision="0"*40,
        engine="mock", engine_digest="sha256:"+"0"*64, runtime_config_sha256="0"*64,
        precision="synthetic", gpu="NO GPU", gpu_count=1, topology="mock", context_limit=4096,
        prompt_min=1, prompt_max=1024, output_max=128)
    baseline = Tuning(concurrency=2, resident_token_budget=4096, max_batched_tokens=1024, draft_tokens=0)
    candidate = baseline.model_copy(update={"concurrency": 4, "resident_token_budget": 8192})
    rows = [Observation(identity=identity, tuning=tuning, run_id=f"mock-{pair}-{name}", pair_id=str(pair),
        workload_sha256="0"*64, execution_mode="mock", scope="direct_engine", total_requests=100,
        successful_requests=100, successful_output_tokens=tokens, elapsed_seconds=60.0, p95_seconds=10.0,
        quality_score=1.0, final_token_counts_known=True, cost_usd=0.003, cost_scope="warm_estimate",
        telemetry_coverage=1.0, peak_memory_fraction=0.5,
        evidence_sha256=digest({"synthetic_pair": pair, "name": name}))
        for pair in range(3) for name, tuning, tokens in (("baseline", baseline, 10000),
                                                        ("candidate", candidate, 15000))]
    with (folder/"observations.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(row.model_dump_json()+"\n")
    write(folder/"baseline.json", baseline.model_dump())
    write(folder/"qualification.json", qualify(rows, baseline, now=1000.0))
    scenario = Replay(identity=identity, baseline=baseline, engine_tuning=baseline,
        snapshot=Snapshot(observed_at_epoch=1000.0, active_requests=0, resident_tokens=0,
                          memory_fraction=0.2, error_rate=0.0, p95_seconds=1.0),
        queue=[Pending(request_id=f"mock-{i}", tenant_id="synthetic", prompt_tokens=512,
                       output_limit=64, deadline_epoch=1100.0) for i in range(4)],
        now=1000.0, hard_limit=4, tenant_remaining={"synthetic": 4})
    write(folder/"scenario.json", scenario.model_dump())
    write(folder/"recommendation.json", recommend(**scenario.model_dump(exclude={"identity", "baseline",
        "engine_tuning", "snapshot", "queue"}), identity=identity, baseline=baseline, engine_tuning=baseline,
        snapshot=scenario.snapshot, queue=scenario.queue))
    write(folder/"study.json", Study(identity=identity, tuning=baseline, served_model="mock", run_id="mock-study",
        pair_id="mock-pair", execution_mode="mock", requests=[{"custom_id": "mock-ready",
        "messages": [{"role": "user", "content": "Reply READY"}], "max_output_tokens": 16,
        "expected_text": "READY"}]).model_dump())
    return {"synthetic_only": True, "profile_qualified": False, "live_scheduler_enabled": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    example = sub.add_parser("demo")
    example.add_argument("--output", type=Path, required=True)
    fit = sub.add_parser("qualify")
    fit.add_argument("--input", type=Path, required=True)
    fit.add_argument("--baseline", type=Path, required=True)
    fit.add_argument("--output", type=Path, required=True)
    review = sub.add_parser("attach-review", help="Join manually reviewed invoice/quality/telemetry evidence")
    review.add_argument("--benchmark", type=Path, required=True)
    review.add_argument("--review", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)
    schema = sub.add_parser("schema")
    schema.add_argument("--output", type=Path, required=True)
    replay = sub.add_parser("replay")
    replay.add_argument("--input", type=Path, required=True)
    replay.add_argument("--profile", type=Path)
    replay.add_argument("--use-profile", action="store_true")
    replay.add_argument("--output", type=Path, required=True)
    bench = sub.add_parser("benchmark", help="Direct calls to existing authorized capacity; never provisions")
    bench.add_argument("--study", type=Path, required=True)
    bench.add_argument("--base-url", required=True)
    bench.add_argument("--timeout", type=float, default=120)
    bench.add_argument("--execute", action="store_true")
    bench.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "demo":
        print(json.dumps(demo(args.output)))
        return
    if args.output.exists():
        raise ValueError("Refusing to overwrite evidence")
    if args.action == "schema":
        report = {name: cls.model_json_schema() for name, cls in
                  (("study", Study), ("observation", Observation), ("tuning", Tuning),
                   ("replay", Replay), ("review", Review), ("profile", Profile))}
    elif args.action == "attach-review":
        row = attach(json.loads(read(args.benchmark)), Review.model_validate_json(read(args.review)))
        report = row.model_dump()
    elif args.action == "qualify":
        rows = [Observation.model_validate_json(line) for line in read(args.input).splitlines() if line.strip()]
        report = qualify(rows, Tuning.model_validate_json(read(args.baseline)), now=time.time())
    elif args.action == "replay":
        scenario = Replay.model_validate_json(read(args.input))
        profile = json.loads(read(args.profile))["profile"] if args.profile else None
        report = recommend(identity=scenario.identity, baseline=scenario.baseline, engine_tuning=scenario.engine_tuning,
            snapshot=scenario.snapshot, queue=scenario.queue, now=scenario.now, hard_limit=scenario.hard_limit,
            tenant_remaining=scenario.tenant_remaining, profile=Profile.model_validate(profile) if profile else None,
            use_profile=args.use_profile)
    else:
        if not args.execute:
            raise ValueError("Explicit --execute required; no network calls made")
        study = Study.model_validate_json(read(args.study))
        origin = endpoint(args.base_url)
        key = os.getenv("THROUGHPUT_ENGINE_KEY", "")
        if "\r" in key or "\n" in key:
            raise ValueError("Invalid engine credential")
        intent = args.output.with_suffix(args.output.suffix+".intent.json")
        records_path = args.output.with_suffix(args.output.suffix+".records.jsonl")
        if intent.exists() or records_path.exists():
            raise ValueError("Existing intent requires reconciliation; automatic replay refused")
        write(intent, {"study_sha256": digest(study), "run_id": study.run_id, "pair_id": study.pair_id,
                       "requests": len(study.requests), "execution_mode": study.execution_mode,
                       "scope": "direct_engine", "automatic_replay_allowed": False})

        async def run():
            with records_path.open("x", encoding="utf-8") as records:
                os.chmod(records_path, 0o600)
                def record(row):
                    records.write(json.dumps(row, allow_nan=False)+"\n")
                    records.flush()
                async with httpx.AsyncClient(base_url=origin, trust_env=False, follow_redirects=False,
                    headers={"Authorization": "Bearer "+key} if key else {}) as client:
                    return await measure(study, client, timeout_seconds=args.timeout, record_sink=record)
        report = asyncio.run(run())
    write(args.output, report)
    print(json.dumps({"written": str(args.output), "live_scheduler_enabled": False}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Input validation and transport errors can embed prompts or header values.
        raise SystemExit("Throughput command failed: "+type(error).__name__) from None
