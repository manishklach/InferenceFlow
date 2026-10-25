"""Internal disposable-tenant mock rehearsal; not a customer top-up or real-GPU tool."""

import argparse
import json
import os
from pathlib import Path
import re

from sqlalchemy import select, text

from packages.common.config import settings
from packages.common.db import Session, Tenant
from packages.common.service import account, lock_wallet, new_key, post
from scripts.audit_gpu_run import audit_run


def require_mock():
    cfg = settings()
    if (cfg.environment != "staging" or cfg.execution_mode != "mock" or cfg.provisioning_enabled
            or cfg.public_beta_enabled or cfg.stripe_enabled or cfg.reviewed_gpu_experiment_enabled):
        raise RuntimeError("Only isolated staging mock rehearsal permitted")


def seed(session, run_id):
    require_mock()
    if not re.fullmatch(r"[0-9]+-[0-9]+", run_id):
        raise ValueError("GitHub run/attempt identity required")
    if os.environ.get("HOSTED_DISPOSABLE_MOCK") != "true":
        raise RuntimeError("Disposable rehearsal identity required")
    subject = "github-disposable-mock:"+run_id
    if session.scalar(select(Tenant.id).where(Tenant.subject == subject)):
        raise RuntimeError("Refuse to reseed an existing tenant")
    tenant = account(session, subject)
    wallet = lock_wallet(session, tenant.id)
    post(session, wallet, "github-mock-test-credit:"+run_id, "topup", 1_000_000, 0)
    return {"tenant_id": tenant.id, "key": new_key(session, tenant.id, "disposable mock rehearsal")["key"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["seed", "audit"])
    parser.add_argument("--run-id")
    parser.add_argument("--job-id")
    parser.add_argument("--output")
    args = parser.parse_args()
    require_mock()
    with Session.begin() as session:
        if args.action == "seed":
            # Captured by trusted runner; never relay stdout to Actions logs.
            print(json.dumps(seed(session, args.run_id)))
        else:
            session.execute(text("SET TRANSACTION READ ONLY"))
            report = audit_run(session, [args.job_id], require_vllm=False)
            if (report["measurement_modes"] != ["mock"] or report["accepted_requests"] != 10
                    or report["statuses"] != {"succeeded": 10} or report["unique_usage_records"] != 10
                    or report["unique_capture_sources"] != 10):
                report["passed"] = False
            Path(args.output).write_text(json.dumps(report), encoding="utf-8")
            if not report["passed"]:
                raise RuntimeError("Mock pipeline audit failed")
            print(json.dumps({"mock_audit_passed": True, "requests": 10, "gpu_measurement": False}))


if __name__ == "__main__":
    main()
