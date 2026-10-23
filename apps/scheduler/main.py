import time
import json
from packages.common.config import settings
from packages.common.db import Session
from packages.common.service import schedule, purge, reconcile
from packages.common.webhooks import enqueue


def tick():
    with Session.begin() as s:
        schedule(s)
    with Session.begin() as s:
        enqueue(s)
        purge(s)
    with Session.begin() as s:
        if reconcile(s):
            print('{"alert":"wallet_reconciliation_drift"}', flush=True)


def main():
    c = settings()
    print(json.dumps({"component": "scheduler_policy_configuration", "scheduler_v2_enabled": c.scheduler_v2_enabled,
                      "adaptive_dispatch_enabled": c.adaptive_dispatch_enabled, "max_inflight": c.max_inflight,
                      "provisioning_enabled": c.provisioning_enabled}), flush=True)
    while True:
        try:
            tick()
        except Exception:
            print('{"alert":"scheduler_tick_failed"}', flush=True)
        time.sleep(1)


if __name__ == "__main__":
    main()
