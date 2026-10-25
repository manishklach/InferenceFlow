# Real experiment connection handoff — approval boundary

The [hosted mock/export verification](../validation/2026-10-25/hosted-mock-export.json) passed on run 40228875061: ten successes, ten usage records, ten unique capture sources, no ledger errors, zero reserved balance afterward. The downloaded 48,305-byte encrypted artifact decrypted successfully to the exact three allowed files, including the matching job and ledger in the SQL dump. A database restore has not been tested. The rehearsal completed teardown; its temporary endpoint is no longer the live real experiment backend.

The next real-mode host needs a minimal connection handoff so the operator can connect one separately approved GPU and drive the existing experiment tools. This is a different payload from the already-approved mock evidence export and therefore needs explicit approval before transmission.

Proposed destination: one-day GitHub Actions artifact **`sealed-experiment-connection-RUN-ATTEMPT`** in **`manishklach/InferenceFlow`**, encrypted with the same owner RSA public key and authenticated AES-GCM envelope as the verified rehearsal. Treat its ciphertext as publicly downloadable. The private decryption key remains local under the verified operator/SYSTEM ACL; it is not sent to GitHub or RunPod.

The encrypted plaintext contains exactly:

- `CONTROL_PLANE_URL`: the temporary HTTPS API origin.
- `WORKER_BOOTSTRAP_TOKEN`: fresh, experiment-only authority for an outbound worker to register.
- `METRICS_TOKEN`: fresh operator telemetry/readiness authority for this isolated experiment.
- `INFERENCEFLOW_API_KEY`: a fresh API key for this disposable synthetic tenant only.

The serializer is `scripts.experiment_connection`, whose allowed fields and URL/credential checks are tested. **Exclude** the Auth0 client secret, database URL/password, session/hash/encryption keys, provider credentials, cleanup key and any customer key. The operator decrypts the handoff locally, keeps metrics/tenant keys on the operator side, and supplies only the HTTPS origin and bootstrap token to the one approved RunPod worker. The worker never receives the control-plane database or RunPod management key.

Approval permits only this encrypted credential handoff for the temporary private experiment. It does not approve a GPU rental, a public plaintext upload, a customer rollout or a new Auth0 callback. The real-mode hosting workflow, live worker challenge, fresh all-in GPU/storage quote, balance and independent watchdog must still be verified before separately requesting Pod approval. No connection artifact or billable Pod has been created by this document.
