"""
rag/llm_providers/router.py

Provider selection and automatic fallback for LLM answer generation.

Environment variables:
    LLM_PROVIDER          — primary provider name (default: "groq")
    LLM_FALLBACK_PROVIDER — fallback provider name (default: "gemini")
                            Set to "" or same as LLM_PROVIDER to disable fallback.

Usage:
    from rag.llm_providers.router import generate
    text = generate(system_prompt, user_message)

Switching providers at runtime (no code change needed):
    export LLM_PROVIDER=gemini          # use Gemini as primary
    export LLM_FALLBACK_PROVIDER=groq   # fall back to Groq on failure
"""

from __future__ import annotations

import os
from types import ModuleType
from typing import Final

from .base import LLMProviderError
from . import groq_provider, gemini_provider

_PROVIDERS: Final[dict[str, ModuleType]] = {
    "groq":   groq_provider,
    "gemini": gemini_provider,
}

DEFAULT_PRIMARY:  Final[str] = "groq"
DEFAULT_FALLBACK: Final[str] = "gemini"


def generate(
    system_prompt: str,
    user_message: str,
    *,
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 512,
) -> str:
    """
    Call the active LLM provider and return the response text.

    If the primary provider raises LLMProviderError (rate limit, bad key,
    safety filter, etc.) and a different fallback provider is configured,
    automatically retries with the fallback before propagating failure.

    Raises LLMProviderError if both primary and fallback fail.
    """
    primary_name  = os.environ.get("LLM_PROVIDER", DEFAULT_PRIMARY).strip()
    fallback_name = os.environ.get("LLM_FALLBACK_PROVIDER", DEFAULT_FALLBACK).strip()

    primary = _PROVIDERS.get(primary_name)
    if primary is None:
        raise LLMProviderError(
            f"Unknown LLM_PROVIDER: '{primary_name}'. "
            f"Supported: {sorted(_PROVIDERS)}"
        )

    kwargs: dict = {"temperature": temperature, "max_tokens": max_tokens}
    if model is not None:
        kwargs["model"] = model

    # ── Primary attempt ────────────────────────────────────────────────────
    primary_error: LLMProviderError | None = None
    try:
        return primary.generate(system_prompt, user_message, **kwargs)
    except LLMProviderError as exc:
        primary_error = exc

    # ── Fallback attempt ───────────────────────────────────────────────────
    fallback = _PROVIDERS.get(fallback_name)
    if fallback is None or fallback_name == primary_name or not fallback_name:
        # No usable fallback — raise the original primary error
        raise primary_error

    try:
        return fallback.generate(system_prompt, user_message, **kwargs)
    except LLMProviderError as fallback_error:
        raise LLMProviderError(
            f"Primary provider '{primary_name}' failed: {primary_error}. "
            f"Fallback provider '{fallback_name}' also failed: {fallback_error}"
        ) from fallback_error
