# Private real-mode CPU control host

The [hosted mock pipeline and export](../validation/2026-10-25/hosted-mock-export.json) passed. This separate workflow removes the remaining mock-only hosting restriction. It **does not provision a GPU, perform inference, or contact RunPod**. It has no provider credential. A running control plane is not a ready GPU worker.

`real-control-host.yml` is manually dispatched from `main` and requires owner review in `staging-experiment`. It uses the already-approved Auth0 secret, owner public encryption key, standard public-repository Ubuntu runner and pinned verified Cloudflare binary. It builds the CPU API image, downloads only the exact Qwen3-4B tokenizer revision, and verifies its chat template. It does not download model weights or use a GPU.

The API and scheduler start in vLLM mode with reviewed private experiment admission enabled. Public beta, Stripe and provisioning are disabled. Baseline starts with scheduler-v2/adaptive flags false, max in-flight four and estimator uncalibrated. No mock worker starts. The API's existing live-worker readiness challenge must still pass after a separately approved real worker connects; a healthy CPU `/readyz` response alone does not satisfy GPU admission.

The host seeds a **new disposable synthetic tenant** with ten dollars of test credits using existing accounting functions. This does not fund RunPod, create payment revenue, change the owner's previous zero wallet or change billing rates. The one-use seed refuses an existing experiment identity and cannot run with public beta, provider credentials or auto-provisioning enabled.

The approved encrypted connection artifact contains exactly the HTTPS origin, worker bootstrap, tenant API key and metrics token. Download and decrypt it privately; supply only origin/bootstrap to the approved worker. The operator retains metrics/tenant keys. No Auth0, database, application encryption or provider key is in the handoff. Ciphertext is retained one day on GitHub and may be publicly retrievable; the private RSA key stays local.

The child host is bounded to **150 minutes from script startup**, including image/tokenizer setup. The workflow has a 160-minute ceiling. This non-GPU window leaves export/cleanup headroom; it does not increase the maximum approved paid experiment duration. Do not create a Pod unless the independent watchdog's full lifetime fits inside the remaining CPU-host window and the 90-minute target leaves reserve. Recreate hosting rather than start a GPU late in an expiring session.

On deadline, operator cancellation or service failure, the host attempts to seal the isolated PostgreSQL dump before removing its disposable volume. The workflow uploads only the exact encrypted final evidence file and runs exact-project cleanup on every outcome. Missing export, provider outage or runner loss remains a failure: never assert billing reconciliation from unavailable evidence. Retrieve periodic operator-side job/result/audit records during the experiment too. This workflow is temporary experiment hosting, not a durable database service or high availability.

## Before GPU approval

1. CI must pass and the protected host job must be owner-approved. Verify its readiness marker, decrypt the handoff, test HTTPS/anonymous rejection and inspect actual mode/policy through authenticated operator endpoints.
2. Obtain approval for the new exact Auth0 callback and confirm login. Prior mock-session callbacks do not authorize a different origin.
3. Refresh RunPod GPU stock, actual all-in disk/GPU price, console balance and cumulative experiment budget. Keep the pinned vLLM image/model settings and no public Pod ports/persistent volume.
4. Present those concrete facts with the exact one-Pod cleanup plan for **separate billable creation approval**. Independently arm the protected cleanup workflow and verify its heartbeat before any create.
5. After approved creation, validate the real engine identity and live canary, then execute the ten-request smoke, reversed-order 100-request comparisons and gated 500-request interruption plan. Stop/terminate on critical failures, missing evidence or reserve exhaustion.

Host approval or an encrypted credential handoff is never GPU rental approval.
