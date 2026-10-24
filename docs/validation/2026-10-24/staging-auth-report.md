# October 24 staging authentication validation

**OIDC login passed on an isolated, temporary staging control plane. Paid GPU provisioning remains NO-GO.** This phase ran mock inference mode and did not create paid infrastructure, provision a GPU, alter customer billing algorithms or enable public beta.

## Verified

- The operator created an Auth0 development tenant and explicitly approved a separate Regular Web Application and its single exact HTTPS callback. No wildcard callback or management API grant was configured. Only free-plan-compatible features were used.
- Discovery verified the actual issuer, authorization-code flow, S256 PKCE, RS256 support and published RSA signing keys. The application settings confirmed RS256 and OIDC conformity.
- A deployed Post Login Action restricts only this staging application to the verified operator account. Four local policy cases covered allowed owner, unverified owner, another account and an unrelated client. The unrelated client is unaffected. The Action was bound to the live login flow.
- A separate Docker API, scheduler and PostgreSQL database passed the existing `ENVIRONMENT=staging` runtime validation with actual OIDC configuration and fresh signing, HMAC, encryption, metrics and bootstrap secrets. `EXECUTION_MODE=mock`; provisioning, public beta, Stripe and the reviewed real-experiment gate stayed disabled. This is not the development rehearsal gateway.
- Twelve HTTPS checks passed: health, mock readiness, staging auth configuration, denied development login, denied anonymous wallet/session, protected metrics, denied invalid worker bootstrap, correct OIDC redirect, code/PKCE/state/nonce, secure HttpOnly flow cookie and rejected invalid callback.
- The operator completed a real browser login. The authenticated browser could read the protected wallet endpoint; a separate unauthenticated client and a forged session cookie were rejected. This exercises the existing authorization-code exchange, issuer/audience/signature validation and application session, rather than a fabricated local identity.
- The new database contained exactly one OIDC-created tenant, membership and wallet, with no ledger credits or charges. The existing reconciliation command returned zero drift. No existing wallet was migrated or modified.

## Operational limits

The temporary Cloudflare tunnel depends on the local PC remaining awake and connected; its hostname changes on restart. The local supervisor stops this exact Compose project and tunnel after 120 minutes. It is not independent GPU teardown protection, a provider spending cap or a production availability guarantee. A recreated API triggered the supervisor's fail-closed stop as expected; subsequent validation used a fresh supervised run. A preparation-only validator error showed part of an unused generated encryption key, which was replaced before any tenant or job existed; no Auth0 client secret was printed or committed.

All account metadata, client credentials, runtime configuration, signing material, logs, temporary URLs, callback approval evidence and screenshots remain in ignored private runtime files. No private credential or identifying operator allowlist is included in this report. The earlier backend regression evidence remains **128 passed / 1 real-GPU test skipped**, with 14 HTTPS mock pipeline checks; this authentication phase is additional operational evidence, not another GPU benchmark.

## Remaining before a paid experiment

1. Establish and verify a cleanup host independent of this PC and GPU. Confirm the dedicated credential's termination authority and arm exact-pod identity/budget/deadline enforcement. Report simulated DELETE tests and actual provider permission evidence separately; authenticated GET alone is insufficient.
2. Validate the reviewed real-mode configuration and pinned CPU tokenizer, then refresh GPU availability, exact compute/storage/ancillary costs and balance. Actual VRAM fit still needs an approved GPU canary.
3. Present the final $10 maximum experiment approval package, including an earlier stop threshold, independent cleanup verification, sequential 10/100/up-to-1,000 request commands and all remaining risks. Obtain explicit approval before any billable creation.

No real GPU batching, throughput, 60-minute attainment or economic advantage is established by this login test. Root repository licensing remains an owner decision; no LICENSE was added.
