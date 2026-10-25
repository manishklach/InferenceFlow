"""Append read-only MCP catalog observations and render a dependency-free rate chart.

Input: JSON array of get_gpu_type responses, each augmented with cloud.
No provider credentials, provisioning or network access are used by this script.
"""
import csv
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main():
    folder = Path(__file__).resolve().parents[1] / "docs/gpu-rates"
    folder.mkdir(exist_ok=True)
    observed = datetime.now(timezone.utc).isoformat()
    incoming = json.load(sys.stdin)
    rows = []
    for item in incoming:
        cloud = item["cloud"]
        assert cloud in ("SECURE", "COMMUNITY")
        rows.append({"observed_at_utc": observed, "gpu": item["name"],
                     "gpu_id": item["id"], "vram_gb": item["memory"], "cloud": cloud,
                     "cloud_supported": item.get(cloud.lower()),
                     "gpu_usd_per_hour": item["price"][cloud.lower()],
                     "availability": item["availability"],
                     "data_centers": item.get("dataCenters", []),
                     "source": "RunPod MCP GPU catalog", "cuda_floor": item.get("cuda_floor")})
    history = folder / "observations.jsonl"
    with history.open("a", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    all_rows = [row for line in history.read_text().splitlines() if line
                for row in [json.loads(line)] if not row.get("invalidated")]
    fields = ["observed_at_utc", "gpu", "vram_gb", "cloud", "gpu_usd_per_hour", "availability"]
    with (folder / "hourly.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)
    groups = {}
    for row in all_rows:
        groups.setdefault((row["observed_at_utc"][:10], row["gpu"], row["cloud"]), []).append(row)
    with (folder / "daily.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["utc_date", "gpu", "cloud", "samples", "min_gpu_usd_per_hour", "mean_gpu_usd_per_hour", "max_gpu_usd_per_hour", "samples_with_stock"])
        for key, values in sorted(groups.items()):
            prices = [r["gpu_usd_per_hour"] for r in values]
            writer.writerow([*key, len(values), min(prices), sum(prices)/len(prices), max(prices), sum(r["availability"] != "NONE" for r in values)])
    series = {}
    for row in all_rows:
        series.setdefault(f'{row["gpu"]} / {row["cloud"]}', []).append(row)
    times = [datetime.fromisoformat(r["observed_at_utc"]).timestamp() for r in all_rows]
    start, end = min(times), max(times)
    ceiling = max(r["gpu_usd_per_hour"] for r in all_rows) * 1.15
    height = max(540, 140 + len(series) * 35)
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}">',
           f'<rect width="1200" height="{height}" fill="#101827"/>',
           '<g font-family="sans-serif" fill="#e5e7eb">',
           '<text x="45" y="35" font-size="23">RunPod GPU rental quotes — observed history</text>',
           '<text x="45" y="60" font-size="13">USD per GPU-hour; excludes storage/tax. Hollow dots: no stock. No historical backfill.</text>']
    for tick in range(6):
        y = 400 - tick * 60
        svg += [f'<path d="M70 {y} H770" stroke="#334155"/>', f'<text x="15" y="{y+5}">${ceiling*tick/5:.2f}</text>']
    colors = ["#60a5fa", "#fbbf24", "#34d399", "#fb7185", "#c084fc", "#22d3ee"]
    for index, (name, values) in enumerate(sorted(series.items())):
        color = colors[index % len(colors)]
        points = []
        for row in values:
            t = datetime.fromisoformat(row["observed_at_utc"]).timestamp()
            x = 70 + 700 * (t-start)/max(1, end-start)
            y = 400 - 300 * row["gpu_usd_per_hour"]/ceiling
            points.append(f"{x:.2f},{y:.2f}")
            fill = "#101827" if row["availability"] == "NONE" else color
            svg.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="{fill}" stroke="{color}" stroke-width="2"/>')
        # Lines connect observations only; gaps are not inferred measurements.
        svg.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2"/>')
        svg.append(f'<text x="795" y="{105+index*35}" fill="{color}" font-size="13">{html.escape(name)}</text>')
    svg += [f'<text x="70" y="435" font-size="12">{html.escape(min(r["observed_at_utc"] for r in all_rows))}</text>',
            f'<text x="70" y="460" font-size="12">Latest: {html.escape(observed)} · {len(all_rows)} observations</text>',
            '<text x="70" y="490" font-size="12">One observation is a starting point, not evidence of an hourly or daily trend.</text>', '</g></svg>']
    (folder / "rates.svg").write_text("\n".join(svg), encoding="utf-8")
    latest = {}
    for row in all_rows:
        latest[(row["gpu"], row["cloud"])] = row
    table = ["# Latest RunPod catalog quotes", "", "GPU-only USD/hour; storage and taxes excluded. NONE means no stock, not a rentable offer.", "", "| GPU | VRAM GB | Cloud | USD/hour | Stock | Observed UTC |", "|---|---:|---|---:|---|---|"]
    for row in sorted(latest.values(), key=lambda r: (r["gpu"], r["cloud"])):
        table.append(f'| {row["gpu"]} | {row["vram_gb"]} | {row["cloud"]} | {row["gpu_usd_per_hour"]:.4f} | {row["availability"]} | {row["observed_at_utc"]} |')
    (folder / "latest.md").write_text("\n".join(table) + "\n", encoding="utf-8")
    print(f"Recorded {len(rows)} quotes; regenerated hourly.csv, daily.csv and rates.svg")


if __name__ == "__main__":
    main()
