"""Authenticate the approved experiment reader without modifying provider resources."""

import json
import os

from scripts.experiment_telemetry import PodReader


def main():
    reader = None
    try:
        reader = PodReader(os.environ.get("RUNPOD_EXPERIMENT_READ_KEY", ""))
        reader.authenticate()
    except Exception as error:
        # Never print provider response bodies, headers or credential values.
        raise SystemExit("Experiment read preflight failed: "+type(error).__name__) from None
    finally:
        if reader is not None:
            reader.close()
    print(json.dumps({"authenticated_pod_read": True, "provider_mutations": False,
                      "log_stream_permission_tested": False, "gpu_created": False}))


if __name__ == "__main__":
    main()
