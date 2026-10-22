# Prepaid accounting
All money is integer micro-USD. USD 1 = 1,000,000 units. Rate cards use micro-USD per million tokens. Local sample rates are synthetic test fixtures, not offered public prices.

For each request, reserve `ceil(prompt * input_rate / 1e6) + ceil(max_output * output_rate / 1e6)`. Capture `ceil(engine_input * input_rate / 1e6) + ceil(engine_output * output_rate / 1e6)` once; release the remainder. Each component rounds upward separately. Example test rates: 10 input tokens at 100000 plus 5 output at 300000 -> 1 + 2 = 3 micro-USD. Failed attempts cost the operator, not the customer.

Wallet lock and append-only postings update available/reserved atomically. Reservation: (-amount,+amount). Capture: (0,-actual). Release: (+unused,-unused). Top-up: (+funds,0). Unique source references dedupe each posting; usage primary key is request_id. Terminal states are fenced. Missing or mismatched token usage quarantines reservation and output for audit, with zero capture. No automatic billing guess.

Stripe accepts only sk_test_ credentials and rejects live events. Enable both STRIPE_ENABLED and PUBLIC_BETA_ENABLED only after review. Checkout credits only paid USD fixed-amount sessions; unique PaymentIntent prevents duplicate credit from multiple events/sessions. Refund amount is cumulative and only new reversed amount is debited. Disputes freeze the tenant. If funds already spent, debit available balance, audit shortfall debt, keep account frozen and reconcile manually. Never make available balance negative.

```sql
SELECT w.tenant_id, w.available, w.reserved,
       COALESCE(SUM(l.available_delta),0) AS journal_available,
       COALESCE(SUM(l.reserved_delta),0) AS journal_reserved
FROM wallets w LEFT JOIN wallet_ledger l ON l.tenant_id=w.tenant_id
GROUP BY w.tenant_id,w.available,w.reserved
HAVING w.available != COALESCE(SUM(l.available_delta),0)
    OR w.reserved != COALESCE(SUM(l.reserved_delta),0);
```

Run `python -m packages.common.cli reconcile`. For billing_pending, compare engine/tokenizer revision and usage, identify a valid current result, then perform a reviewed transaction with explicit audit event and ledger postings; do not UPDATE journal entries. Administrative reconciliation tooling needs hardening before beta. Taxes, refund policy, prepaid credit terms and processor reconciliation require launch review.

Audited CLI reconciliation (operator database access only): `python -m packages.common.cli reconcile-request --request-id <id> --input-tokens <verified> --output-tokens <verified> --reference <review-ticket>`. It only accepts billing_pending, caps capture at original reservation, records usage/output and a permanent audit reference atomically.

For unverifiable or retention-purged output use `reconcile-request --request-id <id> --release-only --reference <review-ticket>` to release the full reservation and audit the decision.

## Refund and dispute freeze policy
After a verified reversal, the wallet lock serializes the event against finalization. All outstanding requests (including running/quarantined work) are canceled and fenced; their reservations are released before reversal. No later result from that work is charged. If finalization already committed, its captured amount remains usage and any unfunded reversal is journaled as wallet debt. Future credits repay debt first. The account remains frozen until an operator reviews its funding and explicitly unfreezes it. Debt is exposed as debt_micro_usd and debt_delta on wallet/transaction responses. Reconciliation compares wallet balances/debt to ledger totals, remaining request reservations, and captured usage.
