# A sub-hour objective for asynchronous inference

InferenceFlow lets customers submit independent text-processing work, receive a job ID immediately and retrieve ordered results later. Its v0.3 scheduling hypothesis is that shared warm capacity, concurrent dispatch and completion-aware scheduling can improve the cost/reliability balance for workloads that tolerate asynchronous completion. This remains an experimental hypothesis.

With scheduler v2 enabled, new jobs default to a configurable 3,600-second target, measured from acceptance to every request becoming terminal. Capacity dispatches promptly; an hour is not an intentional queueing delay. Standard/economy priorities remain. Existing jobs and explicit requested deadlines are preserved; with v2 disabled the prior tier defaults apply.

Eligible workloads are independent classification, extraction, enrichment, summarization and synthetic-text batches within catalog/context/tenant/credit limits. Interactive streaming chat, arbitrary models and time-critical workloads requiring a guaranteed deadline are outside this milestone.

Admission responds explicitly:

- `best_effort`: accept with a persisted estimate, reasons, source and calibration status, and reserve the published maximum token charge.
- `reject_if_at_risk`: reject before reservation when available capacity and calibrated estimates cannot support the target. Increase the target, attach approved capacity or choose disclosed best effort.

No real GPU calibration has been performed here. The estimator labels its assumptions uncalibrated. Successful deadline attainment requires every request to succeed within target. Failed, canceled, expired or partial jobs never inflate successful counts. Queue expiration releases unstarted reservations; running work can finish late and bill returned output under the existing cancellation policy.

Customers pay for completed input/output tokens, not GPU partitions. The operator owns rental cost and recovery. Shared capacity is logical scheduling across customers; it does not imply dedicated physical isolation. Tenant authentication, encrypted content, scoped reads, immutable rates and exactly-once billing remain core requirements.

Compared with a synchronous request, the API separates admission from execution, makes progress and recovery visible, and tolerates waiting. It does not establish lower prices than hosted alternatives. Real provider bills, identical model/tokenizer/decoding, matched workload distributions, failures, idle time, output quality and customer outcomes are needed before making an economic claim.

**There is no formal 60-minute SLA in v0.3.** The immediate release goal is readiness to test the hypothesis on explicitly approved NVIDIA capacity.
