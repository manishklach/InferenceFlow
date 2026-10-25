# Resumed real-GPU preparation — 2026-10-25

**No GPU has been created. Live termination authority remains unverified.**
This report updates the [previous readiness review](../2026-10-24/prearmed-gpu-readiness.md).

## Completed CPU staging preparation

The previous local Docker stack and temporary tunnel shut down under their
supervisor as intended. The existing isolated PostgreSQL data was preserved.
API and scheduler were restarted on the existing local Docker host with:

- Genuine staging authentication and `EXECUTION_MODE=vllm`.
- Qwen/Qwen3-4B and tokenizer revision
  `1cfa9a7208912126459214e8b04321603b3df60c`.
- A cached CPU tokenizer, verified offline with thinking disabled. No model
  weights were loaded and no inference was executed on the CPU.
- Context 10,240 and four-slot worker/control-plane caps; fixed baseline policy
  initially, adaptive expansion and estimator calibration disabled.
- Public beta, automatic provisioning and Stripe disabled; no provider key on
  the control plane and a fresh expendable worker bootstrap credential.

The operator approved the exact replacement Auth0 callback for the new temporary
HTTPS tunnel. It was saved in the existing staging application without wildcards
or additional applications. Real OIDC login and an authenticated wallet read
succeeded again; the existing operator wallet remained unfunded and unchanged.
Private hostnames, keys, account metadata and screenshots remain under ignored
runtime storage.

**15 operational checks passed:** HTTPS health/readiness, real execution mode,
disabled development login, rejected anonymous wallet/models/metrics access,
rejected forged session, authenticated operator metrics, disabled paid/beta
switches, absent provider key, exact OIDC redirect with PKCE/state/nonce,
offline pinned tokenizer and zero wallet reconciliation drift.

A separate synthetic tenant was prepared with **1 USD-equivalent of test
credits** through the existing development-only CLI in a one-off process against
this isolated staging database. The running API stayed in staging mode. This is
synthetic opening credit, not a Stripe payment, customer revenue or RunPod credit.
No existing customer wallet or billing implementation was changed. Its API key
is restricted to private local storage, not chat, Git or workflow inputs.
Five additional authenticated checks verified credit balance, pinned model and
tokenizer identity, real execution mode, context limit and test-only rates.
Reconciliation still returned zero drift.

All 1,000 prepared synthetic prompts were tokenized using that CPU image:
237–863 input tokens, at most 1,119 input plus reserved output tokens. These are
tokenization measurements, **not GPU throughput or memory-fit measurements**.
No inference jobs were submitted and no GPU worker is attached.

The CPU supervisor now allows a four-hour preparation window and stops on
component failure. Its current expiry is **03:58 PDT on 2026-10-25**. This extends
only unpaid local CPU availability; the GPU watchdog's earlier 110-minute cleanup
threshold and the user's 120-minute maximum remain unchanged. The tunnel still
depends on this machine staying powered and connected. Refresh lifetime and
login if the preparation window expires before the experiment.

Worker credentials currently expire after one hour and have no automatic renewal.
Restart/re-register the worker between arms before expiry, or keep the first
measured execution phase below 45 minutes and stop if more time is needed. Do
not claim seamless two-hour worker authentication. Record restart/idle costs
and all unfinished requests in the eventual report.

## Provider evidence and remaining gate

The complete RunPod pod inventory is empty. The signed-in console still reports
**$10.00 credit**. Fresh POD catalog reads with one GPU and host CUDA >=12.8 show:

| Candidate | Tier | GPU compute USD/hour | Stock |
|---|---|---:|---|
| RTX 4090 24 GB | Community | 0.34 | NONE |
| L4 24 GB | Secure | 0.59 | LOW |
| L40S 48 GB | Secure | 1.09 | HIGH aggregate |

L4's returned available DCs include US-MO-2 and US-GA-2. Catalog capacity is not
a reservation or proof that a machine meets the inference payload's RAM/CPU
filters. The undeployed L4 console hardware draft shows 80 GB ephemeral disk at
$0.011/hour plus GPU $0.59/hour, with a rounded total $0.60/hour. CPU/RAM allocation
varies with live stock. This remains a quote display, not a provisioned pod or
an accepted final all-in machine price. Recheck any applicable fees and actual
resource allocation before approval execution.

The fresh [GitHub read-only cleanup preflight](https://github.com/manishklach/InferenceFlow/actions/runs/40171169446)
passed after operator environment review. The last main CI run also
[passed](https://github.com/manishklach/InferenceFlow/actions/runs/40130480327).
Application source remains unchanged; the previous full suite result was
162 passed, one real-GPU test skipped. No fresh full-suite claim is made here.

**A successful GET does not prove DELETE authority.** No existing pod is available
for a live termination check. Under the original requirement to establish that
authority before any GPU creation, provisioning must remain blocked.

A possible next step is a separately approved **teardown-only validation pod**:
one Secure L4, pinned existing vLLM image, 80 GB ephemeral disk, no mounts or
public ports, no application/provider/database credentials and no inference.
Its entrypoint would sleep while the already-running independent watchdog binds
its exact name/ownership marker/creation time. Cancellation requests immediate
cleanup; fresh provider reads must confirm disappearance. Local proposal files
are inert and retain false approval/cost-confirmation fields.

Target termination within five minutes would cost approximately $0.05 using the
displayed $0.601/hour components, including startup/pull time. If that attempt
fails, the existing 110-minute guard provides a later retry path, not a hard
provider spending cap; a two-hour estimate is approximately $1.202 before any
unverified fees. Both validation and inference would count toward the same $10
total. Runner/provider outages or insufficient permission may defeat cleanup;
an operator must retain direct console access for fallback.

This would be an explicit exception to the original ordering rule, and would
require separate approval of the exact machine quote, budget and teardown-only
scope before creation. It does **not** authorize the subsequent inference pod.
If the original rule is retained, remain NO-GO rather than manufacture DELETE
proof. No billable resource or watchdog run has been started.
