from functools import lru_cache
from packages.common.config import settings


@lru_cache
def tokenizer():
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(
        settings().model_repo, revision=settings().model_revision, trust_remote_code=False
    )


def count_prompt(messages):
    if settings().execution_mode == "mock":
        return len(("".join(m["role"] + ":" + m["content"] + "\n" for m in messages) + "assistant:").encode())
    return len(
        tokenizer().apply_chat_template(messages, tokenize=True, add_generation_prompt=True, enable_thinking=False)
    )


def cost(tokens, rate):
    return (tokens * rate + 999999) // 1000000
