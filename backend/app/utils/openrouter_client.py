"""The LLM client.

Built lazily rather than at import time. A module-level `ChatOpenAI(...)` raises
during `import app.main` when the API key is absent, which takes the whole
service down - including `/health` - instead of failing one review with a clear
message.
"""
from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import (
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
    OPENROUTER_API_KEY,
)
from app.core.constants import DEFAULT_TEMPERATURE


class LLMNotConfigured(RuntimeError):
    """No LLM credentials are configured on this server."""


@lru_cache(maxsize=4)
def get_llm(model: str | None = None, max_tokens: int = 4096) -> ChatOpenAI:
    if not OPENROUTER_API_KEY:
        raise LLMNotConfigured(
            "No OPENROUTER_API_KEY (or OPENAI_API_KEY) is configured, so reviews "
            "cannot run. Set one in the server environment."
        )

    return ChatOpenAI(
        model=model or LLM_MODEL,
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
        temperature=DEFAULT_TEMPERATURE,
        max_tokens=max_tokens,
        # Without an explicit timeout the OpenAI SDK default is 10 minutes with
        # retries, so one stalled agent can hold a review open for half an hour.
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=1,
        default_headers={
            "X-Title": "CodeArmor",
            "HTTP-Referer": "https://github.com/imluffy000/CodeArmor",
        },
        # OpenRouter relays prompts to whichever upstream provider serves the
        # model, and these prompts contain users' private source code.
        # data_collection=deny restricts routing to providers that do not store
        # or train on them.
        extra_body={
            "provider": {
                "data_collection": "deny",
                "allow_fallbacks": True,
            }
        },
    )
