"""
rag/llm_providers/base.py

Common interface every LLM provider module must implement.

Each provider module must expose a module-level function:

    def generate(
        system_prompt: str,
        user_message: str,
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str: ...

On success it returns the raw response text (stripped).
On any unrecoverable failure it raises LLMProviderError.
"""

from __future__ import annotations


class LLMProviderError(RuntimeError):
    """
    Raised when an LLM provider call fails after all retries.

    Caught by call_groq() in answer_generator.py and re-raised as
    AnswerGeneratorError so the rest of the pipeline sees a single
    exception type regardless of which provider was active.
    """
