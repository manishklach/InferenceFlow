import time
from packages.common.db import Session
from packages.common.service import schedule, purge, reconcile
from packages.common.webhooks import enqueue, deliver


def tick():
    with Session.begin() as s:
        schedule(s)
    with Session.begin() as s:
        enqueue(s)
        purge(s)
    deliver()
    with Session.begin() as s:
        if reconcile(s):
            print('{"alert":"wallet_reconciliation_drift"}', flush=True)


def main():
    while True:
        try:
            tick()
        except Exception:
            print('{"alert":"scheduler_tick_failed"}', flush=True)
        time.sleep(1)


if __name__ == "__main__":
    main()
