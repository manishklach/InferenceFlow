# Recovery fixes after the first L4 experiment

The [first real inference attempt](real-inference-report.md) passed baseline 10/100 execution and accounting, then stopped after a transient control-plane 502 killed the worker. This follow-up fixes the observed paths without renting another GPU or changing the customer billing implementation. **Local regression validation is not a successful real-GPU recovery experiment.**

## Changes

The worker now retries temporary transport failures, HTTP 429 and HTTP 5xx during registration, polling, heartbeat and finalization. Each operation has a 120-second total recovery budget, request timeouts bounded by the remaining budget, and exponential waits capped at 15 seconds. Cancellation remains immediate. Other HTTP errors fail immediately; only finalization treats existing 404/409 fences as terminal. Exhausted recovery or a fatal execution-task error stops the worker rather than silently discarding the failure.

Retries preserve the credential, request body and lease epoch. A temporary outage does not re-register an active worker or change its generation. A lost finalization response retries the same completion; the server may answer 409 after the first transaction already committed. Existing server generation/epoch fencing, unique usage/capture records and wallet transactions remain authoritative. An outage longer than a lease may cause physical execution to repeat after requeue, but stale results cannot revive the lease or create a second charge. This change does not promise recovery from every outage.

Registration can retry before accepting work; it does not use re-enrollment to bypass a 401/403. Authentication expiry/revocation remains fatal. Ordinary authenticated heartbeats extend the existing worker expiry on the server. The independent provider watchdog remains necessary: a stopped worker process is not a terminated paid pod, and container restart behavior does not enforce a spending limit.

The generated bootstrap handles an existing Git origin, resets the known application checkout to its pinned source and reapplies the reviewed, hashed overlays. Model cache and evidence are outside that checkout and are retained. This fixes `remote origin already exists` on a retained container disk. The inert proposed payload was regenerated; its credentials remain placeholders and its old hardware selection is **not a current availability quote or an approval to rent**.

The launcher keeps the vLLM engine key in its environment rather than its printed CLI arguments. This uses vLLM 0.8.5's environment authentication support, which was exercised by the first actual GPU payload. Public inbound ports remain closed.

Telemetry still writes raw Prometheus and NVIDIA records to private ephemeral disk. Provider stdout now receives a compact, versioned sample containing selected engine counters, running/waiting sequences, KV-cache usage and bounded NVIDIA data. This avoids the long raw histogram messages that fragmented at 16 KiB. Malformed metrics and oversized hardware samples are explicitly marked unknown, not converted to zero. This reduces log loss risk; it does **not** provide durable external storage or prove provider logs will retain every sample. The next run must verify coverage before interpreting full-lifetime utilization.

## Regression evidence

- Deterministic worker test injects separate poll, heartbeat and finalize 502s, verifies the worker stays alive, one registration and one engine execution occur, and the same completion is retried.
- Transport-loss/503 tests preserve authentication, payload and epoch; 400/401/403 and non-finalization 404/409 do not retry. Recovery deadline, cancellation and stale-finalization fences are checked.
- A real FastAPI/PostgreSQL test commits a completion, simulates losing the response and retries through the worker helper. The retry receives the existing 409 fence. Exactly one usage record and one capture remain, worker generation is unchanged, reservation is released and reconciliation has zero drift.
- A Linux Bash test executes the actual generated checkout commands twice against an offline Git repository, including a modified tracked overlay and an existing origin.
- Compact telemetry tests use a raw payload over 100 KiB, preserve engine/hardware measurements below 8 KiB, and verify malformed/oversized samples stay unknown.

All checks use local synthetic tenants, mocked engine/control-plane failures and an isolated test database. No RunPod mutation or live payment is involved. The live-GPU pytest remains gated and skipped. Full test counts and CI links are recorded in the associated pull request; the historical real GPU evidence is unchanged.

## Next manually approved run

Keep public beta, Stripe live payments, optional provider execution and automatic provisioning disabled. Refresh the remaining RunPod credit, GPU availability, all-in quote, source hashes and the staging HTTPS/OIDC endpoint. Arm a fresh independently authenticated teardown job and verify its heartbeat before creating one separately approved resource.

Start with 10 baseline requests, confirm usage/reconciliation and compact telemetry coverage, then 100 baseline. Change scheduling policy only while the queue is idle, observe the worker reconnect after any brief API restart and confirm a new authenticated heartbeat before admitting the adaptive workload. Repeat the same 100 requests for adaptive/sequential comparisons. Run a separately scoped interruption/recovery case and check its ledger. Attempt 1,000 only after those pass and the remaining budget/time allows it. Stop on critical errors; terminate the pod and verify 404 plus empty storage inventories. Report all incomplete/failed requests in the completion denominator.

**Current decision remains NO-GO for public launch or savings claims.** A fresh real GPU test is still needed to validate these local fixes, larger-load completion, fault recovery and economic advantage. This document does not authorize that spend.
