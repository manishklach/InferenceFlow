# CPU rental price history

RunPod Secure Cloud CPU Pods, all returned CPU3/CPU5 families. [Live page](https://inferenceflow-execution.abc123xyza.chatgpt.site/gpu-hourly-rates/#cpu-rates).

- `observations.jsonl`: append-only timestamped provider observations.
- `hourly.csv`: every collected observation; missed hours are not fabricated.
- `daily.csv`: per-UTC-day min/mean/max observed **USD per vCPU-hour**, with sample counts.

Prices are per vCPU-hour, not per physical CPU or complete instance. Instance estimates multiply that rate by the chosen vCPU count. RAM follows each family's GB-per-vCPU ratio. Disk, tax and other charges are excluded. Availability is queried for **two vCPUs**; it is not evidence that a larger shape is currently available. Serverless prices/availability are outside this Pod dataset.

Collector: read-only MCP `list_cpu_types(include=[AVAILABILITY], product=[POD], vcpuCount=2)`. Feed its `cpus` array through stdin to `python -m scripts.cpu_rate_history`. No credentials are stored, no compute is rented, and valid earlier observations are retained. The website reads the public repository history; its bundled snapshot is an explicitly labeled fallback. The local hourly collector requires the app and connector to remain available.
