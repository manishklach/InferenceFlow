"""Persist read-only RunPod CPU Pod quotes; prices are per vCPU-hour."""
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main():
    folder = Path(__file__).resolve().parents[1] / "docs/cpu-rates"
    folder.mkdir(parents=True, exist_ok=True)
    incoming = json.load(sys.stdin)
    observed = datetime.now(timezone.utc).isoformat()
    rows = [{"observed_at_utc": observed, "cpu_id": item["id"], "cpu_name": item["name"],
             "group": item["group"], "ram_gb_per_vcpu": item["ramGbPerVcpu"],
             "min_vcpu": item["vcpu"]["min"], "max_vcpu": item["vcpu"]["max"],
             "usd_per_vcpu_hour": item["price"]["securePerVcpu"],
             "cloud": "SECURE", "product": "POD", "availability_vcpu_count": 2,
             "availability": item["availability"], "data_centers": item.get("dataCenters", []),
             "source": "RunPod MCP list_cpu_types"} for item in incoming]
    history = folder / "observations.jsonl"
    with history.open("a", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, sort_keys=True) + "\n")
    all_rows = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines() if line]
    fields = ["observed_at_utc", "cpu_id", "cpu_name", "group", "ram_gb_per_vcpu", "usd_per_vcpu_hour", "cloud", "availability_vcpu_count", "availability"]
    with (folder / "hourly.csv").open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)
    groups = {}
    for row in all_rows:
        groups.setdefault((row["observed_at_utc"][:10], row["cpu_id"]), []).append(row["usd_per_vcpu_hour"])
    with (folder / "daily.csv").open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["utc_date", "cpu_id", "samples", "min_usd_per_vcpu_hour", "mean_usd_per_vcpu_hour", "max_usd_per_vcpu_hour"])
        for key, prices in sorted(groups.items()):
            writer.writerow([*key, len(prices), min(prices), sum(prices) / len(prices), max(prices)])
    print(f"Appended {len(rows)} CPU quotes; retained {len(all_rows)} observations")


if __name__ == "__main__":
    main()
