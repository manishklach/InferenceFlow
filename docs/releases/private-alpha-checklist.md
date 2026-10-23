# Future private alpha release checklist

Not a release announcement. No public beta or production-readiness claim.

- [ ] Private staging HTTPS origin and managed OIDC verified from outside local machine; Sites remains showcase only.
- [ ] Independent session/HMAC/encryption/metrics/bootstrap credentials provisioned/rotated, DB least privilege and restore drill validated.
- [ ] Default PROVISIONING_ENABLED,STRIPE_ENABLED,PUBLIC_BETA_ENABLED remainfalse; reviewed private experiment gate explicitly scoped and audited.
- [ ] Exact GPU placement and complete quote, license/rates, model/container/hash provenance reviewed; expense and cleanup explicitly approved.
- [ ] Independent exact-pod guard authenticated and recovery drill demonstrated, manual termination backup available; no guarantee of provider cap.
- [ ] Real10-request pipeline with verified model and usage, followed by100-request matched arms; sustained1000 only within remaining time/budget.
- [ ] Actual concurrency/engine sequences/KV/GPU samples and timing evidence retained; no mock-to-real relabeling.
- [ ] Controlled interruption after inference/before finalize shows recovery, stale fencing, one usage/capture and zero drift; reconcile every terminal reservation.
- [ ] Full cost coverage/invoice and equal-workload hosted comparison; performance/price claims independently reviewed.
- [ ] Paid capacity fully deleted and read-back confirmed; evidence backed up, credentials revoked; no retained storage surprise.
- [ ] Callback egress/TLS, production key rotation, PostgreSQL recovery, rate limits and dependency/image security reviewed; no open public vLLM endpoint.
- [ ] CI, review and merge completed; website fix publication separately approved, metadata/index policy and audience verified after deploy.
- [ ] Operator runbooks, incident ownership, support policy and actual admission limits reviewed before admitting private-alpha users.

Vast.ai/Lambda activation and automated capacity require separate credentialed read/lifecycle validation and spending authorization. Current tests and mocks do not satisfy those gates.
