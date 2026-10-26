# Trusted hosted experiment controls

These are operator experiment utilities, not a product API. No additional HTTP admin route, RunPod key, database credential transport or repository permission is introduced. Existing main-branch repository writers can already change the control-host workflow; the mailbox explicitly trusts that same boundary. Review this code before starting a new protected staging job.

The running real host polls the fixed public file `docs/experiments/host-command.json` on this repository's `main` branch. No command is shipped by default. An accepted command must name the exact GitHub run-attempt, be the next integer sequence, expire within ten minutes, and contain only `run_id`, `sequence`, `expires_at`, `policy`. Supported policies are sequential, baseline, deadline_fixed, adaptive, and read-only audit. Unknown fields cannot execute arbitrary commands. No credential or prompt belongs in this public file. GitHub/raw delivery can lag; verify completion rather than assuming a commit was delivered.

Prepare a command locally, review its four fields, then commit/push only that file to main:

```powershell
.\.venv\Scripts\python.exe -m scripts.experiment_commands --run-id RUN_ID-ATTEMPT --sequence 1 --policy sequential
git add docs/experiments/host-command.json
git commit -m "Request reviewed experiment phase"
git push origin main
```

The sequence is consumed on disk before mutation; failed or ambiguous commands cannot replay after process restart. A successful command emits `host_policy_command` with status `verified` to that run's logs. Independently read `/internal/scheduling/report` using the private metrics credential and verify the new flags. Real workload submission still requires a new worker engine-canary challenge; a heartbeat is not proof of readiness.

Before each policy transition, the host audits only its fresh synthetic tenant in a read-only PostgreSQL transaction. The policy utility checks unresolved work, stops API/scheduler admission, repeats the idle check to close a concurrent-admission race, rewrites only scheduling flags/concurrency, recreates API/scheduler, then verifies effective configuration. PostgreSQL stays running. All paid/public flags must remain false. A failed audit, busy boundary delivered through the mailbox, failed restart or configuration mismatch writes STOP and ends the supervised host. Keep the GPU watchdog independent because stopping a CPU host does not itself terminate a GPU.

Use the next sequence with `--policy audit` after each completed stage. It performs no restart. It audits cumulative accepted jobs for this experiment tenant, requiring all to succeed, unique usage/captures, matching settlement and no reconciliation drift. Reports stay private on the runner and are included in the existing owner-encrypted final evidence export. A verified audit receipt is required before more requests. Telemetry coverage remains an independent gate using the GPU collector's provider logs; the mailbox does not fabricate or replace those samples.

## No-GPU rehearsal

The `Hosted policy controls (mock only)` workflow builds the isolated Compose stack with PostgreSQL and keeps one mock worker alive across sequential → baseline → adaptive → baseline. Each stage completes ten requests and performs the existing read-only audit. It uses no Auth0/RunPod secrets, no tunnel and no GPU. The initial run [40280625273](https://github.com/manishklach/InferenceFlow/actions/runs/40280625273) passed 40/40 requests with four audits. Subsequent runs cover delivery through the mailbox dispatcher as well as service transitions. This is recovery/control evidence only, not GPU performance evidence.

Local unit commands:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_experiment_commands tests.test_experiment_policy tests.test_staging_supervisor -q
```

The full PostgreSQL suite and Compose rehearsal run on GitHub, because this workstation's Docker engine is unavailable. Before another paid run, merge only after fresh CI/rehearsal passes, start the updated protected real CPU host, verify its initial settings and exercise a no-work policy change/audit through the actual main-branch mailbox. Then revalidate worker admission rejection and prepare the separately approved GPU.
