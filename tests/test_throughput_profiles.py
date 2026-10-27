import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import unittest

import httpx
from pydantic import ValidationError

from packages.common.throughput import (Identity, Observation, Pending, Profile, Snapshot,
                                       Tuning, digest, qualify, recommend)
from packages.common.throughput_benchmark import Study, measure
from packages.common.throughput_evidence import Review, attach
from scripts.throughput_profile import demo, endpoint


def identity():
    return Identity(model="test-only/model", revision="a"*40, tokenizer_revision="b"*40,
        engine="vllm", engine_digest="sha256:"+"c"*64, runtime_config_sha256="d"*64,
        precision="bf16", gpu="test-only", gpu_count=1, topology="test-only",
        context_limit=4096, prompt_min=1, prompt_max=1024, output_max=512)


BASE = Tuning(concurrency=2, resident_token_budget=4096, max_batched_tokens=1024, draft_tokens=0)
CANDIDATE = BASE.model_copy(update={"concurrency": 4, "resident_token_budget": 8192})


def observations():
    # Artificial test fixtures, never saved as real GPU measurements.
    return [Observation(identity=identity(), tuning=tuning, run_id=f"fixture-{pair}-{tag}", pair_id=str(pair),
        workload_sha256="f"*64, execution_mode="real", scope="direct_engine", total_requests=100,
        successful_requests=100, successful_output_tokens=tokens, elapsed_seconds=60.0, p95_seconds=10.0,
        quality_score=1.0, final_token_counts_known=True, cost_usd=1.0, cost_scope="full_rental_invoiced",
        telemetry_coverage=1.0, peak_memory_fraction=.5, evidence_sha256=digest({"fixture": pair, "tag": tag}))
        for pair in range(3) for tag, tuning, tokens in (("base", BASE, 10000), ("candidate", CANDIDATE, 12500))]


def qualified_profile():
    return Profile.model_validate(qualify(observations(), BASE, now=1000.0)["profile"])


class QualificationTests(unittest.TestCase):
    def test_paired_sustained_trials_produce_integrity_checked_profile_and_deterministic_selection(self):
        rows = observations()
        report = qualify(rows, BASE, now=1000.0)
        self.assertEqual(report, qualify(list(reversed(rows)), BASE, now=1000.0))
        self.assertFalse(report["live_scheduler_enabled"])
        self.assertAlmostEqual(report["candidates"][0]["minimum_paired_gain"], .25)
        profile = Profile.model_validate(report["profile"])
        self.assertTrue(profile.integrity_valid())
        self.assertFalse(profile.model_copy(update={"expires_at_epoch": 99999999.0}).integrity_valid())

    def test_single_bad_repeat_is_not_filtered_out_to_manufacture_a_win(self):
        cases = [{"successful_requests": 99}, {"oom_count": 1}, {"quality_score": None},
                 {"quality_score": .99}, {"p95_seconds": 12.0}, {"cost_usd": 2.0},
                 {"telemetry_coverage": .5}, {"peak_memory_fraction": None},
                 {"peak_memory_fraction": .95}, {"successful_output_tokens": 11000},
                 {"execution_mode": "mock"}, {"cost_scope": "warm_estimate"},
                 {"final_token_counts_known": False}, {"elapsed_seconds": 1.0},
                 {"total_requests": 101, "successful_requests": 101}]
        for update in cases:
            with self.subTest(update=update):
                rows = observations()
                rows[1] = rows[1].model_copy(update=update)
                result = qualify(rows, BASE, now=1000.0)
                self.assertIsNone(result["profile"])
                self.assertTrue(result["candidates"][0]["reasons"])

    def test_incomplete_pairs_and_duplicate_run_or_evidence_are_rejected(self):
        self.assertIsNone(qualify(observations()[:-2], BASE, now=1000.0)["profile"])
        for update in ({"run_id": "fixture-0-base"}, {"evidence_sha256": observations()[0].evidence_sha256}):
            rows = observations()
            rows[1] = rows[1].model_copy(update=update)
            with self.assertRaises(ValueError):
                qualify(rows, BASE, now=1000.0)
        rows = observations()
        rows[1] = rows[1].model_copy(update={"pair_id": "missing"})
        self.assertIsNone(qualify(rows, BASE, now=1000.0)["profile"])

    def test_model_hardware_tokenizer_scope_and_workload_cannot_be_mixed(self):
        for field, value in (("revision", "e"*40), ("tokenizer_revision", "e"*40),
                             ("gpu_count", 2), ("topology", "other"), ("runtime_config_sha256", "e"*64)):
            rows = observations()
            rows[1] = rows[1].model_copy(update={"identity": identity().model_copy(update={field: value})})
            with self.assertRaises(ValueError):
                qualify(rows, BASE, now=1000.0)
        for update in ({"scope": "queue_pipeline"}, {"workload_sha256": "e"*64}):
            rows = observations()
            rows[1] = rows[1].model_copy(update=update)
            with self.assertRaises(ValueError):
                qualify(rows, BASE, now=1000.0)

    def test_strict_input_rejects_nonfinite_boolean_counts_and_floating_model_revision(self):
        for update in ({"elapsed_seconds": float("nan")}, {"cost_usd": float("inf")},
                       {"total_requests": True}, {"successful_requests": 101}):
            data = observations()[0].model_dump()
            with self.assertRaises(ValidationError):
                Observation.model_validate({**data, **update})
        with self.assertRaises(ValidationError):
            Identity.model_validate({**identity().model_dump(), "revision": "main"})


class AdvisoryTests(unittest.TestCase):
    def replay(self, **changes):
        values = dict(identity=identity(), baseline=BASE, engine_tuning=BASE,
            snapshot=Snapshot(observed_at_epoch=1000.0, active_requests=0, resident_tokens=0,
                              memory_fraction=.5, error_rate=0.0, p95_seconds=10.0),
            queue=[Pending(request_id=str(i), tenant_id="a" if i < 2 else "b", prompt_tokens=512,
                           output_limit=64, deadline_epoch=1200.0) for i in range(4)],
            now=1001.0, hard_limit=4, tenant_remaining={"a": 4, "b": 4}, profile=qualified_profile())
        values.update(changes)
        return recommend(**values)

    def test_disabled_default_tenant_caps_and_real_hard_cap_survive_qualified_profile(self):
        self.assertEqual(len(self.replay()["admit"]), 2)
        result = self.replay(use_profile=True, tenant_remaining={"a": 1, "b": 1})
        self.assertEqual(result["admit"], ["0", "2"])
        self.assertFalse(result["live_scheduler_enabled"])
        self.assertEqual(len(result["admit"])+len(result["deferred"]), 4)
        self.assertEqual(len(self.replay(use_profile=True, hard_limit=2)["admit"]), 2)

    def test_stale_future_and_critical_memory_do_not_create_capacity(self):
        for timestamp, memory in ((900.0, .5), (1010.0, .5), (900.0, .95)):
            snapshot = Snapshot(observed_at_epoch=timestamp, active_requests=0, resident_tokens=0,
                                memory_fraction=memory, error_rate=0.0, p95_seconds=1.0)
            self.assertEqual(self.replay(use_profile=True, snapshot=snapshot)["admit"], [])

    def test_profile_expiry_identity_and_error_fallback_do_not_expand(self):
        self.assertEqual(len(self.replay(use_profile=True, now=99999999.0)["admit"]), 0)  # stale telemetry
        self.assertEqual(len(self.replay(use_profile=True,
            identity=identity().model_copy(update={"revision": "e"*40}))["admit"]), 2)
        bad = Snapshot(observed_at_epoch=1000.0, active_requests=0, resident_tokens=0,
                       memory_fraction=.5, error_rate=.2, p95_seconds=10.0)
        self.assertEqual(len(self.replay(use_profile=True, snapshot=bad)["admit"]), 2)

    def test_static_engine_flags_require_reconfiguration_and_fallback_does_not_fake_it(self):
        profile = qualified_profile()
        tuning = profile.tuning.model_copy(update={"draft_tokens": 5})
        profile = profile.model_copy(update={"tuning": tuning})
        profile = profile.model_copy(update={"profile_sha256": digest(profile.model_dump(exclude={"profile_sha256"}))})
        self.assertIn("engine_reconfiguration_required", self.replay(use_profile=True, profile=profile)["reason"])
        bad = Snapshot(observed_at_epoch=1000.0, active_requests=0, resident_tokens=0,
                       memory_fraction=.5, error_rate=.2, p95_seconds=10.0)
        self.assertEqual(self.replay(use_profile=True, profile=profile, engine_tuning=tuning, snapshot=bad)["admit"], [])

    def test_token_budget_uses_prompt_plus_output_not_engine_batch_tokens(self):
        snapshot = Snapshot(observed_at_epoch=1000.0, active_requests=0, resident_tokens=4000,
                            memory_fraction=.5, error_rate=0.0, p95_seconds=10.0)
        self.assertEqual(self.replay(snapshot=snapshot)["admit"], [])
        self.assertEqual(len(self.replay(use_profile=True)["admit"]), 4)

    def test_expired_and_out_of_bucket_are_deferred_without_leases_or_deadline_promises(self):
        queue = [Pending(request_id="expired", tenant_id="a", prompt_tokens=10,
                         output_limit=10, deadline_epoch=900.0),
                 Pending(request_id="too-long", tenant_id="a", prompt_tokens=1025,
                         output_limit=10, deadline_epoch=1200.0)]
        result = self.replay(queue=queue)
        self.assertEqual(result["admit"], [])
        self.assertFalse(result["deadline_guaranteed"])


class BenchmarkTests(unittest.IsolatedAsyncioTestCase):
    def study(self, count=4):
        return Study(identity=identity(), tuning=BASE, served_model="pinned-test-id", run_id="test",
            pair_id="0", execution_mode="mock", requests=[{"custom_id": str(i),
            "messages": [{"role": "user", "content": "Reply READY"}], "max_output_tokens": 16,
            "expected_text": "READY"} for i in range(count)])

    def response(self, *, details=True):
        return {"choices": [{"message": {"content": "READY"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2,
                          **({"completion_tokens_details": {"reasoning_tokens": 0}} if details else {})}}

    async def test_real_async_overlap_is_bounded_and_failures_stay_in_denominator(self):
        active = peak = calls = 0
        async def respond(request):
            nonlocal active, peak, calls
            if request.url.path == "/v1/models":
                return httpx.Response(200, json={"data": [{"id": "pinned-test-id"}]})
            calls += 1
            call = calls
            active += 1
            peak = max(active, peak)
            await asyncio.sleep(.01)
            active -= 1
            return httpx.Response(503, text="private body") if call == 2 else httpx.Response(200, json=self.response())
        async with httpx.AsyncClient(base_url="https://unit.invalid", transport=httpx.MockTransport(respond)) as client:
            result = await measure(self.study(), client)
        self.assertEqual(peak, 2)
        self.assertEqual(result["observation"]["successful_requests"], 3)
        self.assertEqual(result["observation"]["total_requests"], 4)
        self.assertEqual(result["observation"]["successful_output_tokens"], 6)
        self.assertEqual(len(result["records"]), 4)
        self.assertNotIn("private body", json.dumps(result))
        self.assertNotIn('"content": "READY"', json.dumps(result))

    async def test_missing_reasoning_accounting_is_unknown_not_synthetic_output_tokens(self):
        def respond(request):
            return httpx.Response(200, json={"data": [{"id": "pinned-test-id"}]} if request.url.path == "/v1/models"
                                  else self.response(details=False))
        async with httpx.AsyncClient(base_url="https://unit.invalid", transport=httpx.MockTransport(respond)) as client:
            result = await measure(self.study(1), client)
        self.assertFalse(result["observation"]["final_token_counts_known"])
        self.assertIsNone(result["records"][0]["final_output_tokens"])
        self.assertEqual(result["records"][0]["reported_generated_tokens"], 2)

    async def test_deadline_cancels_active_and_waiting_requests_with_durable_records(self):
        async def respond(request):
            if request.url.path == "/v1/models":
                return httpx.Response(200, json={"data": [{"id": "pinned-test-id"}]})
            await asyncio.sleep(10)
            return httpx.Response(200, json=self.response())
        async with httpx.AsyncClient(base_url="https://unit.invalid", transport=httpx.MockTransport(respond)) as client:
            result = await measure(self.study(), client, timeout_seconds=.01)
        self.assertEqual(len(result["records"]), 4)
        self.assertEqual(result["observation"]["successful_requests"], 0)

    async def test_truncated_reasoning_conflicts_and_malformed_answers_are_failures(self):
        truncated = self.response()
        truncated["choices"][0]["finish_reason"] = "length"
        conflict = self.response()
        conflict["choices"][0]["message"]["reasoning_content"] = "hidden reasoning"
        for payload in (truncated, conflict, {"choices": []}, self.response() | {"usage": {}}):
            with self.subTest(payload=payload):
                def respond(request):
                    return httpx.Response(200, json={"data": [{"id": "pinned-test-id"}]}
                        if request.url.path == "/v1/models" else payload)
                async with httpx.AsyncClient(base_url="https://unit.invalid", transport=httpx.MockTransport(respond)) as client:
                    result = await measure(self.study(1), client)
                self.assertEqual(result["observation"]["successful_requests"], 0)
                self.assertEqual(result["observation"]["successful_output_tokens"], 0)


class ReviewTests(unittest.TestCase):
    def review(self, benchmark):
        return Review(benchmark_sha256=digest(benchmark), identity_evidence_sha256="1"*64,
            invoice_evidence_sha256="2"*64, telemetry_evidence_sha256="3"*64, quality_evidence_sha256="4"*64,
            full_rental_cost_usd=1.0, telemetry_coverage=1.0, peak_memory_fraction=.5, quality_score=1.0)

    def test_review_is_bound_to_hash_and_cannot_upgrade_mock_mode_quality_or_token_unknowns(self):
        row = observations()[0].model_copy(update={"execution_mode": "mock", "quality_score": .5,
            "final_token_counts_known": False, "cost_scope": "unknown", "cost_usd": None})
        benchmark = {"observation": row.model_dump(), "records": []}
        review = self.review(benchmark)
        joined = attach(benchmark, review)
        self.assertEqual(joined.execution_mode, "mock")
        self.assertEqual(joined.quality_score, .5)
        self.assertFalse(joined.final_token_counts_known)
        self.assertEqual(joined.cost_scope, "full_rental_invoiced")
        self.assertNotEqual(joined.evidence_sha256, row.evidence_sha256)
        with self.assertRaises(ValueError):
            attach({**benchmark, "records": [{"different": True}]}, review)


class CliTests(unittest.TestCase):
    def test_cli_runs_bounded_loopback_http_and_refuses_replay_or_implicit_execution(self):
        calls = []
        payload = BenchmarkTests().response()
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append("GET")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"data": [{"id": "pinned-test-id"}]}).encode())

            def do_POST(self):
                calls.append("POST")
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode())

            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with TemporaryDirectory() as root:
                study, output = Path(root)/"study.json", Path(root)/"result.json"
                study.write_text(BenchmarkTests().study().model_dump_json(), encoding="utf-8")
                command = [sys.executable, "-m", "scripts.throughput_profile", "benchmark", "--study", str(study),
                    "--base-url", f"http://127.0.0.1:{server.server_port}", "--output", str(output)]
                env = {**os.environ, "THROUGHPUT_ENGINE_KEY": ""}
                denied = subprocess.run(command, capture_output=True, text=True, timeout=20, env=env)
                self.assertNotEqual(denied.returncode, 0)
                self.assertEqual(calls, [])
                ran = subprocess.run(command+["--execute"], capture_output=True, text=True, timeout=20, env=env)
                self.assertEqual(ran.returncode, 0, ran.stderr)
                self.assertEqual(json.loads(output.read_text())["observation"]["successful_requests"], 4)
                self.assertEqual(calls.count("POST"), 4)
                self.assertEqual(len(output.with_suffix(".json.records.jsonl").read_text().splitlines()), 4)
                output.unlink()  # Removing a summary must not make old intent replayable.
                again = subprocess.run(command+["--execute"], capture_output=True, text=True, timeout=20, env=env)
                self.assertNotEqual(again.returncode, 0)
                self.assertEqual(calls.count("POST"), 4)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_demo_cannot_qualify_synthetic_data_and_keeps_baseline_default(self):
        with TemporaryDirectory() as root:
            folder = Path(root)/"demo"
            report = demo(folder)
            self.assertTrue(report["synthetic_only"])
            self.assertIsNone(json.loads((folder/"qualification.json").read_text())["profile"])
            self.assertEqual(json.loads((folder/"recommendation.json").read_text())["admit"], ["mock-0", "mock-1"])
            with self.assertRaises(FileExistsError):
                demo(folder)

    def test_endpoint_refuses_credentials_queries_redirect_style_paths_and_plain_remote_http(self):
        self.assertEqual(endpoint("http://127.0.0.1:8000/"), "http://127.0.0.1:8000")
        for url in ("http://example.com", "https://user:key@example.com", "https://example.com/?key=secret",
                    "https://example.com/v1", "file:///tmp/x"):
            with self.assertRaises(ValueError):
                endpoint(url)
