> Current evidence: [October 25 real L4 results](../validation/2026-10-25/real-inference-report.md). Baseline 10/100 passed; transient reconnect failed during adaptive preparation. Pod terminated, no volumes remain. 1,000 requests, matched policy comparison, interruption recovery, invoice economics and full-lifetime GPU utilization remain unverified. Historical preparation statements below refer to their original dates. No public-beta or savings claim is supported.

# First GPU economics — no real measurements yet

Status: NOT EXECUTED. Input/output tokens, paid GPU runtime, startup/idle time, utilization, completed jobs, provider invoice, CPM and deadline attainment are all unknown. A planning quote is not an observed result. No20–30% advantage has been demonstrated.

Use scripts/experiment_economics.py to calculate an offline report from an explicit JSON evidence file. Required fields: input_tokens,output_tokens,successful_jobs,accepted_jobs,jobs_within_deadline,paid_seconds,startup_seconds,cost_kind (estimate or actual_invoice),cost_reference,compute_usd,storage_usd,ancillary_usd. Missing cost is not zero; obtain full coverage before calculating. Optional hardware_intervals contain nonoverlapping seconds,gpu_utilization_fraction; report observed/unobserved coverage and time-weighted mean. Zero-util intervals are a sampled idle proxy; no samples produce null idle/utilization, notzero. Guard/provider/engine evidence must supply actual coverage; metadata-only HTTP idle is distinct.

```bash
python -m scripts.experiment_economics --input PRIVATE_SESSION_EVIDENCE.json --output .runtime/final-economics.json
```

The tool never calls provider, inference or wallet APIs. It refuses overwrites, invalid totals/times/costs and inconsistent success counts. actual_invoice is operator-attested provenance, not automatic invoice verification: retain provider invoice/reference and UTC coverage. Include all creation-to-deletion startup/model download/warmup/canaries/idle/retries/cleanup, disk and tax. Do not sum per-stage allocation and add the same complete invoice again. Successful workload tokens exclude failed/retried waste but paid uptime includes that cost. Customer capture is not infrastructure spend.

Formulas: blendedCPM=full cost×1e6/(successful input+output tokens); input-normalizedCPM=full cost×1e6/input tokens; output-normalizedCPM=full cost×1e6/output tokens. Both separately normalized figures allocate the WHOLE bill; do not add them or treat them as independent customer prices. Cost/job=full cost/successful jobs. Attainment=successful within deadline/all accepted, including failed and unfinished. p50/p95/p99 and queue latency come from read-only audit_gpu_run; do not turn successful-only latency into full completionrate.

## Hosted comparison and 20–30% feasibility

The public OpenRouter models API (https://openrouter.ai/api/v1/models) returned no exact qwen/qwen3-4b entry in this session. [Its model page](https://openrouter.ai/qwen/qwen3-4b) exists but did not supply a verified purchasable equivalent paid quote. Therefore there is no honest numerical equal-revision hosted comparison yet. Do not substitute larger/quantized/different thinking-mode models, promotional/free prices or an unsourced assumed competitorprice.

The optional hosted_alternative object requires equivalent_model_and_workload=true, source, input_usd_per_million,output_usd_per_million. Before setting equivalence, verify exact revision/tokenizer or document unavoidable mismatch, precision, thinking, decoding, context, output quality, billing tokenization and service terms. Hosted cost=(input×inputprice+output×outputprice)/1e6. Advantage=1−ourFullCost/hostedCost. 20–30% savings requires ourFullCost<=0.8–0.7×equivalentHostedCost; do not claim it if invoice, quality or latency comparison is missing. Include non-GPU CPU/database/payment/operations costs when evaluating sustainable commercial margin.

## Reproducible sensitivity, explicitly hypothetical

scripts.experiment_economics.sensitivity uses full assumed hourly cost, useful tokens/s, workload token volume, utilization, startup and retry fraction. Model paid seconds=startup+tokens/(throughput×utilization×(1−retryfraction)). This simplified model is a planning assumption, not a GPU prediction.

At the RTX4090 catalog+730-hour disk estimate0.350959USD/h, ignoring unknown tax and all CPU operating costs, infinite warm throughput100/500/1000 useful tokens/s implies approximately0.975/0.195/0.0975USD blendedCPM at100% utilization. At25% utilization the warm processing component quadruples; startup adds hourlyRate×startup/3600 spread over actual volume. These rates are sensitivity inputs, NOT measured Qwen throughput. Higher volume amortizes startup; sparse arrivals reduce utilization; longer outputs change decode mix; larger models change throughput/KV needs; provider prices scale cost; retries consume capacity without duplicate customer charges. A model/length/arrival-specific measured profile must replace each assumption. Tests check monotonic idle/startup/retry effects and missing denominators.

Retain actual mixed-arrival trace, input/output lengths, scheduled concurrency, baseline/adaptive arm, measured engine counter coverage and one cumulative invoice. Real savings remain an open empirical question.
