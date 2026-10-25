# Temporary GitHub-hosted staging proposal

Requested October 25, 2026. This is one bounded integration-test session, not permanent API hosting. The owner subsequently approved the protected `staging-experiment` environment and Auth0 client-secret destination. Main-only restrictions and owner review were verified; that one secret is stored encrypted. No RunPod key or previous database was transferred. The manual [no-GPU rehearsal workflow](../../.github/workflows/staging-rehearsal.yml) implements mock hosting only; real GPU execution and private evidence export remain gated. A dispatched/approved workflow is not proof that HTTPS/OIDC or mock execution passed.

## Architecture and cost

One standard `ubuntu-24.04` runner in the public InferenceFlow repository runs isolated PostgreSQL, API and scheduler Compose services, an outbound Cloudflare temporary HTTPS tunnel, the tracked supervisor and synthetic test driver. Build from an approved immutable main commit; no pull-request or scheduled trigger receives secrets. The Sites website stays separate. A different runner in the existing `gpu-experiment` environment runs independent GPU cleanup.

GitHub lists standard hosted-runner compute as free for public repositories: [billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners). Proposed control-plane compute cost is **$0**, conditional on keeping the repository public and using a standard runner. Larger runners and artifact/cache storage have separate billing rules. Do not enable paid storage, select a larger runner or assume artifact uploads are free. No permanent VM, domain, or network volume is proposed.

Limit staging service lifetime to 120 minutes plus a short job-finalization window. Limit the proposed GPU load session to 90 minutes from creation to leave export/cleanup headroom. Neither runner is guaranteed available. This is an experiment host, not high availability or a GitHub-enforced GPU spending cap.

## Exact credential destination requiring approval

Create a separate protected GitHub environment **`staging-experiment`** in **`manishklach/InferenceFlow`**, main-only and requiring owner deployment review. Before storing anything, verify those protections by readback. Do not reuse or weaken `gpu-experiment`.

After explicit approval, store only the existing staging Auth0 client secret as encrypted environment secret **`AUTH0_STAGING_CLIENT_SECRET`**. This permits the reviewed staging job to perform the existing OIDC code exchange; it grants no Auth0 management access. The issuer and client ID are non-secret environment variables. Generate fresh database, encryption, session, metrics and worker-bootstrap credentials inside the runner. Do not transfer the previous database, wallet balances, API keys or full private environment bundle.

The RunPod cleanup key remains exclusively in `gpu-experiment`; staging receives no RunPod API key. Pricing's read-only key stays separate. Mask generated secrets, use operator-only temporary files, never put secrets in shell arguments, and never print Compose-expanded configuration. PostgreSQL has no public port. Only the authenticated control API uses the HTTPS tunnel; vLLM stays private on the separately approved GPU Pod. Public beta, live Stripe and automatic provisioning stay disabled. Pin the Actions and tunnel binary/image before implementation is activated.

## Implementation and rehearsal gates

1. Implement the manual hosting workflow and isolated Compose configuration; keep it inert until environment protection and credential-destination approval exist.
2. Launch a **no-GPU** rehearsal. A new temporary tunnel requires a separately approved **exact callback URL** for the existing Auth0 application. No wildcard or unknown future callback is authorized by this proposal.
3. Verify owner OIDC login, rejected anonymous access, PostgreSQL/API/scheduler readiness, rejected invalid worker authentication, and a mock outbound worker round-trip. Inject transient/exhausted Docker status errors; verify retained private diagnostics and bounded shutdown. Clearly label mock results.
4. Verify private evidence export independently of the desktop **before renting**. Public Actions logs/artifacts are not an acceptable destination for raw prompts, database dumps, credentials or private provider logs. Select an owner-approved private encrypted export destination or demonstrate secure owner retrieval. If export cannot be demonstrated, stop. The runner database is ephemeral.
5. Present fresh GPU+storage pricing, console balance, remaining original $10 budget, Pod configuration and exact independent cleanup plan for separate approval. Require an owner-approved watchdog with a fresh armed heartbeat before Pod creation. The old completed watchdog is not armed protection.
6. Create a fresh synthetic tenant/test-credit balance using the existing accounting implementation; do not change customer rates or wallet logic. Enable the reviewed real experiment gate only after the approved worker and live canary pass. Run the [matched comparisons and 500-request plan](third-gpu-experiment.md).

## Shutdown

Stop new submissions on staging/tunnel/database failure; invoke independent exact-Pod cleanup and verify fresh provider GET 404 plus no persistent billable storage. Export and reconcile surviving results; if evidence is incomplete, say so rather than asserting zero drift. On normal completion, export evidence, terminate/verify the GPU, stop the tunnel and exact Compose project, remove only the isolated disposable test volume, then let GitHub destroy the runner. Test normal, failure and cancellation finalizers before use. Provider/GitHub-wide outages remain risks; separate runners are not separate providers.

## Decision

Recommended only for a bounded repository integration experiment. A stable paid host/domain may be preferable later, but no such purchase is proposed here. Next approval is the named GitHub environment and Auth0 secret destination. Implementation rehearsal, exact callback approval, private export validation, and fresh GPU approval still follow; none are claimed complete by this document.
