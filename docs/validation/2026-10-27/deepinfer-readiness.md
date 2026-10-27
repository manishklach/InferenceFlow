# Latest DeepSeek / DeepInfer: pinned rehearsal and budget gate

October 27, 2026. **NO-GO for a paid GPU run under the current balance and credit floor.** Source and CPU syntax checks passed; native CUDA compilation, an immutable working image, memory/interconnect fit and model execution remain unverified. No pod, volume or paid API call was created for this work. See [structured evidence](deepinfer-readiness.json).

## What was actually performed

- Cloned the official DeepInfer repository into ignored local storage and checked out `553741557a57df44a46fb3ab72b6aafeaf945337` detached. The [source lock](../../../infra/throughput/deepinfer-source-lock.json) records 16 contract-file hashes and four NVIDIA vendor gitlinks. Hashes normalize UTF-8 text to LF; they do not silently normalize model weights.
- Verified the exact source commit, tracked-file cleanliness, contract hashes and vendor gitlink pins with a new read-only preflight command. Vendor checkouts are not initialized/built by that command.
- Started the existing Docker Desktop Linux engine and used an existing isolated Python 3.12.10 image, network disabled and source mounted read-only. The checked-in [CPU rehearsal script](../../../infra/throughput/deepinfer/syntax_rehearsal.py) parsed **270 Python files and 10 shell scripts**. It never imports or executes DeepInfer. The CPU image ID is in the JSON evidence; it is **not** a DeepInfer serving image.
- Detected Windows CRLF in all ten shell scripts. Raw `bash -n build.sh` failed; normalized LF text passed. A future native build must clone/check out source inside Linux with LF line endings, rather than execute this Windows-mounted checkout directly.
- Read metadata for the pinned latest-model snapshot without downloading weights: **48 safetensors shards, 510,296,708,312 bytes (510.30 decimal GB / 475.25 GiB)**. The old 80 GB experimental disk cannot hold it.
- Added and tested actual native-token accounting, including draft acceptance, failures, rank deduplication and rejection of nominal benchmark data. No synthetic result is presented as GPU evidence.

## Build and runtime compatibility

| Item | Pinned-source finding | Verification state |
| --- | --- | --- |
| Model | `deepseek-ai/DeepSeek-V4.1-Flash-1017`, revision `1bae0e1088993b9b82de08f59de5be5a34e42170` | Metadata/config identity checked; weights not downloaded |
| Runtime | DeepInfer commit above | Source contract audited |
| Python | 3.12 | CPU syntax checked on 3.12.10 |
| NVIDIA PyTorch | `2.13.0+cu132` | Requirement read; wheel resolution/install unverified |
| CUDA line | 13.2 for this pinned stack | Do not reuse the old vLLM CUDA/image assumptions |
| NCCL | Build script forces `2.32.3` | Source read; ABI/runtime unverified |
| Native ABI | C++20 and PyTorch CXX11 ABI | Source read; C++/CUDA compilation not run |
| Vendor operators | DeepSelect, FlashMLA, DeepEP, DeepGEMM | Gitlink commits pinned; libraries not built |
| Hardware | Upstream lists NVIDIA SM100 and Ascend 950 | No device validated by InferenceFlow |
| Complete service | Native release is offline-oriented | No native HTTP/worker adapter implemented |

This is a separate environment from both the existing Qwen/vLLM 0.8.5 worker and the proposed newer vLLM recipe. Do not upgrade the platform's shared dependencies to DeepInfer's requirement set. Native dependency resolution, vendor builds, `deepinfer._C` import, collective communication, final-answer parsing and model generation still need validation. A source/syntax pass is not a native build pass.

Upstream's example uses EP8. Four B200s are only a **memory-sizing hypothesis**, not a verified minimum. The checkpoint's file size does not establish resident weights, Engram duplication/offload, KV cache, scratch buffers, process replication or usable memory. A suitable NVLink/peer-access topology and sufficient CPU RAM must be verified. B300 compatibility is not established merely because its family is Blackwell; do not automatically substitute it for documented SM100 support. H100/H200 support through another engine does not prove native DeepInfer support.

## Cost and live capacity

Fresh authenticated RunPod catalog reads, Secure Pods, CUDA floor 13.2:

| Candidate | Stock at check | GPU-only catalog rate |
| --- | --- | ---: |
| 4 x B200 180 GB | NONE | 4 x $7.99 = $31.96/hour |
| 8 x B200 180 GB | NONE | 8 x $7.99 = $63.92/hour |
| 4 x B300 | NONE; native runtime compatibility unverified | 4 x $8.99 = $35.96/hour |

Current displayed credit: **$7.26**. Owner floor: **$5**. Maximum above the floor is **$2.26**, or **$1.86** after an additional $0.40 pending-charge reserve. Four B200s would cost **$2.66333 for five minutes**, **$7.99 for 15 minutes**, or **$15.98 for 30 minutes**, GPU only. These lower bounds already exceed the remaining authorized funds. They are not available reservations or an all-in experiment quote.

Storage, staging/download overhead, image build/load, idle/failed work and cleanup must be included before approval. Capacity, model fit, a complete storage quote and a realistic experiment duration are unverified. It would be misleading to present an exact total or a ready-to-rent configuration. No teardown job was armed and no GPU was rented for this preparation. Do not spend down the credit floor or reuse the old Qwen approval/configuration.

## Critical benchmark-accounting finding

The pinned upstream `examples/README.md` defines decode throughput using **full draft acceptance**. Its `steps/s x batch x (1 + draft length)` figure is a nominal microbenchmark, not measured successful output tokens. Profiler timings also perturb execution and must not be used as unqualified production TPS.

The new `packages/common/deepinfer_measurement.py` instead consumes actual emitted `RequestOutput` token events. It counts successful emitted IDs over a synchronized cohort wall span, retains unsuccessful work in request/time accounting, and derives draft acceptance from the actual verification counters. It does not multiply by GPU count or assume that all drafts are accepted. No-draft acceptance is unknown/not applicable, not zero. Duplicate rank/request streams, missing accepted requests and inconsistent counters are rejected. Unit fixtures demonstrate three emitted tokens when full-acceptance accounting would suggest six; those fixtures are explicitly mock.

Emitted IDs can include reasoning and special tokens. The tool therefore leaves **final-answer tokens unknown** and marks the summary **ineligible for final-answer throughput-profile qualification**. A protocol-aware final-answer parser, pinned tokenizer accounting and quality evidence are still required. It does not validate InferenceFlow's queue, customer receipts or billing. The native event capture/serving adapter is not implemented or GPU-validated by this change.

## Reproduce the free checks

From the platform repository, with development dependencies installed:

```bash
git clone --filter=blob:none --no-checkout https://github.com/deepseek-ai/DeepInfer.git .runtime/deepinfer-source
git -C .runtime/deepinfer-source checkout --detach 553741557a57df44a46fb3ab72b6aafeaf945337
python -m scripts.deepinfer_preflight source \
  --source .runtime/deepinfer-source --output .runtime/deepinfer-source-audit.json
python -m scripts.deepinfer_preflight native-schema --output .runtime/deepinfer-native-schema.json
python -m unittest tests.test_deepinfer_preflight tests.test_throughput_profiles -q
```

Reuse an existing matching checkout rather than cloning over it. The source audit checks source identities only; it does not build, initialize submodules, download models, start servers or contact a provider. Output files are not overwritten. Inside an isolated **Linux Python 3.12** environment, run `python syntax_rehearsal.py --source /read-only/pinned/checkout` using the checked-in script. It needs Bash for shell syntax validation, but no PyTorch, CUDA, weights or GPU.

A separate manual [GitHub CPU rehearsal](../../../.github/workflows/deepinfer-readiness.yml) repeats source/syntax checks and unit tests with contents-read permission, no environment secrets, no provider key and a ten-minute timeout. It uploads only public source-audit/syntax reports. It does not compile CUDA, download weights or provision anything.

For an eventual native capture conforming to the schema:

```bash
python -m scripts.deepinfer_preflight summarize-native \
  --input .runtime/native-events.json --output .runtime/native-summary.json
```

This summarizes supplied events; it never runs DeepInfer. Do not feed it the upstream nominal `result_jsonl` or label synthetic events real. Store raw events privately because token IDs can reconstruct text. The exported summary contains counts and a canonical digest, not token IDs or text. Its declared real/mock mode is an operator assertion, not independent hardware attestation.

## Minimum next experiment once funding/capacity permit

1. Resolve/install the locked native dependencies and build the pinned vendor operators in an isolated Linux/CUDA 13.2 environment. Record compiler, wheel hashes and final image digest. Test native import and a small kernel first; do not compile the entire stack on a paid model-serving rental by default.
2. Validate memory fit and device interconnect on a supported topology; stage the pinned model/cache without unbudgeted persistent storage. Verify final-answer parser/tokenizer behavior and capture exact emitted IDs and actual draft counters.
3. Prepare the CPU controller and independent teardown **before** starting the paid clock. Check current balance, all-in quote, storage cleanup and verified watchdog authority. Native trials are separate from the existing OpenAI-compatible HTTP benchmark until a service adapter is tested.
4. Smoke ten requests with DSpark off, verifying nonempty complete answers, actual counters and telemetry. Stop on missing accounting, memory errors, quality failure or unexpected charges.
5. Use identical hashed short/medium workloads and explicit sampling. Run three balanced paired baseline/candidate cohorts of 100 requests, changing **one** setting at a time: first bounded concurrency, then native drafting. Explicitly set no-draft baseline; the upstream default is drafting enabled. Confidence-scheduled verification and memory/offload changes are separate later arms, not silent changes to the baseline.
6. Count successful emitted and final-answer tokens separately, acceptance rate, p50/p95/p99, failures, complete rented lifetime, provider invoice and task correctness. Do not substitute nominal decode curves or projected estimator attainment for these measurements. Include cold/idle/failed work in economics. Full InferenceFlow recovery/receipt checks follow only after a native worker adapter exists.

The current [profile qualifier](../../performance/model-throughput-controller.md) remains offline/advisory. No native serving image, paid benchmark result, qualified DeepSeek profile, throughput improvement or cost advantage is claimed. A larger funded budget and fresh compatible capacity are prerequisites for real execution.

## Primary source references

- [Pinned DeepInfer README](https://github.com/deepseek-ai/DeepInfer/blob/553741557a57df44a46fb3ab72b6aafeaf945337/README.md)
- [Pinned build script](https://github.com/deepseek-ai/DeepInfer/blob/553741557a57df44a46fb3ab72b6aafeaf945337/build.sh) and [NVIDIA requirements](https://github.com/deepseek-ai/DeepInfer/blob/553741557a57df44a46fb3ab72b6aafeaf945337/requirements-nvidia.txt)
- [Pinned benchmark semantics](https://github.com/deepseek-ai/DeepInfer/blob/553741557a57df44a46fb3ab72b6aafeaf945337/examples/README.md)
- [Pinned model repository](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017/tree/1bae0e1088993b9b82de08f59de5be5a34e42170)
- RunPod price/stock reads and authenticated balance observation are recorded in the structured evidence; they are snapshots, not reserved capacity.
