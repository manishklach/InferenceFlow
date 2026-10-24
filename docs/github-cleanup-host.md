# Independent GitHub cleanup host

The operator approved GitHub Actions as the independent cleanup host and the
`gpu-experiment` environment as the encrypted cleanup-secret destination on
2026-10-24. This approval does **not** authorize GPU creation.

## Protection and secret entry

The environment permits deployments from `main` only and requires owner review.
Self-review is allowed so the single repository owner can approve manual jobs.
GitHub administrators can bypass environment protection; this is not an
immutable policy boundary. Review the checked-out commit before approving.

Enter a dedicated RunPod key directly into GitHub's environment secret named
`RUNPOD_CLEANUP_API_KEY`. Never paste it into chat, a workflow input, an issue,
a command argument or a tracked file. From your own authenticated terminal,
the following command prompts for the secret value:

```powershell
gh secret set RUNPOD_CLEANUP_API_KEY --repo manishklach/InferenceFlow --env gpu-experiment
```

Alternatively use repository Settings → Environments → gpu-experiment → Add
environment secret. Use the narrowest provider permissions that support pod
read and termination; a broad read/write account key carries broader authority.
Revoke the experiment key when it is no longer needed.

## Read-only preflight

After saving the secret, manually run **GPU cleanup read-only preflight** on
`main`, then approve its environment review. It makes only an authenticated
`GET /pods?limit=1`, hides inventory details and fails on authentication,
provider or schema errors. It never creates, stops or deletes anything.

```powershell
gh workflow run gpu-cleanup-preflight.yml --repo manishklach/InferenceFlow --ref main
```

Success proves the independent GitHub runner can read inventory with the
protected secret. It explicitly reports DELETE permission unverified and
watchdog unarmed. Standard GitHub-hosted runners for public repositories are
free; no larger runners, paid add-ons or artifact storage are configured.
See [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

## Pre-armed controller (prepared, not dispatched)

`gpu-experiment-watchdog.yml` is manual-only, `main`-only and uses the same
owner-reviewed environment. It contains no creation calls. Do not approve a
watchdog job until its exact cleanup plan and prospective experiment are
reviewed. GPU creation still requires separate explicit approval.

Generate a fresh 128-bit `experiment_id` locally with
`python -c "import secrets; print(secrets.token_hex(16))"`. This ownership marker
is not a credential. The exact pod name must be
`inferenceflow-experiment-<experiment_id>`, and the prospective pod environment
must contain `IF_OWNER=inferenceflow` and `IF_EXPERIMENT_ID=<experiment_id>`.
Never reuse a marker or name. The workflow input is JSON with exactly:

```json
{
  "pod_name": "inferenceflow-experiment-REPLACE_WITH_FRESH_32_HEX",
  "experiment_id": "REPLACE_WITH_FRESH_32_HEX",
  "all_in_hourly_usd": "REPLACE_WITH_CONFIRMED_QUOTE",
  "fixed_cost_usd": "REPLACE_WITH_CONFIRMED_FIXED_CHARGES",
  "budget_usd": "10",
  "cleanup_approved": false,
  "all_in_cost_confirmed": false
}
```

This example intentionally fails validation. No credentials belong in workflow
inputs. Confirm compute, ephemeral disk, billing increments, taxes and all other
charges before setting approval fields true. Two hours plus fixed charges must
remain below 70% of budget. No persistent, network or global volume is allowed
in the experiment configuration; this controller does not delete volumes.

After separate experiment approval, dispatch the reviewed plan on `main` and
approve its environment gate. **Wait for the live `armed:true` log before any
create**, ensure the job is still running and create within its 10-minute
window. A queued or approval-waiting job is not armed. There is no automatic
provisioner and no release signal that creates a pod. If the window expires,
do not create; prepare a new marker and reviewed run. Never queue competing
watchdogs: concurrency deliberately does not cancel an existing guard.

The controller rejects a preexisting exact name, pages inventory completely,
rejects ambiguity and binds only a matching name/marker/owner whose provider
creation timestamp falls within the arming window. It saves the exact ID and
creation time on runner-local ephemeral disk. Fresh reads recheck identity
before deletion. It logs heartbeat/cost state without inventory or secrets.
An observed provider hourly cost above the approved ceiling, or an invalid
cost field, also requests immediate cleanup of the verified identity.

Budget estimates include supplied fixed costs and round compute/disk elapsed
time up to whole hours. It starts DELETE at 110 minutes from arming (earlier
than 120 minutes from pod creation), or the earlier 70% admission-stop threshold.
There is no remote pause endpoint: it terminates rather than claiming that a
log flag pauses admissions. DELETE must be followed by a fresh GET returning
404. Transient errors retry every 10 seconds, with monitoring bounded at 119
minutes. SIGTERM/SIGINT request immediate cleanup. An `always()` final step
rechecks identity and attempts cleanup after success/failure/cancellation.

Runner loss, forced cancellation, GitHub/provider outage or revoked credentials
can defeat these best-effort attempts. An `always()` step is not guaranteed to
run after runner destruction. A live armed log proves controller activity,
**not DELETE permission or a provider hard budget**. Keep an operator with
independent console access available; do not start an unattended experiment.

## Remaining provisioning blockers

Validation on 2026-10-24: full local PostgreSQL suite **162 passed, 1 real-GPU
test skipped**; Ruff, mypy (34 source files), manual-only workflow structure
and a scan of publishable files against local secrets passed. Nine new
deterministic preflight cases cover read-only behavior, authentication/provider
failures and malformed inventory; 25 additional controller cases exercise identity,
pagination, deadlines, cancellation, failures and verified deletion. Live authentication
completed successfully in [the independent read-only run](https://github.com/manishklach/InferenceFlow/actions/runs/40128846861).

This workflow is a credential preflight, **not a running watchdog**. The existing
`scripts/experiment_guard.py` requires an approved exact pod ID/name receipt,
actual provider creation time and confirmed all-in hourly cost. It targets only
that identity, requests DELETE, then requires a fresh GET returning 404. Its
contract tests are simulations, not evidence of real DELETE authorization.

Before any billable creation, review and arm the prepared independent
controller, verify it is active outside the local machine, and establish its
actual termination authority. Verify
actual provider termination authority without treating a successful GET, a
read/write label or a nonexistent-ID 404 as a live DELETE test. If that cannot
be established without a paid test, obtain separate explicit authorization or
remain NO-GO. GitHub queueing, outages and cancellation must be considered;
Actions alone is not a provider-enforced spending cap.

Recheck balance, live capacity, all GPU/disk/ancillary charges, pinned model
fit and real worker staging connectivity. Keep the $10 ceiling, earlier stop
threshold and 120-minute maximum. Nothing in this change modifies wallets,
billing, automated provisioning, public beta or Stripe live payments.
