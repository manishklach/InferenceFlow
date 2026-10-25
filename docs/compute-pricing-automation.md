# GitHub-hosted hourly GPU and CPU price history

The [hourly pricing workflow](../.github/workflows/compute-pricing.yml) runs on a standard GitHub-hosted Ubuntu runner, independent of the developer computer. It runs at minute 17 of each hour (UTC; minute 17 in PDT too) and can be started manually. GitHub schedules are best-effort and may be delayed; missed hours stay gaps. It does not rent compute or change RunPod resources.

## Credential separation

Use a dedicated **read-only** RunPod key in the repository Actions secret `RUNPOD_PRICING_API_KEY`. Enter it directly with:

```powershell
gh secret set RUNPOD_PRICING_API_KEY --repo manishklach/InferenceFlow
```

Do not paste it into chat, code, a file, workflow input, URL or log. Do not reuse `RUNPOD_CLEANUP_API_KEY`. The protected `gpu-experiment` environment, its owner approvals and its read/write cleanup credential remain unchanged. The pricing workflow has no access to that environment or secret. Creating a read-only key is an owner action; successful catalog reads alone cannot attest a key's configured scope.

## Reads and publication

The standard-library collector calls only fixed HTTPS **GET** endpoints on `api.runpod.io/v2/catalog`: all GPU entries separately for Community and Secure Cloud, plus all CPU Pod families with two-vCPU availability. It sets no CUDA, memory, manufacturer or region filters. Requests use a Bearer header, TLS verification, no redirects and bounded retries for transport/429/5xx failures. Authentication failures are not retried and provider response bodies are not logged.

All three catalogs must be fetched and validated before appending either history. Empty, malformed, duplicate or unexpectedly paginated results fail rather than fabricate a complete snapshot. Both datasets share a collection timestamp and identify their source as REST v2. Historical MCP observations retain their original provenance. Valid raw observations are retained; previously invalidated renderer replays remain raw but are excluded from exports and charts.

The workflow's short-lived GitHub token writes only eight explicitly staged generated files:

- GPU `observations.jsonl`, `hourly.csv`, `daily.csv`, `latest.md`, `rates.svg` under `docs/gpu-rates/`.
- CPU `observations.jsonl`, `hourly.csv`, `daily.csv` under `docs/cpu-rates/`.

No provider key or runtime file is staged. The commit uses `[skip ci]`; the pricing job already runs its focused collection/history tests, and routine snapshots should not rerun the entire platform test suite. Concurrent pricing runs serialize. Pushes are never forced; branch-protection/conflict failures stop publication and retain the public snapshot/history as a 30-day workflow artifact for review. Recovery must merge the snapshot without replacing other observations or relabeling an old response with a new time. GitHub's write token is not used as a RunPod credential.

The live [GPU Hourly Rates and CPU page](https://inferenceflow-execution.abc123xyza.chatgpt.site/gpu-hourly-rates/) reads the main-branch histories directly; no Sites deployment is needed per collection. It labels snapshot fallback/stale data. Prices exclude disk/tax, GPU quotes are per GPU-hour, CPU quotes per vCPU-hour, and CPU instance costs are estimates. Stock at two vCPUs is not stock assurance for 32 vCPUs.

## Manual verification and failures

```powershell
gh workflow run compute-pricing.yml --repo manishklach/InferenceFlow --ref main
gh run list --repo manishklach/InferenceFlow --workflow compute-pricing.yml --limit 5
```

Confirm the run succeeds, a bot commit reaches main, both JSONL histories contain the new matching UTC timestamp, earlier valid rows remain present, and website readback shows it. A dispatched or queued run alone is not proof of collection. Missing secrets, expired/read-disallowed keys, schema changes, network errors, disabled Actions or denied branch writes are failures, not zero prices. Review the failed run/artifact and fix the cause; never bypass protected environment approvals or substitute a more privileged key.

The previous Codex local hourly follow-up is paused only after the first GitHub-hosted collection and website readback are verified. The GitHub schedule then continues when this computer is locked, sleeping or off. Its timing remains subject to [GitHub schedule semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
