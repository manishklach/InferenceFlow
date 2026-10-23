# Scheduler simulation comparison — seed 42

Generated with `python -m scripts.benchmark_scheduler --seed 42 --count 240 --output docs/performance/simulation-v0.3-seed42.json`. This is an offline synthetic experiment, not GPU measurements or an economic advantage claim. Each row has 240 requests from eight tenants.

| Workload | Policy | Succeeded | p95 successful latency (s) | Accepted requests successful within target | Slot utilization proxy | Estimated total-token CPM (micro-USD) | Failed / retried attempts |
|---|---|---:|---:|---:|---:|---:|---:|
| low | baseline | 240 | 24 | 100.0% | 3.9% | 1924113 | 0 / 0 |
| low | deadline | 240 | 24 | 100.0% | 3.9% | 1924113 | 0 / 0 |
| low | adaptive | 240 | 24 | 100.0% | 3.9% | 1924113 | 0 / 0 |
| bursty | baseline | 240 | 284 | 100.0% | 71.4% | 601285 | 0 / 0 |
| bursty | deadline | 240 | 284 | 100.0% | 71.4% | 601285 | 0 / 0 |
| bursty | adaptive | 240 | 261 | 100.0% | 38.9% | 561201 | 0 / 0 |
| sustained | baseline | 240 | 382 | 100.0% | 82.5% | 561201 | 0 / 0 |
| sustained | deadline | 240 | 385 | 100.0% | 82.2% | 561201 | 0 / 0 |
| sustained | adaptive | 240 | 332 | 100.0% | 43.8% | 440944 | 0 / 0 |
| mixed | baseline | 195 | 357 | 72.5% | 80.4% | 585453 | 0 / 0 |
| mixed | deadline | 198 | 364 | 68.8% | 80.6% | 617496 | 0 / 0 |
| mixed | adaptive | 212 | 311 | 82.5% | 43.8% | 491670 | 0 / 0 |
| outage | baseline | 240 | 436 | 100.0% | 74.6% | 641372 | 15 / 15 |
| outage | deadline | 240 | 440 | 100.0% | 75.3% | 641372 | 15 / 15 |
| outage | adaptive | 240 | 341 | 100.0% | 37.0% | 521115 | 4 / 4 |
| capacity_change | baseline | 240 | 364 | 100.0% | 72.8% | 641372 | 15 / 15 |
| capacity_change | deadline | 240 | 364 | 100.0% | 72.6% | 641372 | 15 / 15 |
| capacity_change | adaptive | 240 | 300 | 100.0% | 32.1% | 561201 | 5 / 5 |

## Interpretation

The deadline-only policy is not a universal improvement. On mixed short deadlines it can improve successful completion count while worsening the fraction of all accepted requests completed successfully within their targets. Compare both columns; successful-only percentiles hide expired and failed work. Adaptive dispatch is more favorable in several scenarios under this particular synthetic saturation curve, which deliberately makes excess concurrency inefficient. Actual vLLM behavior may differ completely. Low load shows no scheduling gain.

The utilization field measures occupied request slots divided by rented GPU slot-seconds; it is not NVIDIA utilization. An algorithm can improve completion time while lowering this proxy by avoiding excessive slot occupancy. Cost uses a hypothetical $1/hour per GPU, upward-rounded 60-second billing increments, including cold/idle/outage intervals. Input/output lengths, service rates and scaling are assumed.

Raw JSON includes p50/p95/p99, queue latency, throughput, successful-only attainment, all-accepted success fraction, tenant completion-rate Jain fairness, costs, failures and retries. No real model output quality, GPU kernels, VRAM fit or actual provider bill was measured. The baseline reproduces the prior score formula in the same simulator; it does not run the PostgreSQL service. V2 and adaptive variants call the production policy/controller, but the virtual engine, queue and failure clock are synthetic. Use the integration suite separately for database/lease/wallet correctness.
