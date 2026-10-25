# Three auditable-extraction discovery hypotheses

These are interview hypotheses, not validated markets, legal/compliance claims or implemented features. The first GPU workload tested synthetic summaries, not extraction accuracy. A narrow segment must offer value beyond commodity token cost, and must be validated before building.

| Segment and interview roles | Narrow document workflow | Audit evidence to investigate | Hypothesis to test |
|---|---|---|---|
| Freight forwarders / regional 3PLs: operations leads, document coordinators | Extract shipment references, dates, quantities and delivery exceptions from bills of lading and proof-of-delivery documents | Source page/field location, original value, correction history, reviewer approval, missing-field exceptions | Batched document review has a real non-instant deadline; reducing manual reconciliation is valuable even if inference tokens are not cheaper |
| Wholesale distributors: accounts-payable managers, purchasing operations | Extract invoice line items and PO references for human-reviewed invoice/PO matching | Field-to-source evidence, duplicate/mismatch flags, approved corrections, export history | Reconciliation labor and exception handling dominate cost; reliable abstention and traceability matter more than generic chat latency |
| Industrial suppliers / manufacturers: quality-document coordinators, supplier operations | Extract lot IDs, material grades, test dates and stated results from supplier certificates and inspection documents | Exact source spans, units, version/lot linkage, human sign-off, explicit unreadable/unsupported fields | Teams need a reviewable record of what a document states; they may pay for reliable document handling rather than a model's compliance judgment |

Start discovery with logistics teams because the workflow can be narrowly scoped to a recurring batch and clear operational fields. That is a starting hypothesis, not evidence of superior demand. Do not infer shipping-document extraction quality from the synthetic logistics-summary benchmark. Keep decisions requiring domain judgment with the customer's reviewers; do not market extraction as a legal, financial or safety certification.

## Short interview guide (20–25 minutes)

1. **Last real case:** “Walk me through the last document batch you processed. Where did it arrive, who handled it, and what happened next?” Ask for a redacted example only if they can share it appropriately.
2. **Volume and deadline:** “How many documents/pages were in that batch? What were last month's average and peak volumes? When did the results actually need to be ready?” Separate seconds/minutes/hours/day requirements.
3. **Current effort and cost:** “Which steps were manual? How long did they take, including rework and exceptions? What systems or vendors do you already pay for?” Ask how they measured those numbers.
4. **Errors and abstention:** “Describe the last incorrect or missing field. How was it detected, what did it cost to correct, and which errors are unacceptable? When should software ask for review rather than guess?”
5. **Evidence:** “What must a reviewer see to trust a value? Do you need page/position references, original text, correction history, reviewer identity or retained versions? Who later asks for this evidence?”
6. **Adoption constraints:** “Where must output go? What access, retention, security and vendor-review requirements would block a pilot? Who approves a new tool and budget?” Do not assume one policy fits the segment.
7. **Pilot and purchase:** “What small real batch could demonstrate value? What measurable result would justify a paid pilot, and what would make you reject it? Who else should we interview?” Ask how they would compare against their existing process rather than seeking praise for our idea.

Record actual past behavior, quantities, deadline distribution, review minutes, error costs, required evidence, purchasing authority and contradictory examples. Avoid leading questions such as “Wouldn't an auditable AI platform help?” Do not promise savings, accuracy or delivery guarantees before a quality-labeled evaluation. Ask permission before recording or retaining any documents; do not send interview invitations/messages without separate authorization.

## Decision criteria before building extraction

Interview multiple independent organizations per candidate segment. Look for recurring document types, an identifiable buyer, a reachable batch deadline, access to appropriately redacted evaluation examples, measurable review/correction effort and a concrete willingness to run a paid pilot. Stop if volumes are too small, every document requires expert judgment, evidence requirements cannot be met, or integrations/review effort erase the value. Prioritize the segment with the clearest repeated workflow and buyer evidence, not the most enthusiastic interview. No extraction UI, parser, schema, integration or storage feature is authorized by this research proposal.
