"""
rag/llm_providers/groq_provider.py

Groq API provider — primary LLM for RAG answer generation.

Free tier: 30 req/min on llama-3.3-70b-versatile (as of June 2026).
Temperature=0.0 is supported and required for deterministic answers.

Required environment variable:
    GROQ_API_KEY — get a free key at https://console.groq.com/keys
"""

from __future__ import annotations

import os
import time
from typing import Final

from .base import LLMProviderError

MAX_RETRIES: Final[int] = 3
RETRY_DELAYS_SECONDS: Final[tuple[int, ...]] = (2, 4, 8)
DEFAULT_MODEL: Final[str] = "llama-3.3-70b-versatile"


def generate(
    system_prompt: str,
    user_message: str,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 512,
) -> str:
    """
    Call the Groq API and return the response text.

    Retries up to MAX_RETRIES times on RateLimitError with exponential backoff.
    Raises LLMProviderError on unrecoverable failure.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise LLMProviderError("GROQ_API_KEY environment variable not set.")

    try:
        import groq as groq_sdk
    except ImportError as exc:
        raise LLMProviderError(
            "groq package not installed. Run: pip install groq"
        ) from exc

    client = groq_sdk.Groq(api_key=api_key)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message},
    ]

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()

        except groq_sdk.RateLimitError:
            if attempt == MAX_RETRIES:
                raise LLMProviderError(
                    f"Groq rate limit exceeded after {MAX_RETRIES} retries. "
                    "Set LLM_FALLBACK_PROVIDER=gemini to use the Gemini fallback."
                )
            time.sleep(RETRY_DELAYS_SECONDS[attempt])

        except groq_sdk.APIError as exc:
            raise LLMProviderError(f"Groq API error: {exc}") from exc

    # Should never be reached — loop always returns or raises.
    raise LLMProviderError("Groq: exhausted retries without raising.")  # pragma: no cover
