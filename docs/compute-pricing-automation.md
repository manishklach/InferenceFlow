# GitHub-hosted hourly GPU and CPU price history

The [hourly pricing workflow](../.github/workflows/compute-pricing.yml) runs on a standard GitHub-hosted Ubuntu runner, independent of the developer computer. It runs at minute 43 of each hour (UTC; minute 43 in PDT too) and can be started manually. GitHub schedules are best-effort and may be delayed; missed hours stay gaps. It does not rent compute or change RunPod resources.

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

## Schedule incident: October 25, 2026

The initial manual collections succeeded at 13:53 and 16:34 UTC, but no `schedule` runs were created through 18:27 UTC. The workflow was active, on the default branch `main`, with Actions enabled. Disabling and re-enabling it did not establish recovery. This isolates the observed failure to trigger creation, rather than a failing collector or missing RunPod secret; the underlying GitHub-side cause is unconfirmed.

The recovery changes the cron from minute 17 to minute 43 in a new repository commit and records event, schedule, actor, revision and runner start time in each run summary. GitHub documents committing a cron change as recovery for some actor-related schedule failures; there is no evidence that this account was suspended or deleted. See [GitHub troubleshooting](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows#scheduled-workflow-stopped-running). `[skip ci]` applies to push/pull-request triggers and is not established as the cause here.

Verify automatic recovery separately from manual collection:

```powershell
gh run list --repo manishklach/InferenceFlow --workflow compute-pricing.yml --event schedule --limit 5 --json databaseId,event,status,conclusion,createdAt,url
```

Recovery requires a successful run with `event=schedule`, publication of both histories with a matching new timestamp, and preserved prior observations. A manual refresh never proves the scheduler works. Do not backfill missed hours using current quotes. If scheduled events still never appear after the revised schedule has had time to fire, retain the run/configuration evidence for owner escalation to GitHub Support; do not rotate a working provider key or increase its privileges.

The previous local Codex collector remains paused. The GitHub runner does not depend on this computer, but automatic hourly collection remains unverified until the above evidence exists. Timing is subject to [GitHub schedule semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
