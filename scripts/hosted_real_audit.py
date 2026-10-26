"""Read-only audit of the current disposable GitHub experiment tenant."""

import argparse
import json
import re


def audit(identity):
    from sqlalchemy import select, text
    from packages.common.config import settings
    from packages.common.db import Session, Tenant, Job
    from scripts.audit_gpu_run import audit_run
    cfg = settings()
    if (not re.fullmatch(r"[0-9]+-[0-9]+", identity) or cfg.environment != "staging"
            or cfg.execution_mode != "vllm" or not cfg.reviewed_gpu_experiment_enabled
            or cfg.provisioning_enabled or cfg.public_beta_enabled or cfg.stripe_enabled or cfg.runpod_api_key):
        raise RuntimeError("Isolated real experiment required")
    with Session.begin() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        tenant = session.scalar(select(Tenant).where(Tenant.subject == "github-disposable-real:"+identity))
        if not tenant:
            raise RuntimeError("Experiment tenant missing")
        ids = list(session.scalars(select(Job.id).where(Job.tenant_id == tenant.id)))
        report = audit_run(session, ids) if ids else {"passed": True, "accepted_requests": 0}
        if ids and report["statuses"] != {"succeeded": report["accepted_requests"]}:
            report["passed"] = False
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", required=True)
    report = audit(parser.parse_args().identity)
    print(json.dumps(report))  # Captured privately by the trusted host, not relayed to CI logs.
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
