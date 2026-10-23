import argparse
import json
from datetime import datetime
from packages.common.config import settings
from packages.common.db import Session
from packages.common.service import account, new_key, lock_wallet, post, reconcile, purge, reconcile_request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed", "reconcile", "purge", "reconcile-request", "rotate-encryption", "scheduling-report", "gpu-invoice", "gpu-attach", "gpu-record-stop"])
    parser.add_argument("--email", default="developer@example.local")
    parser.add_argument("--micro-usd", type=int, default=10000000)
    parser.add_argument("--reference", default="initial")
    parser.add_argument("--request-id")
    parser.add_argument("--input-tokens", type=int)
    parser.add_argument("--output-tokens", type=int)
    parser.add_argument("--release-only", action="store_true")
    parser.add_argument("--instance-id")
    parser.add_argument("--provider")
    parser.add_argument("--gpu-type")
    parser.add_argument("--billing-increment-seconds", type=int, default=60)
    parser.add_argument("--startup-seconds", type=int)
    parser.add_argument("--invoiced-through", help="ISO UTC timestamp; cumulative cost from recorded instance start")
    parser.add_argument("--invoice-micro-usd", type=int)
    parser.add_argument("--hourly-micro-usd", type=int)
    parser.add_argument("--started-at")
    parser.add_argument("--stopped-at")
    args = parser.parse_args()
    with Session.begin() as s:
        if args.command == "scheduling-report":
            from packages.common.performance import operations_report
            print(json.dumps(operations_report(s), indent=2))
        elif args.command == "gpu-invoice":
            from packages.common.economics import record_invoice
            if not all((args.instance_id, args.provider, args.gpu_type, args.invoiced_through)) or args.reference == "initial" or args.invoice_micro_usd is None:
                raise SystemExit("Require --instance-id --provider --gpu-type --reference --invoiced-through --invoice-micro-usd")
            through = datetime.fromisoformat(args.invoiced_through)
            if through.tzinfo is None:
                raise SystemExit("Timezone required")
            record_invoice(s, args.instance_id, args.provider, args.gpu_type, args.billing_increment_seconds,
                           args.invoice_micro_usd, args.reference, through, args.startup_seconds)
            print(json.dumps({"recorded": True, "customer_wallet_changed": False}))
        elif args.command == "gpu-attach":
            from packages.common.economics import record_attachment
            if not args.started_at or args.hourly_micro_usd is None:
                raise SystemExit("Require --started-at --hourly-micro-usd --instance-id --provider --gpu-type")
            started = datetime.fromisoformat(args.started_at)
            if started.tzinfo is None:
                raise SystemExit("Timezone required")
            record_attachment(s, args.instance_id, args.provider, args.gpu_type, args.hourly_micro_usd, started,
                              args.billing_increment_seconds, args.startup_seconds or 0)
            print(json.dumps({"recorded": True, "provider_contacted": False}))
        elif args.command == "gpu-record-stop":
            from sqlalchemy import select
            from packages.common.db import Instance, Audit, now
            if not args.stopped_at or args.reference == "initial":
                raise SystemExit("Require --instance-id --stopped-at --reference; stop and verify billing at provider FIRST")
            stopped = datetime.fromisoformat(args.stopped_at)
            instance = s.scalar(select(Instance).where(Instance.id == args.instance_id).with_for_update())
            if stopped.tzinfo is None or instance is None or not instance.created_at <= stopped <= now():
                raise SystemExit("Known instance and valid timezone-aware shutdown time required")
            if instance.terminated_at and instance.terminated_at != stopped:
                raise SystemExit("Shutdown already recorded at a different timestamp")
            instance.terminated, instance.terminated_at = True, stopped
            s.add(Audit(kind="manual_gpu_stop_recorded", reference=args.instance_id + ":" + args.reference))
            print(json.dumps({"recorded": True, "provider_contacted": False}))
        elif args.command == "seed":
            if settings().environment != "development":
                raise SystemExit("Development only")
            t = account(s, "dev:" + args.email)
            w = lock_wallet(s, t.id)
            if args.micro_usd < 0:
                raise SystemExit("Positive credits required")
            post(s, w, "seed:" + t.id + ":" + args.reference, "topup", args.micro_usd, 0)
            print(json.dumps({"tenant_id": t.id, **new_key(s, t.id, "CLI seed")}))
        elif args.command == "rotate-encryption":
            from sqlalchemy import select
            from packages.common.db import Work, Tenant
            from packages.common.security import encrypt, decrypt

            if not settings().encryption_active_key:
                raise SystemExit("Configure an active versioned encryption key first")
            changed = 0
            for model, fields in [(Work, ["payload", "output"]), (Tenant, ["webhook_secret"])]:
                for row in s.scalars(select(model).with_for_update()):
                    for field in fields:
                        value = getattr(row, field)
                        if value is not None:
                            setattr(row, field, encrypt(decrypt(value)))
                            changed += 1
            print(json.dumps({"reencrypted_fields": changed}))
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
