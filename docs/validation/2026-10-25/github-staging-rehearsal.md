# GitHub-hosted staging: HTTPS and owner authentication

October 25, 2026. [Protected no-GPU rehearsal run](https://github.com/manishklach/InferenceFlow/actions/runs/40227678819), source `468acd0`. This is an independently running temporary control plane, not real GPU validation or production hosting.

The owner approved the `staging-experiment` GitHub environment and the existing staging Auth0 client-secret destination. Main-only restrictions and owner review were verified before storing that secret. No RunPod credential, previous database or wallet balance was transferred. The owner approved this run through GitHub deployment review.

The standard GitHub runner started fresh isolated PostgreSQL, API, scheduler and mock worker containers and an outbound HTTPS tunnel. Supervision tests and the pinned Cloudflare binary SHA256 check passed. The runner's readiness marker explicitly states mock mode and owner-login-unverified at startup; subsequent browser checks below establish login separately.

## Observed checks

| Check | Result |
|---|---|
| External HTTPS `/readyz` | 200, `status=ready`, `execution_mode=mock` |
| Anonymous `/v1/wallet` | 401 |
| Invalid worker registration bearer | 401 |
| Development `/auth/login` | Rejected by runner startup check |
| Exact callback replacement | Owner-approved single URL; Auth0 save-success message observed |
| Owner OIDC authorization-code login | Returned to `/healthz`, `{"status":"ok"}` using the existing SSO session |
| Authenticated `/v1/wallet` | Available/reserved/debt/total all zero, frozen false |

Temporary endpoint: `https://traveling-deborah-semester-talked.trycloudflare.com`. Exact callback: `https://traveling-deborah-semester-talked.trycloudflare.com/auth/oidc/callback`. No wildcard or additional application was authorized. Auth0 initially rejected the callback before its save completed; after the explicit save and propagation window the complete login succeeded. A rendered edited field alone was not taken as final authentication proof.

The authenticated read demonstrates an accepted staging session, not tenant-isolation coverage or a complete inference pipeline. Private screenshot evidence is retained under ignored `.runtime/` and is not published. No provider resource or charge was created. Fresh synthetic balances are zero; no top-up, capture or payment was performed.

## Remaining gates

- A complete 10-request hosted **mock** round-trip with usage and ledger reconciliation has not run in this session.
- Durable private evidence export independent of this PC is not established. Raw database, credentials and logs are not uploaded as public Actions artifacts.
- No real worker canary, GPU model readiness, fresh all-in deployment quote or armed independent watchdog is established for a new rental.
- Public beta, live Stripe, automatic provisioning and the real experiment admission gate remain disabled.

The host is time-bounded: the script stops within 120 minutes of its start and the job has a 130-minute ceiling. Cleanup removes only this new disposable mock database and exact Compose project. Auth0 callback configuration persists after the tunnel disappears; the next session needs another exact-URL approval or an independently approved stable hostname. The temporary runner is not persistent hosting, a durable billing archive, or proof that the future GPU experiment is ready.
