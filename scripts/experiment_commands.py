"""Main-repository command mailbox for one disposable GitHub host; no public API."""

from datetime import datetime, timezone
import json
import re
import time

import httpx

from scripts.experiment_policy import POLICIES, switch
from scripts.staging_supervisor import private_write

COMMAND_URL = "https://raw.githubusercontent.com/manishklach/InferenceFlow/main/docs/experiments/host-command.json"


def validate(command, run_id, previous, now):
    if set(command) != {"run_id", "sequence", "expires_at", "policy"}:
        raise ValueError("Exact non-secret policy command required")
    if command["run_id"] != run_id:
        return False
    if type(command["sequence"]) is not int or command["sequence"] != previous+1:
        return False
    expires = datetime.fromisoformat(command["expires_at"].replace("Z", "+00:00"))
    if expires.tzinfo is None or not 0 < (expires-now).total_seconds() <= 600:
        return False
    if command["policy"] not in {*POLICIES, "audit"}:
        raise ValueError("Unknown scheduling policy")
    return True


class Mailbox:
    def __init__(self, runtime, origin, run_id, *, transition=switch, clock=time.monotonic, audit=None):
        if not re.fullmatch(r"[0-9]+-[0-9]+", run_id):
            raise ValueError("GitHub run-attempt identity required")
        self.runtime, self.origin, self.run_id = runtime, origin, run_id
        self.transition, self.clock, self.last_poll = transition, clock, float("-inf")
        self.previous = 0
        self.audit = audit
        receipt = runtime / "command-receipt.json"
        if receipt.exists():
            record = json.loads(receipt.read_text())
            if record["run_id"] != run_id:
                raise RuntimeError("Mailbox receipt belongs to another host")
            self.previous = record["sequence"]

    def tick(self, fetch=None):
        if self.clock()-self.last_poll < 15:
            return
        self.last_poll = self.clock()
        try:
            if fetch is None:
                with httpx.Client(timeout=4, trust_env=False, follow_redirects=False) as client:
                    response = client.get(COMMAND_URL, params={"fresh": time.time_ns()})
                    if response.status_code == 404:
                        return
                    response.raise_for_status()
                    if len(response.content) > 2048:
                        raise ValueError("Oversized command")
                    command = response.json()
            else:
                command = fetch()
        except (httpx.HTTPError, ValueError):
            # A failed read cannot authorize a transition. Normal host supervision continues.
            return
        if not validate(command, self.run_id, self.previous, datetime.now(timezone.utc)):
            return
        # Consume before any mutation. Ambiguous crashes cannot replay a restart.
        self.previous = command["sequence"]
        receipt = {"run_id": self.run_id, "sequence": self.previous, "policy": command["policy"],
                   "status": "started"}
        private_write(self.runtime / "command-receipt.json", json.dumps(receipt))
        try:
            if self.audit is not None:
                report = self.audit()
                if report.get("passed") is not True:
                    raise RuntimeError("Experiment billing/timing audit failed")
                private_write(self.runtime / f"stage-audit-{self.previous}.json", json.dumps(report))
            elif command["policy"] == "audit":
                raise RuntimeError("No audit executor configured")
            if command["policy"] != "audit":
                self.transition(command["policy"], self.runtime, self.origin)
            receipt["status"] = "verified"
        except Exception:
            receipt["status"] = "failed"
            private_write(self.runtime / "STOP", "Policy command failed; stop this host")
            raise
        finally:
            private_write(self.runtime / "command-receipt.json", json.dumps(receipt))
        print(json.dumps({"host_policy_command": receipt}), flush=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Prepare only a non-secret, expiring host command; no network calls")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--sequence", required=True, type=int)
    parser.add_argument("--policy", required=True, choices=[*POLICIES, "audit"])
    args = parser.parse_args()
    command = {"run_id": args.run_id, "sequence": args.sequence, "policy": args.policy,
               "expires_at": datetime.fromtimestamp(time.time()+600, timezone.utc).isoformat()}
    if not re.fullmatch(r"[0-9]+-[0-9]+", args.run_id) or args.sequence < 1:
        raise ValueError("Run-attempt and positive sequence required")
    from scripts.github_staging_host import ROOT
    (ROOT / "docs/experiments/host-command.json").write_text(json.dumps(command, indent=2)+"\n")
    print("Prepared non-secret command. Review and commit to main to deliver; no GPU created.")


if __name__ == "__main__":
    main()
