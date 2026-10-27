# A40 startup and REST log contract failure

October 27, 2026. **Model startup/fit was observed; zero customer inference jobs were admitted. No throughput, batching, receipts-under-real-load or savings result is claimed.**

## Resource and safeguards

Under the owner's standing financial approval with a $5 remaining-credit floor, one A40 48 GB was rented in RunPod Secure CA-MTL-1. The displayed balance was $8.23; the GPU quote was $0.59/hour plus displayed $0.011/hour for 80 GB temporary disk. The conservative guard was $0.61/hour with a $1 attempt allocation. There were no other pods, endpoints or network volumes in the preflight inventory.

CPU host [40480904397](https://github.com/manishklach/InferenceFlow/actions/runs/40480904397) passed pod-list authentication, detail/log 404 checks for an already terminated pod, anonymous GitHub status HTTP 200, pinned-model checks, worker-auth rejection, no-worker admission without wallet mutation and receipt-route deployment checks. The corrected receipt implementation had passed 252 tests, 31 scheduler regressions and 40 hosted mock requests with 40 verified receipts. A 404 route probe was explicitly not live-SSE proof.

Independent watchdog [40482158001](https://github.com/manishklach/InferenceFlow/actions/runs/40482158001) authenticated and armed at 09:38:16 UTC, with a 10:23:15 UTC cutoff. Pod `yo5k11tjg89b2t` was created at **09:38:53.370 UTC** and bound at 09:38:57 UTC. Readback matched one A40, pinned vLLM image, 80 GB disk, no ports/mounts and disabled global networking.

## Observed startup evidence

Operator provider-log reads observed the pinned Qwen3-4B model/tokenizer revision `1cfa9a7208912126459214e8b04321603b3df60c` on vLLM 0.8.5, with BF16 and a 10,240-token context/four-slot configuration.

| Observation | Evidence |
| --- | --- |
| Worker environment ready | 09:43:19.418 UTC, about 266 seconds after creation; this combines allocation/image/bootstrap rather than separately measuring each |
| Model download | 09:43:20.132–09:43:27.895 UTC, approximately 7.76 seconds |
| Engine launch requested | 09:43:28.122 UTC |
| Model loading | vLLM reported 7.5552 GiB and 1.836133 seconds; weight loading reported 1.38 seconds |
| Compilation | vLLM reported total `torch.compile` 54.39 seconds |
| KV capacity | vLLM reported 214,384 tokens and memory-based concurrency 20.94× at 10,240 tokens; the configured admission/engine slot cap remained four |
| Graph capture | vLLM reported 26 seconds and 0.53 GiB |
| Engine profile/cache/warmup | vLLM reported 113.36 seconds |
| API ready | Application startup complete 09:45:54.562 UTC; metrics HTTP 200 at 09:45:55.139 UTC |

These engine timing measures overlap; do not sum them as separate elapsed phases. The observations establish startup and memory fit on this pod, not throughput or a performance guarantee. The final database includes one registered worker, zero jobs, zero requests, zero execution attempts and zero usage records.

## Exact failure and correction

The owner-encrypted diagnostics identified **HTTP 422 on `GET /v2/pods/yo5k11tjg89b2t/logs`**. The hosted provider-log file was empty, so the admission telemetry gate stopped the host when the worker arrived. No customer request or customer capture was generated; only the synthetic initial funding entry exists.

Our collector sent REST query `source=both`. The live [RunPod OpenAPI contract](https://api.runpod.io/v2/openapi.json) allows only `source=container` or `source=system`; **omitting source selects both**. The MCP tool's convenient `both` option is translated by that adapter and is not a valid REST enum value. The earlier no-GPU probe omitted source, so it did not exercise the faulty collector query. This is a request-contract bug in our collector, not evidence of bad model compatibility or denied log credentials.

The fix shares a request builder between preflight and collector: initial query `tail=5000` with no source, and reconnect with the provider's unchanged Last-Event-ID and no source/tail override. Permanent 401/403/422 errors now fail startup immediately, rather than waiting through image/model initialization. Tests check actual outgoing query/header combinations, event retention, cursor preservation and no admission after a permanent collector error. Policy-transition report GETs also use the existing bounded read-retry helper; no mutation retries were added.

## Cleanup, cost and next gate

After the host failure was observed, the operator DELETE returned 204; an authenticated GET returned 404. The watchdog independently confirmed absence at **09:46:55.942 UTC**. This attempt does not prove that the watchdog initiated removal. No persistent storage was requested and pod inventory was empty afterward.

Creation to independent absence confirmation was at most 482.572 seconds, approximately **$0.082 at the guard rate**. The initial billing read had no records; the itemized bill remains pending and is not assumed zero. Cost per successful output token is undefined because no customer inference requests completed. No replacement is created by this report.

Twenty-three focused offline checks and lint passed for the fix. Full CI, hosted mock receipt checks and the exact-query no-GPU preflight remain gates before another rental. Further financial approval is covered by the owner's standing authorization only while preserving $5 credit, pending costs and shutdown headroom. Protected GitHub environment reviews remain mandatory. Public beta, live Stripe and automatic provisioning remain disabled.
