import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from pydantic import ValidationError

from packages.common.deepinfer_measurement import NativeRun, summarize
from scripts.deepinfer_preflight import audit


def packet(**updates):
    return {"token_id": 42, "draft_tok": 0, "accept_tok": 0, "finished": False, "finish_reason": "", **updates}


def run_data():
    return {"engine_commit": "553741557a57df44a46fb3ab72b6aafeaf945337",
            "model_revision": "1bae0e1088993b9b82de08f59de5be5a34e42170",
            "execution_mode": "mock", "measurement_kind": "actual_emitted_token_events",
            "expected_requests": 1, "data_parallel_ranks": 1, "gpu_count": 4, "cohort_wall_seconds": 10.0,
            "requests": [{"request_id": "fixture", "dp_rank": 0, "output": [
                packet(draft_tok=6, accept_tok=3), packet(), packet(finished=True, finish_reason="stop")]}]}


class NativeMeasurementTests(unittest.TestCase):
    def test_actual_tokens_do_not_assume_full_draft_acceptance_or_multiply_by_gpus(self):
        result = summarize(NativeRun.model_validate(run_data()))
        self.assertEqual(result["successful_emitted_tokens"], 3)
        self.assertEqual(result["proposed_draft_tokens"], 5)
        self.assertEqual(result["accepted_draft_tokens"], 2)
        self.assertEqual(result["observed_draft_acceptance"], .4)
        self.assertEqual(result["successful_emitted_tokens_per_second"], .3)
        self.assertNotEqual(result["successful_emitted_tokens"], 6)  # nominal full acceptance
        self.assertIsNone(result["final_answer_tokens"])
        self.assertFalse(result["eligible_for_final_answer_throughput_profile"])
        self.assertNotIn("token_id", json.dumps(result))

    def test_failed_work_stays_in_admissions_and_elapsed_time_but_not_successful_tokens(self):
        data = run_data()
        data["expected_requests"] = 2
        data["requests"].append({"request_id": "unfinished", "dp_rank": 0, "output": [packet(), packet()]})
        result = summarize(NativeRun.model_validate(data))
        self.assertEqual(result["all_emitted_tokens"], 5)
        self.assertEqual(result["successful_emitted_tokens"], 3)
        self.assertEqual(result["unsuccessful_or_unfinished_requests"], 1)
        self.assertEqual(result["successful_emitted_tokens_per_second"], .3)

    def test_no_draft_baseline_has_unknown_not_zero_acceptance(self):
        data = run_data()
        data["requests"][0]["output"] = [packet(finished=True, finish_reason="stop")]
        self.assertIsNone(summarize(NativeRun.model_validate(data))["observed_draft_acceptance"])

    def test_length_cutoff_is_not_successful_completion(self):
        data = run_data()
        data["requests"][0]["output"][-1]["finish_reason"] = "length"
        result = summarize(NativeRun.model_validate(data))
        self.assertEqual(result["successful_emitted_tokens"], 0)
        self.assertEqual(result["all_emitted_tokens"], 3)
        self.assertEqual(result["unsuccessful_or_unfinished_requests"], 1)

    def test_duplicate_rank_request_and_missing_request_are_rejected(self):
        data = run_data()
        data["expected_requests"] = 2
        with self.assertRaises(ValidationError):
            NativeRun.model_validate(data)
        data["requests"] *= 2
        with self.assertRaises(ValidationError):
            NativeRun.model_validate(data)

    def test_two_dp_ranks_count_each_emitted_stream_once(self):
        data = run_data()
        data.update(expected_requests=2, data_parallel_ranks=2, gpu_count=8)
        data["requests"].append({**data["requests"][0], "dp_rank": 1})
        self.assertEqual(summarize(NativeRun.model_validate(data))["successful_emitted_tokens"], 6)

    def test_nominal_microbenchmark_is_not_a_native_event_record(self):
        with self.assertRaises(ValidationError):
            NativeRun.model_validate({"avg_SPS": 100.0, "nextn": 5, "decode_num_requests": 64})
        for update in ({"accept_tok": 7, "draft_tok": 6}, {"token_id": -1}, {"draft_tok": True}):
            data = run_data()
            data["requests"][0]["output"][0] = packet(**update)
            with self.assertRaises(ValidationError):
                NativeRun.model_validate(data)
        data = run_data()
        data["cohort_wall_seconds"] = float("nan")
        with self.assertRaises(ValidationError):
            NativeRun.model_validate(data)


class SourceAuditTests(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL).strip()

    def checkout(self, root):
        self.git(root, "init", "-q")
        self.git(root, "config", "core.autocrlf", "false")
        self.git(root, "config", "user.email", "fixture@example.invalid")
        self.git(root, "config", "user.name", "Fixture")
        (root/"build.sh").write_bytes(b"#!/bin/bash\necho fixture\n")
        self.git(root, "add", "build.sh")
        self.git(root, "commit", "-qm", "fixture")
        return {"commit": self.git(root, "rev-parse", "HEAD"), "files": {
            "build.sh": hashlib.sha256((root/"build.sh").read_bytes()).hexdigest()}, "nvidia_submodules": {}}

    def test_source_audit_never_reports_native_build_or_gpu_execution_as_verified(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            lock = self.checkout(root)
            result = audit(root, lock)
            self.assertTrue(result["source_contract_passed"])
            self.assertFalse(result["native_cuda_build_verified"])
            self.assertFalse(result["gpu_execution_verified"])
            self.assertFalse(result["deployable"])
            with self.assertRaises(ValueError):
                audit(root, {**lock, "commit": "0"*40})
            with self.assertRaises(ValueError):
                audit(root, {**lock, "files": {"build.sh": "0"*64}})
            (root/"build.sh").write_text("changed\n")
            with self.assertRaises(ValueError):
                audit(root, lock)

    def test_path_traversal_is_not_a_source_contract(self):
        with TemporaryDirectory() as name:
            parent = Path(name)
            root = parent/"checkout"
            root.mkdir()
            lock = self.checkout(root)
            (parent/"outside").write_text("private")
            with self.assertRaises(ValueError):
                audit(root, {**lock, "files": {"../outside": "0"*64}})

    def test_vendor_gitlink_pin_is_checked_without_claiming_vendor_build(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            lock = self.checkout(root)
            vendor = root/"vendor/DeepEP"
            vendor.mkdir(parents=True)
            vendor_commit = lock["commit"]
            self.git(root, "update-index", "--add", "--cacheinfo", f"160000,{vendor_commit},vendor/DeepEP")
            self.git(root, "commit", "-qm", "vendor fixture")
            lock.update(commit=self.git(root, "rev-parse", "HEAD"), nvidia_submodules={"vendor/DeepEP": vendor_commit})
            result = audit(root, lock)
            self.assertEqual(result["vendor_pins_verified"], 1)
            self.assertFalse(result["vendor_checkouts_initialized"]["vendor/DeepEP"])
            with self.assertRaises(ValueError):
                audit(root, {**lock, "nvidia_submodules": {"vendor/DeepEP": "0"*40}})
