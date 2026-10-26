"""Trusted-runner-only scheduling changes. No HTTP control route or provider calls."""

import argparse
import json
import time

from dotenv import dotenv_values
import httpx

from scripts import github_staging_host as host
from scripts.staging_supervisor import private_write

POLICIES = {"sequential": (False, False, 1), "baseline": (False, False, 4),
            "deadline_fixed": (True, False, 4), "adaptive": (True, True, 4)}
IDLE = ("from sqlalchemy import select,func; from packages.common.db import Session,Work; "
        "s=Session(); n=s.scalar(select(func.count()).select_from(Work).where("
        "Work.status.in_(['queued','leased','running','billing_pending']))); "
        "assert n==0, 'Unresolved work'; print('IDLE'); s.close()")


def expected(policy):
    v2, adaptive, cap = POLICIES[policy]
    return {"scheduler_v2_enabled": v2, "adaptive_dispatch_enabled": adaptive, "max_inflight": cap}


def verify(config, policy, mode):
    wanted = {**expected(policy), "execution_mode": mode, "public_beta_enabled": False,
              "stripe_enabled": False, "provisioning_enabled": False, "estimator_calibrated": False}
    if any(config.get(key) != value for key, value in wanted.items()):
        raise RuntimeError("Effective policy or safety flags mismatch")


def switch(policy, runtime, origin, *, docker=host.docker, write_env=host.write_env, fetch=None):
    desired = expected(policy)  # Reject unknown input before any action.
    values = dict(dotenv_values(runtime / "control.env"))
    if (values.get("ENVIRONMENT") != "staging" or values.get("EXECUTION_MODE") not in {"mock", "vllm"}
            or any(values.get(k) != "false" for k in
                   ("PUBLIC_BETA_ENABLED", "STRIPE_ENABLED", "PROVISIONING_ENABLED"))
            or values.get("RUNPOD_API_KEY") or (runtime / "STOP").exists()):
        raise RuntimeError("Isolated, unarmed staging configuration required")
    if docker("exec", "-T", "api", "python", "-c", IDLE).stdout.strip() != "IDLE":
        raise RuntimeError("Idle boundary required")
    private_write(runtime / "maintenance.json", json.dumps({"expires_at_epoch": time.time()+180}))
    try:
        # Stop admission and scheduling, then repeat the DB check to close the admission race.
        docker("stop", "--timeout", "15", "scheduler", "api")
        if docker("run", "--rm", "--no-deps", "api", "python", "-c", IDLE).stdout.strip() != "IDLE":
            raise RuntimeError("Work arrived during transition")
        values.update(SCHEDULER_V2_ENABLED=str(desired["scheduler_v2_enabled"]).lower(),
                      ADAPTIVE_DISPATCH_ENABLED=str(desired["adaptive_dispatch_enabled"]).lower(),
                      MAX_INFLIGHT=str(desired["max_inflight"]), ESTIMATOR_CALIBRATED="false")
        write_env(runtime / "control.env", values)
        docker("up", "-d", "--wait", "api", "scheduler")
        if fetch is None:
            with httpx.Client(base_url=origin, timeout=15, trust_env=False) as client:
                response = client.get("/internal/scheduling/report",
                                      headers={"Authorization": "Bearer "+values["METRICS_TOKEN"]})
                response.raise_for_status()
                config = response.json()["configuration"]
        else:
            config = fetch()
        verify(config, policy, values["EXECUTION_MODE"])
        private_write(runtime / "current-policy.json", json.dumps({"policy": policy, "configuration": config}))
    except BaseException:
        # Never silently restore admission or continue load after an ambiguous transition.
        private_write(runtime / "STOP", "Policy transition failed; supervisor must shut down")
        raise
    finally:
        (runtime / "maintenance.json").unlink(missing_ok=True)
    return {"policy": policy, "verified": True, "gpu_measurement": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", choices=POLICIES)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--real", action="store_true", help="Use the existing real-image Compose overlay")
    args = parser.parse_args()
    if args.real:
        host.COMPOSE += ["-f", str(host.ROOT / "infra/github-staging/real.yml")]
    print(json.dumps(switch(args.policy, host.RUNTIME, args.origin)))


if __name__ == "__main__":
    main()
