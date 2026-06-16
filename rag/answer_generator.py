"""
rag/answer_generator.py  —  Step 18B

Grounded RAG answer generation for the clinical summarization pipeline.

Three-layer hallucination prevention:
  1. Pre-call grounding check  — LLM never called when evidence is insufficient.
  2. Strict system prompt      — forbids diagnosis, treatment, inference.
  3. temperature=0.0           — deterministic output for demo reliability.

All three must be present. See module docstring in retriever.py for the
retrieval contract this module depends on.

Safety rules:
  - Do NOT diagnose or recommend treatment.
  - Do NOT use medical knowledge beyond retrieved chunks.
  - Do NOT call the LLM when grounding check fails.
  - temperature=0.0 is hard — not configurable by callers.

Manual test (requires GROQ_API_KEY):
    PYTHONPATH=. clinical-rag-env/bin/python3 -m rag.answer_generator \\
        --patient-id PAT-MOD-001 \\
        --query "What medication is this patient taking?"
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Final

from rag.retriever import RetrievedChunk, retrieve, RetrieverError


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

RAG_NO_EVIDENCE_RESPONSE: Final[str] = (
    "The available synthetic records do not contain enough documented evidence "
    "to answer this question. No medical conclusions have been generated."
)

RAG_SYSTEM_PROMPT: Final[str] = (
    "You are a clinical record summarization assistant for an academic demonstration system.\n"
    "You answer questions about synthetic patient records using ONLY the retrieved evidence provided below.\n"
    "You must NOT use any medical knowledge beyond what is documented in the retrieved records.\n"
    "You must NOT diagnose, recommend treatment, prescribe medication, or predict disease.\n"
    "You must NOT infer conditions, medications, or lab values that are not explicitly stated in the records.\n"
    "If the retrieved records do not contain sufficient evidence to answer the question, say exactly:\n"
    "'The available records do not contain enough documented evidence to answer this question.'\n"
    "Every claim in your answer must be traceable to one of the retrieved record chunks provided.\n"
    "Keep your answer concise and factual. Do not speculate."
)

DEFAULT_GROQ_MODEL:         Final[str]          = "llama-3.3-70b-versatile"
DEFAULT_MAX_TOKENS:         Final[int]          = 512
DEFAULT_TEMPERATURE:        Final[float]        = 0.0
DEFAULT_TOP_K:              Final[int]          = 5
DEFAULT_DISTANCE_THRESHOLD: Final[float]        = 0.65
DEFAULT_MIN_CHUNKS:         Final[int]          = 1
MAX_RETRIES:                Final[int]          = 3
RETRY_DELAYS_SECONDS:       Final[tuple[int, ...]] = (2, 4, 8)
CITATION_EXCERPT_LENGTH:    Final[int]          = 150


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GroundingStatus:
    has_evidence:  bool
    usable_chunks: list[RetrievedChunk]
    reason:        str | None  # None when has_evidence=True


@dataclass
class Citation:
    chunk_id:    str
    patient_id:  str
    visit_id:    str | None
    visit_date:  str | None
    source_type: str
    visit_role:  str | None
    excerpt:     str   # first CITATION_EXCERPT_LENGTH chars of chunk.text


@dataclass
class RAGResponse:
    patient_id:    str
    query:         str
    answer:        str
    citations:     list[Citation]
    grounded:      bool
    chunks_used:   int
    model_name:    str
    timestamp_utc: str
    no_evidence:   bool   # True if grounding check failed; LLM was not called


class AnswerGeneratorError(RuntimeError):
    """Raised when answer generation cannot proceed safely."""


# ---------------------------------------------------------------------------
# Mock override hook — set in tests to bypass live Groq calls
# ---------------------------------------------------------------------------

_groq_call_override: Callable[[str, str], str] | None = None


# ---------------------------------------------------------------------------
# Component 1 — Grounding check
# ---------------------------------------------------------------------------

def check_grounding(
    chunks: list[RetrievedChunk],
    *,
    min_chunks: int = DEFAULT_MIN_CHUNKS,
    max_distance: float = DEFAULT_DISTANCE_THRESHOLD,
) -> GroundingStatus:
    """
    Filter chunks by distance threshold and assess evidence sufficiency.

    Returns GroundingStatus with has_evidence=False when the LLM must not be
    called, or has_evidence=True with usable_chunks populated.
    """
    if not chunks:
        return GroundingStatus(
            has_evidence=False,
            usable_chunks=[],
            reason="No chunks retrieved for this patient and query combination.",
        )

    usable = [c for c in chunks if c.distance <= max_distance]

    if not usable:
        closest = min(c.distance for c in chunks)
        return GroundingStatus(
            has_evidence=False,
            usable_chunks=[],
            reason=(
                f"Retrieved {len(chunks)} chunk(s) but all exceeded distance threshold "
                f"{max_distance:.2f}. Closest distance: {closest:.4f}."
            ),
        )

    if len(usable) < min_chunks:
        return GroundingStatus(
            has_evidence=False,
            usable_chunks=[],
            reason=(
                f"Only {len(usable)} chunk(s) passed distance threshold {max_distance:.2f} "
                f"(minimum required: {min_chunks})."
            ),
        )

    return GroundingStatus(has_evidence=True, usable_chunks=usable, reason=None)


# ---------------------------------------------------------------------------
# Component 2 — Prompt builder
# ---------------------------------------------------------------------------

def build_prompt(
    query: str,
    chunks: list[RetrievedChunk],
    patient_id: str,
) -> tuple[str, str]:
    """
    Return (system_prompt, user_message).

    User message follows the exact format specified in Step 18B — each chunk
    prefixed with a [Record N — ...] header, closing with the grounding
    instruction line.
    """
    record_lines: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        visit_date = chunk.visit_date or "patient-level record"
        visit_role = chunk.visit_role or "—"
        header = (
            f"[Record {i} — source_type: {chunk.source_type} | "
            f"visit_date: {visit_date} | visit_role: {visit_role}]"
        )
        record_lines.append(f"{header}\n{chunk.text}")

    records_block = "\n\n".join(record_lines)

    user_message = (
        f"Patient ID: {patient_id}\n"
        f"Question: {query}\n\n"
        f"Retrieved evidence from patient records ({len(chunks)} record(s)):\n\n"
        f"{records_block}\n\n"
        "Answer based ONLY on the retrieved records above. "
        "Do not use any knowledge not present in the records above:"
    )

    return RAG_SYSTEM_PROMPT, user_message


# ---------------------------------------------------------------------------
# Component 3 — Groq LLM client
# ---------------------------------------------------------------------------

def call_groq(
    system_prompt: str,
    user_message: str,
    *,
    model: str = DEFAULT_GROQ_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """
    Call the active LLM provider and return the response text.

    If _groq_call_override is set, calls that instead (test hook — Step 18B
    unit tests depend on this hook and continue to pass unchanged).

    Provider selection is controlled by environment variables:
      LLM_PROVIDER=groq    (default) — Groq llama-3.3-70b-versatile
      LLM_PROVIDER=gemini            — Google Gemini free-tier fallback
      LLM_FALLBACK_PROVIDER=gemini   — auto-fallback when primary fails

    No callers outside this function need to know which provider is active.
    """
    # Test mock override — preserved from Step 18B, unchanged
    if _groq_call_override is not None:
        return _groq_call_override(system_prompt, user_message)

    from rag.llm_providers.router import generate as _provider_generate
    from rag.llm_providers.base import LLMProviderError

    try:
        return _provider_generate(
            system_prompt,
            user_message,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except LLMProviderError as exc:
        raise AnswerGeneratorError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Component 4 — Citation formatter
# ---------------------------------------------------------------------------

def format_citations(
    chunks: list[RetrievedChunk],
    answer: str,                    # accepted for future use; not used in v1.7-lite
) -> list[Citation]:
    """
    Generate one Citation per chunk — citation completeness over precision.

    Every usable chunk that was included in the prompt receives a citation,
    regardless of whether the LLM explicitly referenced it.
    """
    citations: list[Citation] = []
    for chunk in chunks:
        excerpt = (chunk.text or "").strip()[:CITATION_EXCERPT_LENGTH]
        citations.append(Citation(
            chunk_id    = chunk.chunk_id,
            patient_id  = chunk.patient_id,
            visit_id    = chunk.visit_id,
            visit_date  = chunk.visit_date,
            source_type = chunk.source_type,
            visit_role  = chunk.visit_role,
            excerpt     = excerpt,
        ))
    return citations


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_answer(
    query: str,
    patient_id: str,
    *,
    source_type_hint: str | None = None,
    top_k: int = DEFAULT_TOP_K,
    distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD,
    min_chunks: int = DEFAULT_MIN_CHUNKS,
) -> RAGResponse:
    """
    Full RAG pipeline: retrieve → ground → prompt → LLM → cite → respond.

    patient_id filter is enforced in retriever.retrieve() via the ChromaDB
    where clause. The LLM is never called when grounding fails.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _no_evidence_response(reason: str = "") -> RAGResponse:
        return RAGResponse(
            patient_id    = patient_id,
            query         = query,
            answer        = RAG_NO_EVIDENCE_RESPONSE,
            citations     = [],
            grounded      = False,
            chunks_used   = 0,
            model_name    = DEFAULT_GROQ_MODEL,
            timestamp_utc = timestamp,
            no_evidence   = True,
        )

    try:
        # Step 1 — Retrieve (distance_threshold NOT applied here)
        chunks = retrieve(
            query,
            patient_id,
            source_type=source_type_hint,
            top_k=top_k,
            distance_threshold=None,  # applied in grounding check below
            use_routing=(source_type_hint is None),
        )

        # Step 2 — Grounding check
        grounding = check_grounding(
            chunks,
            min_chunks=min_chunks,
            max_distance=distance_threshold,
        )
        if not grounding.has_evidence:
            return _no_evidence_response(grounding.reason or "")

        # Step 3 — Build prompt from usable chunks
        system_prompt, user_message = build_prompt(
            query,
            grounding.usable_chunks,
            patient_id,
        )

        # Step 4 — Call LLM
        answer = call_groq(
            system_prompt,
            user_message,
            model=DEFAULT_GROQ_MODEL,
            temperature=DEFAULT_TEMPERATURE,
            max_tokens=DEFAULT_MAX_TOKENS,
        )

        # Step 5 — Format citations
        citations = format_citations(grounding.usable_chunks, answer)

        # Step 6 — Return grounded response
        return RAGResponse(
            patient_id    = patient_id,
            query         = query,
            answer        = answer,
            citations     = citations,
            grounded      = True,
            chunks_used   = len(grounding.usable_chunks),
            model_name    = DEFAULT_GROQ_MODEL,
            timestamp_utc = timestamp,
            no_evidence   = False,
        )

    except AnswerGeneratorError:
        raise
    except Exception as exc:
        raise AnswerGeneratorError(
            f"Answer generation failed for patient {patient_id!r}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    "AnswerGeneratorError",
    "Citation",
    "GroundingStatus",
    "RAGResponse",
    "RAG_NO_EVIDENCE_RESPONSE",
    "RAG_SYSTEM_PROMPT",
    "DEFAULT_GROQ_MODEL",
    "DEFAULT_TEMPERATURE",
    "DEFAULT_DISTANCE_THRESHOLD",
    "DEFAULT_MIN_CHUNKS",
    "DEFAULT_TOP_K",
    "CITATION_EXCERPT_LENGTH",
    "_groq_call_override",
    "check_grounding",
    "build_prompt",
    "call_groq",
    "format_citations",
    "generate_answer",
]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse, sys

    parser = argparse.ArgumentParser(description="Step 18B — Answer Generator CLI")
    parser.add_argument("--patient-id", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--source-type", default=None)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument(
        "--distance-threshold", type=float, default=DEFAULT_DISTANCE_THRESHOLD
    )
    args = parser.parse_args()

    try:
        resp = generate_answer(
            args.query,
            args.patient_id,
            source_type_hint=args.source_type,
            top_k=args.top_k,
            distance_threshold=args.distance_threshold,
        )
    except AnswerGeneratorError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\nPatient:    {resp.patient_id}")
    print(f"Grounded:   {resp.grounded}  |  No-evidence: {resp.no_evidence}")
    print(f"Chunks used:{resp.chunks_used}  |  Model: {resp.model_name}")
    print(f"\nAnswer:\n{resp.answer}")
    if resp.citations:
        print(f"\nCitations ({len(resp.citations)}):")
        for i, c in enumerate(resp.citations, 1):
            print(f"  [{i}] {c.chunk_id} | {c.source_type} | {c.visit_date or 'patient-level'}")
            print(f"       {c.excerpt[:80]!r}")
    sys.exit(0)
