import time
from packages.common.providers import RunpodProvider, watchdog

if __name__ == "__main__":
    while True:
        try:
            watchdog(RunpodProvider())
        except Exception:
            print('{"alert":"provider_watchdog_failed"}', flush=True)
        time.sleep(60)
