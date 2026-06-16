"""
rag/llm_providers/gemini_provider.py

Google Gemini API provider — fallback LLM for RAG answer generation.

Free tier: gemini-1.5-flash, ~15 req/min, 1M token context window.

Required environment variable:
    GEMINI_API_KEY — get a free key at https://aistudio.google.com/app/apikey

Caution for clinical synthetic text:
    Gemini's content policy may occasionally trigger a safety filter on
    clinical-sounding phrases (e.g., "patient diagnosed with") even in
    clearly synthetic, academic contexts. When this happens, generate()
    returns an empty string which is caught and raised as LLMProviderError.
    Test the allergy query ("Does this patient have a documented allergy?")
    manually before relying on Gemini as a demo fallback.
"""

from __future__ import annotations

import os
import time
from typing import Final

from .base import LLMProviderError

MAX_RETRIES: Final[int] = 3
RETRY_DELAYS_SECONDS: Final[tuple[int, ...]] = (2, 4, 8)
DEFAULT_MODEL: Final[str] = "gemini-1.5-flash"


def generate(
    system_prompt: str,
    user_message: str,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 512,
) -> str:
    """
    Call the Gemini API and return the response text.

    Retries up to MAX_RETRIES times on rate-limit errors.
    Raises LLMProviderError on empty response (safety filter) or API failure.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise LLMProviderError("GEMINI_API_KEY environment variable not set.")

    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise LLMProviderError(
            "google-generativeai package not installed. "
            "Run: pip install google-generativeai"
        ) from exc

    genai.configure(api_key=api_key)

    gen_model = genai.GenerativeModel(
        model_name=model,
        system_instruction=system_prompt,
    )

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = gen_model.generate_content(
                user_message,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )
            # Empty text = safety filter triggered
            if not response.text:
                raise LLMProviderError(
                    "Gemini returned an empty response — likely a content-policy "
                    "filter on clinical-sounding text. "
                    "Check the query wording or use Groq as primary provider."
                )
            return response.text.strip()

        except LLMProviderError:
            raise  # don't retry safety-filter failures

        except Exception as exc:
            err_str = str(exc).lower()
            if ("rate" in err_str or "quota" in err_str) and attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAYS_SECONDS[attempt])
                continue
            raise LLMProviderError(f"Gemini API error: {exc}") from exc

    raise LLMProviderError("Gemini: exhausted retries without raising.")  # pragma: no cover
