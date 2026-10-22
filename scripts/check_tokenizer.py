"""Download only the pinned tokenizer, never model weights or GPU resources."""

import json
from packages.common.config import settings
from packages.common.tokenizer import count_prompt

pin = json.load(open("infra/model-lock.json"))
cfg = settings()
cfg.execution_mode = "vllm"
cfg.model_revision = pin["revision"]
n = count_prompt([{"role": "user", "content": "Name the capital of France."}])
assert n == 18, "Pinned tokenizer/template changed"
print(json.dumps({"pinned_tokenizer": cfg.model_revision, "prompt_tokens": n, "gpu_inference": False}))
