# Auditable execution receipts

This is the first foundation for auditable batch inference, not a demonstrated competitive moat. A receipt connects a finished request to its recorded model identity, content hashes, usage and settlement. Customer trust, useful recovery history and independently demonstrated economics still have to be earned.

The [October 27 hosted A40 experiment](validation/2026-10-27/a40-hosted-1010-report.md) verified 1,010 real receipts against outputs and independent SQL settlement records, including controlled worker interruption with four repeated attempts and no duplicate capture. This validates the tested path, not every possible failure mode.

## API and SDK

`GET /v1/jobs/{job_id}/receipts?cursor=0&limit=100` uses the same tenant authentication as results. Another tenant receives 404. A job with any nonterminal request returns 409, including unresolved `billing_pending` work. Terminal failed/canceled/expired requests receive zero-usage receipts where appropriate. Pages contain `items` and `next_cursor`; no prompts, outputs, worker credentials or tenant-independent data are returned.

```python
from packages.python_sdk import InferenceFlowClient, verify_receipt

with InferenceFlowClient(api_key, base_url) as client:
    page = client.get_receipts(job_id)
    for envelope in page["items"]:
        assert verify_receipt(envelope)  # Integrity check, not an operator signature.
        record = envelope["receipt"]
        assert record["billing"]["request_settlement_reconciled"]
        print(record["custom_id"], record["usage"], record["billing"]["captured"])
```

Receipts record:

- Pinned repository/revision/tokenizer and execution mode from the stored model-price/version snapshot. A Git revision is not a hash of every loaded weight file or hardware attestation.
- SHA-256 of canonical submitted messages, the full normalized request payload, and the successful UTF-8 output. Full normalized payload includes custom ID and defaulted generation settings. Hashes are saved at submission/finalization; purging encrypted content does not erase them. Existing rows without saved hashes remain null; the migration does not fabricate historical evidence.
- Input/output tokens, price ID, test-only rate flag, rates per million tokens, and integer micro-USD reservation/capture/release amounts. These customer charges are separate from provider GPU costs.
- Request-specific ledger reconciliation: exactly one reservation/capture/release source, correct deltas and usage record consistency. This is a read-only check, not a repair or a replacement for whole-wallet reconciliation. Canceled work can have a zero-value capture journal entry and no billable usage.
- Attempts, completion/deadline times, status, finish reason and lateness. Exactly-once settlement does not mean a request physically executed only once.

## Integrity and privacy boundaries

The envelope contains `receipt` plus `sha256`. Schema `inferenceflow.execution-receipt.v1` hashes JSON with sorted keys, separators `,`/`:`, UTF-8, unescaped Unicode, no NaN, and no trailing newline. Output hashes use raw UTF-8 output text. The SDK verifier rejects a changed body under its original digest.

The receipt is **unsigned operator evidence**. Anyone who changes both the body and digest can produce another self-consistent envelope. This is not tamper-proof storage, a digital signature, independent execution attestation, a guarantee of determinism, or proof of no retention. Existing encrypted-content retention rules remain unchanged. Hashes may reveal predictable low-entropy content by guessing; treat exported receipts as customer data. No public receipts or cross-tenant job-history dataset is created.

Migration `0008` adds three nullable metadata columns. Reserve/capture/release algorithms, pricing and wallet mutation paths remain unchanged; submission/finalization only add content hash metadata.

## Real-run validation

The hosted GPU stage driver retains customer receipts only inside the existing owner-encrypted experiment evidence. Every completed stage checks receipt digest, output hash, usage, captured amount and single usage/capture against retained results, alongside the independent SQL audit. Missing or inconsistent receipts stop further stages. Mock tests do not establish real GPU correctness; a paid run must pass these checks before any real-execution claim.

The next defensibility test is customer discovery: do buyers need these receipts enough to adopt the platform, and does recoverable asynchronous execution save them review work? Existing [three extraction hypotheses and interview guide](research/auditable-extraction-discovery.md) remain research; no extraction features were built here.
