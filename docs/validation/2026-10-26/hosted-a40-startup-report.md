# Hosted A40 attempt: stopped before inference

October 26, 2026. **No performance or savings result was produced. The provider-readback fix passed CI; any new rental still requires fresh readiness checks and approval.**

The owner approved exactly one A40 48 GB, Secure Cloud CA-MTL-1, at $0.59/hour GPU plus displayed $0.011/hour temporary 80 GB disk. The conservative guard was $0.61/hour with a $1 allocation inside the original $10 budget. No replacement was created.

## Evidence and cleanup

- CPU host [40380907617](https://github.com/manishklach/InferenceFlow/actions/runs/40380907617) passed real-mode API, authentication, pinned-tokenizer and no-worker admission checks before creation.
- Independent watchdog [40382693589](https://github.com/manishklach/InferenceFlow/actions/runs/40382693589) authenticated and armed at 19:01:04 UTC, with a 19:46:03 UTC cutoff, then bound to the exact pod at 19:05:00 UTC.
- Pod `7xqndpqyhzruoy` was created at **19:04:54.875 UTC**. Readback confirmed one A40, CA-MTL-1, pinned vLLM digest, 80 GB temporary disk, empty ports/mounts and disabled global networking. Provider logs showed image download/extraction.
- The hosted driver stopped at approximately 19:05:20 UTC, before worker readiness or workload admission. The operator issued DELETE after observing the host failure; it returned 204 and a subsequent authenticated GET returned 404. The watchdog independently confirmed absence at **19:06:02 UTC** and finished successfully. This is absence confirmation, not proof that its new control-completion deletion path initiated teardown.
- Network-volume inventory was empty. No persistent storage was requested. The rented-lifetime upper bound from creation to independent absence confirmation was approximately **68 seconds**, about **$0.012 at the guard rate**. This is an estimate, not the posted bill. The billing query initially returned no records; that does not establish free usage.
- The owner-encrypted final database artifact was downloaded and decrypted locally. It contains **zero jobs, zero job requests and zero usage records**. The isolated wallet has its initial synthetic funding entry; no inference capture was generated.

## Root cause and fix

The REST v2 read returns `globalNetworking: {"enabled": false}`. The hosted verifier tested the truthiness of the entire object, so it rejected correctly disabled networking as an unauthorized resource shape. Its synthetic contract fixture had used the create-request boolean shape instead of the live read shape. Reproducing the condition against the retained readback confirms this rejection before `session.json` was written.

The fix accepts an explicit boolean false or an object with `enabled` exactly false, and rejects enabled, missing and malformed values. A regression test covers the actual provider readback and rejects ambiguous values. Another fix retains pre-session driver/error diagnostics inside the existing owner-encrypted final export; previously those files sat outside the exported experiment directory. Connection credentials remain excluded.

Nine focused unittest checks passed locally, including both regressions; lint and application type checks passed. Local pytest could not initialize its automatic PostgreSQL fixture because the configured local test database was unavailable. GitHub's PostgreSQL-backed [CI run 40384144967](https://github.com/manishklach/InferenceFlow/actions/runs/40384144967) subsequently passed **241 tests, one GPU skipped, 31 scheduler-v2 regressions**, lint, type checks, deterministic simulation and the dashboard production build. The separate pull-request CI also passed.

## Next gate

Verify CI, exercise the real response fixture without renting, then prepare a fresh bounded CPU session and independent watchdog. Any further pod needs a fresh unchanged quote, readiness checks and explicit one-pod approval. Do not reuse this consumed rental approval. Sequential/concurrent/adaptive comparisons, interruption, batching, utilization, deadline attainment and economic advantage remain unmeasured for this attempt. Public beta, live Stripe and automatic provisioning remain disabled.
