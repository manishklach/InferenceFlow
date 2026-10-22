"""Callback delivery is isolated from inference dispatch and recovery."""

import time
from packages.common.webhooks import deliver


def main():
    while True:
        try:
            deliver()
        except Exception:
            print('{"alert":"callback_delivery_failed"}', flush=True)
        time.sleep(1)


if __name__ == "__main__":
    main()
