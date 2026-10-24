# October 24 local-backend validation

**NO-GO for paid GPU provisioning; local Docker/HTTPS mock rehearsal validated.** No pod, VM, paid storage or other billable resource was created. No actual GPU utilization, vLLM batching, 60-minute completion rate or economic advantage has been measured.

The first isolated native rehearsal passed 14 checks. It was replaced with an isolated Docker rehearsal using Docker Engine 29.9.2, Compose v5.6.1, the existing locked application Dockerfile and PostgreSQL 16.9. Its migrations completed and API/PostgreSQL health checks passed. A mock worker registered and executed through an outbound connection to a temporary Cloudflare HTTPS endpoint.

The Docker run passed 14 checks: HTTPS health; mock-mode readiness; anonymous denial; invalid customer-key denial; blocked development login; blocked checkout; invalid worker-bootstrap denial; blocked cookie authentication; idempotent submission; 10 successful mock requests; wallet reconciliation; outbound worker registration; unique ledger sources; and one capture per request. The 10 synthetic requests captured 90 micro-USD from test credit. This is a mock ledger check, not a real GPU bill or an interruption/recovery experiment.

Separate checks verified that the image excludes `.env` and `.runtime`, worker configuration excludes control-plane/provider/payment secrets, and containers do not restart automatically. The existing targeted experiment-guard, readiness, comparison, interruption and economics suite passed 23 tests. Local raw evidence and temporary credentials remain ignored/private; no temporary hostname, account balance or credential is included here.

The reusable version is documented in [the local rehearsal runbook](../../local-backend-rehearsal.md). It adds a startup refusal for non-mock/paid configurations and isolates the gateway wrapper from the shared product app. That exact version was built and started as a fresh Compose project, and all 14 HTTPS checks passed again. The complete backend suite passed **128 tests with 1 real-GPU test skipped**; Ruff passed and mypy checked 34 source files. The 15 added regression cases cover gateway isolation, authentication boundaries and refusal of real/paid modes. The publishable tree was scanned against generated local secrets and credential patterns with no secret matches; the existing public development sentinel is not a private credential. CI results are recorded in the pull request.

## Remaining approval gates

| Gate | Status |
|---|---|
| Isolated API/PostgreSQL/scheduler/mock worker | Docker rehearsal passed |
| Temporary authenticated HTTPS API and outbound worker | Mock checks passed; ephemeral and dependent on the local PC |
| Genuine staging OIDC | Not configured/validated |
| RunPod cleanup credential | Operator reports R/W enabled; prior authenticated read does not prove DELETE permission |
| Independent armed watchdog | Not established; local supervisor cannot survive PC/network failure |
| Current suitable GPU stock and all-in quote | Must be refreshed before final approval |
| Pinned Qwen3-4B/vLLM actual VRAM fit | Requires approved GPU canary |
| Real workloads, interruption and exactly-once settlement | Pending approved GPU experiment |
| Root LICENSE | Missing; licensing decision requires owner approval |

Keep `PROVISIONING_ENABLED=false`, `PUBLIC_BETA_ENABLED=false`, `STRIPE_ENABLED=false` and the private real-experiment gate disabled in the rehearsal. The $10 budget is not assumed to be enforced by RunPod. Backend validation does not authorize a pod. The final approval package must identify exact compute/storage/tax costs, independent verified termination, test commands, stop thresholds and cleanup before any paid creation.
