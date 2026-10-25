"""Pod-private phase markers and offline duration accounting; never provisions."""
import argparse
import json
import os
import re
from datetime import datetime, timezone, timedelta


def mark(phase):
    print(json.dumps({"event": "experiment_phase", "phase": phase,
                      "observed_at": datetime.now(timezone.utc).isoformat()}), flush=True)


def cold_start(events):
    lookup = {e["phase"]: datetime.fromisoformat(e["observed_at"].replace("Z", "+00:00")) for e in events}
    pairs = {"pod_allocation": ("pod_create_requested", "image_pull_started"),
             "image_pull": ("image_pull_started", "image_pull_finished"),
             "worker_bootstrap": ("container_bootstrap_started", "worker_environment_ready"),
             "model_download": ("model_download_started", "model_download_finished"),
             "engine_initialization_inclusive": ("engine_launch_requested", "engine_health_ready"),
             "model_weight_loading": ("model_loading_started", "model_loading_finished"),
             "compilation": ("compilation_started", "compilation_finished"),
             "health_readiness_tail": ("compilation_finished", "engine_health_ready"),
             "rental_to_engine_health": ("pod_created", "engine_health_ready")}
    result = {}
    for phase, (start, end) in pairs.items():
        a, b = lookup.get(start), lookup.get(end)
        result[phase] = {"seconds": (b-a).total_seconds() if a and b and b >= a else None,
                         "start_event": start, "end_event": end}
    return {"phases": result, "additive": False,
            "warning": "Engine initialization includes loading/compilation; do not sum inclusive phases. Provider image markers are required for allocation/pull separation; missing markers stay unknown. Download includes cache/metadata checks."}


def extract_events(items):
    """Parse retained provider log entries, preserving provenance for derived times."""
    events = {}
    def add(phase, timestamp, source):
        events.setdefault(phase, {"phase": phase, "observed_at": timestamp, "source": source})
    for item in sorted(items, key=lambda r: r["ts"]):
        line, timestamp = item["line"], item["ts"]
        if line.startswith('{'):
            try:
                data = json.loads(line)
                if data.get("event") == "experiment_phase":
                    add(data["phase"], data["observed_at"], "pod_utc_marker")
            except ValueError:
                pass
        if item.get("source") == "system":
            if re.search(r"Pulling image|Pulling from|Downloading", line):
                add("image_pull_started", timestamp, "provider_first_download_observation")
            if re.search(r"Digest: sha256|Successfully pulled|Status: Downloaded|image is up to date", line, re.I):
                add("image_pull_finished", timestamp, "provider_pull_completion")
        for pattern, start, end in ((r"torch\.compile takes ([0-9.]+) s", "compilation_started", "compilation_finished"),
                                     (r"Model loading took .* and ([0-9.]+) seconds", "model_loading_started", "model_loading_finished")):
            match = re.search(pattern, line)
            if match:
                ended = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                add(end, ended.isoformat(), "provider_log_of_engine_report")
                add(start, (ended-timedelta(seconds=float(match[1]))).isoformat(), "derived_from_engine_reported_duration")
    return list(events.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["mark", "download"])
    parser.add_argument("--phase")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.action == "mark":
        mark(args.phase)
    else:
        if not args.execute:
            raise SystemExit("Download disabled: explicit experiment execution required")
        from huggingface_hub import snapshot_download
        revision = os.environ["MODEL_REVISION"]
        if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
            raise SystemExit("Pinned model revision required")
        mark("model_download_started")
        snapshot_download(os.environ["MODEL_REPO"], revision=revision,
                          allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.tiktoken", "*.jinja"])
        mark("model_download_finished")


if __name__ == "__main__":
    main()
