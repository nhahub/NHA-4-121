"""
rag/llm_providers/

Modular LLM provider package for the clinical RAG pipeline.

Active provider is selected by the LLM_PROVIDER environment variable:
  LLM_PROVIDER=groq    (default) — Groq API with llama-3.3-70b-versatile
  LLM_PROVIDER=gemini            — Google Gemini free-tier fallback

Switch at runtime without touching any other module:
  export LLM_PROVIDER=gemini
  export LLM_FALLBACK_PROVIDER=groq
"""

from .base import LLMProviderError
from .router import generate

__all__ = ["generate", "LLMProviderError"]
