import argparse
import json
from packages.common.config import settings
from packages.common.db import Session
from packages.common.service import account, new_key, lock_wallet, post, reconcile, purge, reconcile_request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed", "reconcile", "purge", "reconcile-request"])
    parser.add_argument("--email", default="developer@example.local")
    parser.add_argument("--micro-usd", type=int, default=10000000)
    parser.add_argument("--reference", default="initial")
    parser.add_argument("--request-id")
    parser.add_argument("--input-tokens", type=int)
    parser.add_argument("--output-tokens", type=int)
    parser.add_argument("--release-only", action="store_true")
    args = parser.parse_args()
    with Session.begin() as s:
        if args.command == "seed":
            if settings().environment != "development":
                raise SystemExit("Development only")
            t = account(s, "dev:" + args.email)
            w = lock_wallet(s, t.id)
            if args.micro_usd < 0:
                raise SystemExit("Positive credits required")
            post(s, w, "seed:" + t.id + ":" + args.reference, "topup", args.micro_usd, 0)
            print(json.dumps({"tenant_id": t.id, **new_key(s, t.id, "CLI seed")}))
        elif args.command == "reconcile":
            drift = reconcile(s)
            print(json.dumps({"drift": drift}))
            if drift:
                raise SystemExit(1)
        elif args.command == "reconcile-request":
            if (
                not args.request_id
                or args.input_tokens is None
                or args.output_tokens is None
                or args.reference == "initial"
            ):
                raise SystemExit("Require --request-id --input-tokens --output-tokens --reference reviewed-ticket")
            reconcile_request(
                s, args.request_id, args.input_tokens or 0, args.output_tokens or 0, args.reference, args.release_only
            )
        else:
            purge(s)


if __name__ == "__main__":
    main()
