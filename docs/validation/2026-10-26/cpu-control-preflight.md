# CPU-only hosted control preflight

Run [40282486311](https://github.com/manishklach/InferenceFlow/actions/runs/40282486311), source `aa0eeba845262f63413638b917cb8ae2c7bd524b`, owner-approved protected staging environment. **No GPU was rented.** The temporary host was cancelled after testing; its final encrypted database/audit artifact was downloaded and decrypted only in the protected local staging directory.

Verified HTTPS real-mode readiness, anonymous wallet rejection, missing-worker admission rejection without wallet mutation, and zero registered workers. Public beta, Stripe and provisioning stayed false. Sequential policy delivery changed max_inflight from four to one; adaptive delivery subsequently enabled scheduler v2 and adaptive dispatch with max_inflight four. The exact owner-approved callback was saved and verified after reload; application OIDC login returned status ok.

The encrypted final evidence contains two successful read-only stage audits, both with zero accepted inference requests. These prove no-work audit/control operation, not real GPU inference or customer billing accuracy. The previous 40-request mock Compose rehearsal is separate evidence of worker recovery and accounting across policy restarts.

## Blocking finding

The adaptive command took approximately five minutes to become observable through the API. Raw GitHub delivery was the transport in use; no claim is made that caching was conclusively identified as the cause. Source inspection also confirmed that receipt output from the detached host went to a private log, so the operator could not reliably acknowledge audit-only delivery from the live Actions log. These are pre-rental blockers: paid GPUs must not idle while controls are uncertain.

[PR 27](https://github.com/manishklach/InferenceFlow/pull/27) replaces raw-file polling with fixed main-branch GitHub Contents API reads using the existing ephemeral contents:read job token. It relays only whitelisted command metadata from the private receipt file into the foreground Actions log. The token is never included in container environment files, connection handoff or evidence. Actual delivery latency and audit acknowledgements must be verified on a fresh protected host before GPU rental approval. A new temporary tunnel will require its own exact callback approval if owner login is repeated.

## RunPod observations

Fresh authenticated inventory contained zero pods. The A40 pod `vio7n9ucbcyh6e` now has a posted GPU charge of **$0.04916666820645332** for the 06:00–07:00 UTC bucket; disk was reported as zero at this read. This is a posted observation, not proof that all charges have finalized. It is distinct from the earlier elapsed-lifetime quote estimate and does not establish fully loaded output-token economics. Last console balance observed was $9.62.

H100 SXM Secure was quoted at $3.99 GPU/hour plus $0.011/hour 80 GB temporary disk, total $4.001/hour. Secure stock was HIGH overall and MEDIUM in CA-MTL-1. Fresh H100 PCIe and NVL catalog reads returned NONE. These observations expire; verify balance, pending billing, exact placement and total price again before requesting rental approval. No automatic deployment subscription was enabled.
