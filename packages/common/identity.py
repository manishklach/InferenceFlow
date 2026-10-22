"""Identity shared by the control plane, worker and pinned vLLM deployment."""

import hashlib
from packages.common.config import settings


def model_identity():
    cfg = settings()
    return {
        "repo": cfg.model_repo,
        "revision": cfg.model_revision,
        "tokenizer_revision": cfg.model_revision,
        "execution_mode": cfg.execution_mode,
    }


def served_model_name():
    identity = model_identity()
    value = ":".join(identity.values())
    return "qwen3-4b-" + hashlib.sha256(value.encode()).hexdigest()[:24]


if __name__ == "__main__":
    print(served_model_name())
