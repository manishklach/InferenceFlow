# Internal GPU unit economics

These reports do not alter customer prices, prepaid reservations or ledger settlement. Amounts use integer micro-USD (1 USD = 1,000,000). Quoted cost rounds uptime upward to the provider billing increment, then money upward with Decimal arithmetic. A quote is not a verified bill.

## Definitions

- Estimated GPU cost = ceil(billable uptime × quoted hourly micro-USD / 3600).
- Total-token CPM = GPU cost / (successful input + successful output tokens) × 1,000,000.
- Output-token CPM = GPU cost / successful output tokens × 1,000,000.
- Gross margin = (attributable customer token revenue − GPU cost) / attributable revenue.

Zero token denominators and zero revenue produce null, not zero cost or infinite margin. Input and output volumes remain separate because prefill and decode differ. Failed/retried work consumes paid uptime without generating customer token revenue. Revenue here is gross captured token charges before refunds, payment fees, storage, networking, tax or other operating costs. This is not contribution margin or a final financial statement.

## Hypothetical example, not a measured result or price

At a hypothetical $1.20/hour, two paid hours cost $2.40. If successful processing totals 3M input + 1M output tokens and token revenue is $4, total-token CPM is $0.60, output-token CPM is $2.40, and GPU-only gross margin is 40%. Idle time, cold starts and failed work are already inside the two-hour rental cost. Additional expenses reduce contribution margin. Change all assumptions to actual deployment observations before making claims.

## Record an approved manual GPU

These CLI commands only record metadata in PostgreSQL. They never contact a provider, create capacity or stop billing. Rent only after separate explicit operator expense approval, and record the actual provider timestamps and quote. Do not run placeholders verbatim.

~~~bash
python -m packages.common.cli gpu-attach --instance-id YOUR_PROVIDER_ID --provider manual-nvidia --gpu-type YOUR_GPU --hourly-micro-usd YOUR_CONFIRMED_QUOTE --started-at ACTUAL_ISO_UTC_START --billing-increment-seconds 60 --startup-seconds ACTUAL_STARTUP_DURATION
~~~

Set `PROVIDER_INSTANCE_ID` on the worker to this tracked ID. Set `WORKER_MODEL_LOADING_SECONDS` to actual weight-loading duration from engine logs (zero/default means unknown). `MODEL_LOADING_SECONDS` is a separate planning assumption. Canary/readiness elapsed time is not weight-loading duration. Automatic Runpod creation, when separately approved/configured, records provider/GPU type with the existing lifecycle intent.

Use one worker agent with a stable `WORKER_ID` per GPU instance. Do not register multiple agents against the same engine/instance: their slot and sampled-activity observations would overlap. Set the planner/provider billing increment and confirmed quote to the actual provider terms; they are operator inputs, not inferred invoice data.

Heartbeat observations store sampled active/idle seconds and leave missed coverage unknown. These are activity proxies, not GPU kernel execution timing. Re-registration can lose a final heartbeat interval and resets reported model-loading duration; preserve source logs for a real experiment. The report includes unobserved seconds and explicitly lists execution modes. Successful requests without a tracked instance are excluded from attributed margin and counted as unattributed.

## Replace quotes with provider invoices

Retrieve the actual provider bill yourself. Reconcile the exact instance and cumulative billing from the recorded instance start through an explicit UTC endpoint, including provider minimums, startup and billing increments. No automatic invoice API integration is claimed.

~~~bash
python -m packages.common.cli gpu-invoice --instance-id YOUR_PROVIDER_ID --provider YOUR_PROVIDER --gpu-type YOUR_GPU --invoice-micro-usd ACTUAL_CUMULATIVE_AMOUNT --reference UNIQUE_BILL_REFERENCE --invoiced-through ACTUAL_ISO_UTC_END --billing-increment-seconds 60
python -m packages.common.cli scheduling-report
~~~

References are idempotent for identical values; conflicting reference reuse is rejected. Updates are audited, coverage cannot move backwards, and customer wallets remain untouched. Reports expose quoted estimates and invoice amounts separately. Nested `provider_invoice_economics` uses only successful attempt tokens and captured revenue through the invoice endpoint. A partial invoice must never be compared with lifetime tokens or treated as a full bill; report the coverage interval alongside each result.

After stopping the GPU **at the provider and confirming billing stopped**, record that observation:

~~~bash
python -m packages.common.cli gpu-record-stop --instance-id YOUR_PROVIDER_ID --stopped-at ACTUAL_ISO_UTC_STOP --reference SHUTDOWN_CONFIRMATION
~~~

This last command does not stop a pod. Missing shutdown records continue accumulating estimated quoted cost. Keep provider alerts, independent watchdog and actual invoice reconciliation; control-plane ceilings cannot guarantee provider billing stops during outages.
