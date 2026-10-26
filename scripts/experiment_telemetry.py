"""GET-only RunPod log collection on the trusted experiment runner."""

from datetime import datetime, timezone
import json
import os
import re
import threading
import time

import httpx
from scripts.second_gpu_experiment import coverage

BASE = "https://api.runpod.io/v2"


class PodReader:
    def __init__(self, key, transport=None):
        if not key:
            raise ValueError("Dedicated read-only experiment key required")
        self.client = httpx.Client(base_url=BASE, headers={"Authorization": "Bearer "+key},
            timeout=httpx.Timeout(10, read=8), trust_env=False, follow_redirects=False, transport=transport)

    def authenticate(self):
        r = self.client.get("/pods", params={"limit": 1})
        r.raise_for_status()
        if not isinstance(r.json().get("pods"), list):
            raise RuntimeError("Pod-read authentication failed")

    def pod(self, pod_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", pod_id):
            raise ValueError("Invalid pod ID")
        r = self.client.get("/pods/"+pod_id)
        r.raise_for_status()
        return r.json()

    def close(self):
        self.client.close()


def events(lines):
    """Parse documented SSE events, retaining opaque reconnect IDs."""
    data, event_id = [], None
    for line in lines:
        if not line:
            if data:
                record = json.loads("\n".join(data))
                if record.get("source") not in {"container", "system"} or not isinstance(record.get("line"), str):
                    raise ValueError("Invalid provider event")
                if event_id and (len(event_id) > 256 or "\r" in event_id or "\n" in event_id):
                    raise ValueError("Invalid reconnect ID")
                yield event_id, record
            data, event_id = [], None
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif line.startswith("id:"):
            event_id = line[3:].strip()


class Collector:
    def __init__(self, reader, pod_id, directory):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", pod_id):
            raise ValueError("Invalid pod ID")
        self.reader, self.pod_id, self.directory = reader, pod_id, directory
        self.stop = threading.Event()
        self.samples, self.seen, self.cursor = {}, set(), None
        self.last_valid = float("-inf")
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def accept(self, event_id, record, output):
        key = (record.get("ts"), record["source"], record["line"])
        if key not in self.seen:
            self.seen.add(key)
            output.write(json.dumps(record)+"\n")
            output.flush()
            try:
                sample = json.loads(record["line"])
                if sample.get("event") == "engine_sample":
                    with self.lock:
                        self.samples[sample["observed_at"]] = sample
                        if sample.get("engine_metrics") and sample.get("nvidia_smi_csv"):
                            observed = datetime.fromisoformat(sample["observed_at"].replace("Z", "+00:00"))
                            age = (datetime.now(timezone.utc)-observed).total_seconds()
                            valid = coverage([sample], observed.timestamp(), observed.timestamp()+1)["passed"]
                            if valid and -2 <= age <= 10:
                                self.last_valid = time.monotonic()
            except (ValueError, TypeError, AttributeError, KeyError):
                pass  # Non-metric engine/system logs remain private evidence.
        self.cursor = event_id or self.cursor

    def run(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.directory / "provider-logs.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            while not self.stop.is_set():
                try:
                    headers = {"Last-Event-ID": self.cursor} if self.cursor else {}
                    params = {"source": "both"} if self.cursor else {"source": "both", "tail": 5000}
                    with self.reader.client.stream("GET", "/pods/"+self.pod_id+"/logs",
                                                   params=params, headers=headers) as response:
                        response.raise_for_status()
                        for event_id, record in events(response.iter_lines()):
                            self.accept(event_id, record, output)
                            if self.stop.is_set():
                                break
                except (httpx.HTTPError, ValueError, TypeError):
                    self.stop.wait(2)  # Reconnect with the same cursor; no provider mutations.

    def snapshot(self):
        with self.lock:
            return list(self.samples.values())

    def healthy(self):
        if not self.thread.is_alive() or time.monotonic()-self.last_valid > 30:
            raise RuntimeError("Fresh compact telemetry missing; stop admissions")

    def close(self):
        self.stop.set()
        self.thread.join(timeout=12)
