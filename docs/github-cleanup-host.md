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

## Remaining provisioning blockers

This workflow is a credential preflight, **not a running watchdog**. The existing
`scripts/experiment_guard.py` requires an approved exact pod ID/name receipt,
actual provider creation time and confirmed all-in hourly cost. It targets only
that identity, requests DELETE, then requires a fresh GET returning 404. Its
contract tests are simulations, not evidence of real DELETE authorization.

Before any billable creation, finish and verify a pre-armed independent
controller that binds the separately approved pod identity, survives local
machine failure, and confirms termination within the experiment limit. Verify
actual provider termination authority without treating a successful GET, a
read/write label or a nonexistent-ID 404 as a live DELETE test. If that cannot
be established without a paid test, obtain separate explicit authorization or
remain NO-GO. GitHub queueing, outages and cancellation must be considered;
Actions alone is not a provider-enforced spending cap.

Recheck balance, live capacity, all GPU/disk/ancillary charges, pinned model
fit and real worker staging connectivity. Keep the $10 ceiling, earlier stop
threshold and 120-minute maximum. Nothing in this change modifies wallets,
billing, automated provisioning, public beta or Stripe live payments.
