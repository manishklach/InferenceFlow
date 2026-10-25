"""Offline before/after evidence, with an explicit pending result before GPU execution."""
import argparse
import json
from pathlib import Path


def compare(before, after=None):
    result = {"before": before, "after": after,
              "real_after_measurements_available": after is not None,
              "decision": "NO-GO", "basis": "Second GPU measurements and equivalent hosted economics are pending"}
    if after:
        if (before.get("accepted_requests") == after.get("accepted_requests") == 100
                and before.get("passed") and after.get("passed")
                and before.get("accepted_to_last_terminal_seconds") is not None
                and after.get("accepted_to_last_terminal_seconds") is not None):
            result["baseline_100_completion_change_seconds"] = (
                after["accepted_to_last_terminal_seconds"]-before["accepted_to_last_terminal_seconds"])
        result["workload_equivalence_verified"] = False
        result["basis"] = "Measured change only; commercial GO additionally requires recovery, coverage, invoice, quality and equivalent hosted comparison gates"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", help="Actual second-run read-only audit; omit while unexecuted")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    before = before.get("audit", before)
    after = json.loads(Path(args.after).read_text(encoding="utf-8")) if args.after else None
    if after:
        after = after.get("audit", after)
    with Path(args.output).open("x", encoding="utf-8") as out:
        json.dump(compare(before, after), out, indent=2)


if __name__ == "__main__":
    main()
