# Why We're Building InferenceFlow: GPU Inference Without Renting GPUs

For a developer processing a backlog of documents, the useful unit is a completed extraction or summary. A GPU reservation is an implementation detail. Yet running an open-weight model still asks that developer to think about model loading, GPU fit, concurrency, idle capacity and failures before the first useful result arrives.

InferenceFlow moves that operational work behind an asynchronous API. Submit a batch, receive an identifier, and collect ordered results later. Prepaid credits reserve a maximum charge and settle against completed token usage. Customers do not rent a GPU from us or receive a physical GPU partition. We, as the operator, still have to procure capacity and pay its bill.

That distinction matters. An API wrapper does not erase idle time. A GPU can be expensive when there is too little demand, and a busy queue can miss customers' deadlines. Our hypothesis is that several customers' compatible asynchronous jobs can share a warm model more efficiently than isolated deployments. It is a hypothesis to measure, not a reason to announce cheaper inference.

## Why asynchronous work is interesting

Many workloads can wait: classifying yesterday's support tickets, enriching a catalog, extracting structured fields or summarizing a collection. They need durable progress, recovery and predictable accounting more than an immediate first token. Separating acceptance from execution lets the platform reason about the queue and lets customers close their client connection without losing work.

Our target is to complete eligible work within an hour. That target is not a reason to wait for an hour's worth of requests. If a compatible warm worker has room, dispatch should happen on the next scheduling tick. vLLM handles continuous token batching; InferenceFlow controls concurrent request admission and dispatch around it.

## Scheduling is a product decision

A first-come queue is easy to describe and can still be unfair. One large customer can occupy the available slots. Blind urgency can produce a different failure: every new short deadline jumps ahead of older work. Our second scheduler combines weighted tenant service, bounded aging, bounded deadline urgency and exact model affinity. Existing worker and tenant limits remain hard boundaries.

The estimator is intentionally explainable. It considers maximum token work, current backlog, usable warm slots and conservative throughput assumptions. If we lack real measurements, it says so. Customers can choose disclosed best effort or request rejection when the target cannot be confidently supported. We do not turn uncertain arithmetic into an SLA.

## Economics include the quiet minutes

Token throughput alone is not a business model. Provider uptime includes cold starts, idle intervals and attempts repeated after a crash. Output-token cost can look very different from total-token cost, especially when input lengths change. We therefore record separate input/output volumes, quoted rental estimates, invoice coverage, token revenue and sampled activity, with missing observations marked unknown.

Exactly-once billing is as important as dispatch speed. Physical inference can repeat after a worker failure. A stale result must not charge a customer twice. The existing lease fences, worker generations, immutable rate snapshots and transactional wallet journal stay underneath the new scheduler.

## What we have proved, and what comes next

The repository has executable mock inference, PostgreSQL concurrency and billing tests, a recorded end-to-end flow and deterministic scheduler simulations. Simulations help expose scheduling tradeoffs; they are not GPU benchmarks. In the mixed-deadline experiment, some changes help one metric while hurting another. That is evidence to inspect rather than a headline to smooth away.

The next proof requires a real, explicitly approved NVIDIA experiment: pinned artifacts, representative input/output mixes, actual provider uptime and bill, deadline reliability, worker restart recovery and zero ledger drift. No paid capacity or live payments were activated for this implementation. Automated provisioning remains disabled and capacity planning produces recommendations only.

If pooling improves measured economics while preserving useful completion reliability and output quality, it will be worth building on. If it does not, the right response is to change the workload or the approach. Customers deserve completed useful work and trustworthy accounting, not unsupported GPU-efficiency claims.
