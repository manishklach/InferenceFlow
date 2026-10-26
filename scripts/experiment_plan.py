"""Bounded stage orchestration shared by hosted real execution and mock rehearsal."""

from dataclasses import dataclass
import json
import time

from scripts.staging_supervisor import private_write


@dataclass(frozen=True)
class Stage:
    name: str
    policy: str
    count: int
    seconds: int
    optional: bool = False


STAGES = (Stage("smoke", "baseline", 10, 120), Stage("sequential", "sequential", 100, 300),
          Stage("baseline-a", "baseline", 100, 180), Stage("adaptive-a", "adaptive", 100, 180),
          Stage("adaptive-b", "adaptive", 100, 180), Stage("baseline-b", "baseline", 100, 180),
          Stage("interruption", "baseline", 500, 600, True))


def run_plan(directory, deadline, *, transition, execute, audit, coverage, healthy=lambda: None,
             stages=STAGES, clock=time.monotonic):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    checkpoint = directory / "checkpoint.json"
    if checkpoint.exists():
        raise RuntimeError("Existing stage intent requires reconciliation; automatic replay refused")
    state = {"mode": "experiment", "status": "running", "stages": [], "in_progress": None}

    def save():
        private_write(checkpoint, json.dumps(state, indent=2))

    save()
    try:
        for stage in stages:
            # Keep time for policy restart, read-only audit and orderly evidence export.
            if deadline-clock() < stage.seconds+90:
                state.update(status="incomplete", reason="insufficient_time", skipped=stage.name)
                save()
                return state
            healthy()
            state["in_progress"] = {"name": stage.name, "phase": "transition"}
            save()
            transition(stage.policy)
            healthy()
            remaining = min(stage.seconds, int(deadline-clock()-60))
            if remaining <= 0:
                raise RuntimeError("No execution time remains after policy change")
            state["in_progress"]["phase"] = "admission_intent"
            save()  # Persist before any HTTP submission; never blindly replay an ambiguous stage.
            result = execute(stage, remaining)
            if result.get("successful_requests") != stage.count:
                raise RuntimeError("Stage incomplete; no further admissions")
            healthy()
            receipt = audit(stage, result)
            if receipt.get("passed") is not True:
                raise RuntimeError("Billing/timing audit failed; no further admissions")
            if stage.name == "smoke" and coverage(stage, result).get("passed") is not True:
                raise RuntimeError("Smoke telemetry coverage failed; no further admissions")
            state["stages"].append({"name": stage.name, "policy": stage.policy, "count": stage.count,
                                    "audit_passed": True, "result": result})
            state["in_progress"] = None
            save()
        state["status"] = "completed"
        save()
        return state
    except BaseException as error:
        state.update(status="failed", error_type=type(error).__name__)
        save()
        raise
