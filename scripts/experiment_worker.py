"""Opt-in one-shot worker interruption for a separately approved synthetic run."""
import argparse
import asyncio
import json
import os
from pathlib import Path


class Interruption:
    def __init__(self, prefix, after, marker):
        if not prefix.startswith("gpu-test-") or after < 1:
            raise ValueError("Synthetic gpu-test- prefix and positive completion count required")
        self.prefix, self.after, self.marker, self.count = prefix, after, Path(marker), 0

    def success(self, item):
        if not item["payload"].get("custom_id", "").startswith(self.prefix):
            return False
        self.count += 1
        if self.count < self.after:
            return False
        self.marker.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Exclusive create persists across process restart, preventing a crash loop.
            with self.marker.open("x", encoding="utf-8") as output:
                output.write("one-shot worker interruption fired\n")
        except FileExistsError:
            return False
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-interruption", action="store_true")
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--after", type=int, default=5)
    parser.add_argument("--marker", required=True)
    args = parser.parse_args()
    if not args.enable_interruption:
        raise SystemExit("Fault injection disabled; explicit experiment authorization required")
    from apps.worker.main import main as worker_main
    from apps.worker.engines import VllmInferenceEngine
    policy = Interruption(args.prefix, args.after, args.marker)
    original = VllmInferenceEngine.execute

    async def execute(engine, item):
        output = await original(engine, item)
        if policy.success(item):
            print(json.dumps({"experiment_event": "interruption_after_engine_before_finalize", "exit_code": 75}), flush=True)
            os._exit(75)
        return output

    VllmInferenceEngine.execute = execute
    asyncio.run(worker_main())


if __name__ == "__main__":
    main()
