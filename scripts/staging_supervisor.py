"""Bounded, host-independent Compose supervision. Never provisions cloud resources."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time


class HealthReadFailed(RuntimeError):
    pass


def private_write(path, content):
    # Diagnostics can contain provider/Compose details: never publish to CI logs.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(content)


def running_services(command, diagnostics, *, attempts=3, timeout=10, sleep=time.sleep,
                     run=subprocess.run, permitted=lambda: True):
    """Retry read failures only; a successful empty response means nothing is running."""
    for attempt in range(1, attempts + 1):
        if not permitted():
            raise HealthReadFailed("Supervision deadline or stop requested")
        try:
            result = run(command + ["ps", "--status", "running", "--services"],
                         capture_output=True, text=True, timeout=timeout, check=False)
            if result.returncode == 0:
                return set(result.stdout.split())
            record = {"attempt": attempt, "returncode": result.returncode,
                      "stderr": result.stderr, "observed_at_epoch": time.time()}
        except (subprocess.TimeoutExpired, OSError) as exc:
            stderr = getattr(exc, "stderr", None)
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            record = {"attempt": attempt, "error_type": type(exc).__name__,
                      "stderr": stderr, "observed_at_epoch": time.time()}
        private_write(diagnostics / f"docker-read-{time.time_ns()}-{attempt}.json", json.dumps(record))
        if attempt < attempts:
            sleep(attempt)
    raise HealthReadFailed("Docker health query failed after bounded retries; inspect private diagnostics")


def monitor(command, diagnostics, deadline, required, stop_file, *, clock=time.monotonic,
            sleep=time.sleep, read=running_services, stopped=lambda: False):
    while clock() < deadline and not stop_file.exists() and not stopped():
        def permitted():
            return clock() < deadline and not stop_file.exists() and not stopped()
        services = read(command, diagnostics, permitted=permitted)
        maintenance = diagnostics / "maintenance.json"
        active_required = required
        if maintenance.exists():
            marker = json.loads(maintenance.read_text(encoding="utf-8"))
            until = marker["expires_at_epoch"]
            if time.time() < until <= time.time()+180:
                active_required = {"postgres"}
        missing = active_required - services
        if missing:
            raise RuntimeError("Required staging services stopped: " + ", ".join(sorted(missing)))
        private_write(diagnostics / "heartbeat.json", json.dumps({"observed_at_epoch": time.time(),
                      "remaining_seconds": max(0, deadline-clock()), "services": sorted(services),
                      "maintenance": active_required != required}))
        sleep(min(2, max(0, deadline-clock())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file", type=Path, required=True)
    parser.add_argument("--diagnostics", type=Path, required=True)
    parser.add_argument("--minutes", type=int, default=120)
    parser.add_argument("--required", nargs="+", default=["postgres", "api", "scheduler"])
    parser.add_argument("--start", action="store_true", help="Start existing configured services, without building")
    args = parser.parse_args()
    if not 1 <= args.minutes <= 120:
        parser.error("Duration must be 1–120 minutes")
    if not args.compose_file.is_file():
        parser.error("Existing Compose configuration required")
    args.diagnostics.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        args.diagnostics.chmod(0o700)
    if (args.diagnostics / "STOP").exists():
        parser.error("STOP marker exists; explicitly choose a new experiment directory")
    command = ["docker", "compose", "-f", str(args.compose_file.resolve())]
    deadline = time.monotonic() + args.minutes*60
    stopping = False

    def stop_signal(signum, frame):
        nonlocal stopping
        stopping = True

    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, stop_signal)
    reason = "deadline_or_operator_stop"
    try:
        if args.start:
            result = subprocess.run(command + ["up", "-d", "--wait", *args.required],
                                    capture_output=True, text=True, timeout=180, check=False)
            if result.returncode:
                private_write(args.diagnostics / "startup-stderr.txt", result.stderr)
                raise RuntimeError("Staging start failed; inspect private diagnostics")
        monitor(command, args.diagnostics, deadline, set(args.required), args.diagnostics / "STOP",
                stopped=lambda: stopping)
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        reason = type(exc).__name__
        raise SystemExit("Staging supervision failed; inspect private diagnostics") from None
    finally:
        # Query errors retry before this point. Exhausted retries fail closed.
        try:
            result = subprocess.run(command + ["stop", "--timeout", "15"],
                                    capture_output=True, text=True, timeout=45, check=False)
            private_write(args.diagnostics / "stop-stderr.txt", result.stderr)
            state = {"reason": reason, "stop_returncode": result.returncode}
        except (subprocess.SubprocessError, OSError) as exc:
            state = {"reason": reason, "stop_error": type(exc).__name__}
        private_write(args.diagnostics / "stopped.json", json.dumps(state))


if __name__ == "__main__":
    main()
