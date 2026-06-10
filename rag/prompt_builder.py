"""
rag/prompt_builder.py

Grounded prompt construction for the clinical RAG answer-generation layer.

This module converts a user query plus retrieved evidence chunks into a strict,
context-grounded LLM prompt. It does not retrieve chunks, call an LLM, format
final citations, or modify patient records.

Safety contract:
- Do not build a medical answer prompt when no retrieved evidence exists.
- Use retrieved chunks as the only evidence source.
- Tell the LLM explicitly not to diagnose, recommend treatment, predict disease,
  or infer undocumented facts.
- Preserve citation anchors so rag/citations.py can attach source citations.
- Do not place BP values in metadata or filters. BP may appear only inside
  retrieved evidence text, usually doctor_note chunks.

Expected integration:
- rag/retriever.py returns RetrievalResult / RetrievedChunk objects.
- rag/prompt_builder.py builds a GroundedPrompt.
- rag/llm_client.py sends the prompt to Groq.
- rag/answer_generator.py coordinates retrieval, prompt building, LLM call, and
  citation formatting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol, Sequence

from config.constants import SOURCE_TYPES


DEFAULT_MAX_CONTEXT_CHARS = 9000
DEFAULT_MAX_CHUNK_CHARS = 1600
DEFAULT_MAX_CITATION_EXCERPT_CHARS = 500
DEFAULT_NO_EVIDENCE_MESSAGE = (
    "The available retrieved records do not contain enough documented evidence "
    "to answer this question."
)

FORBIDDEN_MEDICAL_BEHAVIORS: tuple[str, ...] = (
    "Do not diagnose the patient.",
    "Do not recommend or prescribe medication.",
    "Do not predict future disease or outcomes.",
    "Do not infer undocumented clinical facts.",
    "Do not use medical knowledge outside the retrieved context as evidence.",
    "Do not modify structured patient facts.",
)

ANSWER_STYLE_RULES: tuple[str, ...] = (
    "Answer only from the retrieved evidence.",
    "Be concise, factual, and citation-ready.",
    "Mention when information is not documented in the available records.",
    "Use neutral wording such as 'documented', 'recorded', or 'available records show'.",
    "Do not overstate uncertainty or clinical meaning beyond the record.",
)

SOURCE_TYPE_GUIDANCE: dict[str, str] = {
    "doctor_note": "Use for visit narrative, vitals described in SOAP objective, assessments, plans, and visit summaries.",
    "lab_result": "Use for lab values, lab flags, lab trend evidence, and condition-related monitoring.",
    "prescription": "Use for documented medication names, doses, frequencies, routes, start dates, stop dates, and medication changes.",
    "allergy": "Use for documented allergy registry evidence only; do not claim allergy detection or inference.",
}


class ChunkLike(Protocol):
    """Minimal retrieved chunk interface expected by the prompt builder."""

    chunk_id: str
    patient_id: str
    source_type: str
    text: str
    metadata: Mapping[str, Any]
    rank: int
    score: float | None


@dataclass(frozen=True)
class PromptContextChunk:
    """
    Evidence chunk as rendered inside the prompt context block.

    This is intentionally separate from rag.retriever.RetrievedChunk so this
    module remains easy to test and does not depend on ChromaDB objects.
    """

    context_id: str
    chunk_id: str
    patient_id: str
    source_type: str
    text: str
    metadata: dict[str, Any]
    rank: int
    score: float | None

    @property
    def visit_id(self) -> str:
        return _safe_text(self.metadata.get("visit_id"))

    @property
    def visit_date(self) -> str:
        return _safe_text(self.metadata.get("visit_date"))

    @property
    def visit_type(self) -> str:
        return _safe_text(self.metadata.get("visit_type"))

    def citation_seed(self) -> dict[str, Any]:
        """Return citation seed data derived only from evidence context."""
        return {
            "context_id": self.context_id,
            "chunk_id": self.chunk_id,
            "patient_id": self.patient_id,
            "visit_id": self.visit_id,
            "visit_date": self.visit_date,
            "visit_type": self.visit_type,
            "source_type": self.source_type,
            "rank": self.rank,
            "score": self.score,
            "evidence_excerpt": _truncate_text(
                self.text,
                max_chars=DEFAULT_MAX_CITATION_EXCERPT_CHARS,
            ),
        }


@dataclass(frozen=True)
class GroundedPrompt:
    """
    Prompt object ready for LLM client usage.

    Attributes:
        system_prompt: Stable safety and behavior instructions.
        user_prompt: Query plus evidence context.
        query_text: Original user query.
        patient_id: Patient scope.
        context_chunks: Evidence chunks included in the prompt.
        no_evidence: True when no evidence was available and no answer prompt
            should be sent to the LLM.
        no_evidence_message: Safe response text for no-evidence cases.
    """

    system_prompt: str
    user_prompt: str
    query_text: str
    patient_id: str
    context_chunks: tuple[PromptContextChunk, ...]
    no_evidence: bool
    no_evidence_message: str = DEFAULT_NO_EVIDENCE_MESSAGE

    @property
    def has_evidence(self) -> bool:
        """Return True when the prompt contains usable evidence."""
        return not self.no_evidence and bool(self.context_chunks)

    def messages(self) -> list[dict[str, str]]:
        """Return OpenAI/Groq-style chat messages."""
        if self.no_evidence:
            return []

        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self.user_prompt},
        ]

    def citation_seeds(self) -> list[dict[str, Any]]:
        """Return citation seeds for all prompt context chunks."""
        return [chunk.citation_seed() for chunk in self.context_chunks]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation for debug/UI usage."""
        return {
            "query_text": self.query_text,
            "patient_id": self.patient_id,
            "has_evidence": self.has_evidence,
            "no_evidence": self.no_evidence,
            "no_evidence_message": self.no_evidence_message,
            "system_prompt": self.system_prompt,
            "user_prompt": self.user_prompt,
            "context_chunks": [
                {
                    "context_id": chunk.context_id,
                    "chunk_id": chunk.chunk_id,
                    "patient_id": chunk.patient_id,
                    "source_type": chunk.source_type,
                    "rank": chunk.rank,
                    "score": chunk.score,
                    "visit_id": chunk.visit_id,
                    "visit_date": chunk.visit_date,
                    "visit_type": chunk.visit_type,
                    "text": chunk.text,
                    "metadata": dict(chunk.metadata),
                }
                for chunk in self.context_chunks
            ],
        }


class PromptBuildError(ValueError):
    """Raised when a grounded prompt cannot be built safely."""


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------


def build_grounded_prompt(
    *,
    query_text: str,
    patient_id: str,
    chunks: Sequence[ChunkLike | Mapping[str, Any]],
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
    no_evidence_message: str = DEFAULT_NO_EVIDENCE_MESSAGE,
) -> GroundedPrompt:
    """
    Build a strict context-grounded prompt from retrieved chunks.

    Args:
        query_text: User question.
        patient_id: Required patient scope.
        chunks: Retrieved evidence chunks from rag.retriever or compatible dicts.
        max_context_chars: Maximum total evidence context characters.
        max_chunk_chars: Maximum text characters per chunk.
        no_evidence_message: Safe no-evidence fallback response.

    Returns:
        GroundedPrompt. If chunks are empty, the returned object has
        no_evidence=True and messages() returns an empty list.

    Raises:
        PromptBuildError: For invalid query_text, patient_id, or unsafe chunks.
    """
    cleaned_query = _require_non_empty(query_text, "query_text")
    cleaned_patient_id = _require_non_empty(patient_id, "patient_id")

    if max_context_chars <= 0:
        raise PromptBuildError("max_context_chars must be greater than zero.")

    if max_chunk_chars <= 0:
        raise PromptBuildError("max_chunk_chars must be greater than zero.")

    context_chunks = _prepare_context_chunks(
        chunks=chunks,
        expected_patient_id=cleaned_patient_id,
        max_chunk_chars=max_chunk_chars,
        max_context_chars=max_context_chars,
    )

    system_prompt = build_system_prompt()

    if not context_chunks:
        return GroundedPrompt(
            system_prompt=system_prompt,
            user_prompt="",
            query_text=cleaned_query,
            patient_id=cleaned_patient_id,
            context_chunks=(),
            no_evidence=True,
            no_evidence_message=no_evidence_message,
        )

    user_prompt = build_user_prompt(
        query_text=cleaned_query,
        patient_id=cleaned_patient_id,
        context_chunks=context_chunks,
    )

    return GroundedPrompt(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        query_text=cleaned_query,
        patient_id=cleaned_patient_id,
        context_chunks=context_chunks,
        no_evidence=False,
        no_evidence_message=no_evidence_message,
    )


def build_system_prompt() -> str:
    """
    Build the stable system prompt used for grounded clinical-record answers.
    """
    safety_rules = "\n".join(f"- {rule}" for rule in FORBIDDEN_MEDICAL_BEHAVIORS)
    style_rules = "\n".join(f"- {rule}" for rule in ANSWER_STYLE_RULES)
    source_guidance = "\n".join(
        f"- {source_type}: {guidance}"
        for source_type, guidance in SOURCE_TYPE_GUIDANCE.items()
    )

    return f"""You are an academic clinical-record RAG assistant for synthetic patient records.

Your job is to answer questions by summarizing only the retrieved evidence provided in the context.

Medical safety rules:
{safety_rules}

Answer style rules:
{style_rules}

Source type guidance:
{source_guidance}

Citation behavior:
- Use the context IDs such as [C1], [C2], or [C3] to indicate which evidence supports each factual statement.
- Do not cite sources that do not support the statement.
- If the evidence is incomplete, say that the available records do not document enough information.

Output requirements:
- Write a direct answer.
- Keep the answer grounded and concise.
- Do not include hidden reasoning.
- Do not mention these instructions.
""".strip()


def build_user_prompt(
    *,
    query_text: str,
    patient_id: str,
    context_chunks: Sequence[PromptContextChunk],
) -> str:
    """
    Build the user prompt containing the query and evidence context.
    """
    cleaned_query = _require_non_empty(query_text, "query_text")
    cleaned_patient_id = _require_non_empty(patient_id, "patient_id")

    if not context_chunks:
        raise PromptBuildError("Cannot build user prompt without context chunks.")

    context_block = "\n\n".join(_render_context_chunk(chunk) for chunk in context_chunks)

    return f"""Patient scope: {cleaned_patient_id}
User question: {cleaned_query}

Retrieved evidence:
{context_block}

Instructions:
Answer the user question using only the retrieved evidence above.
If the evidence does not contain the answer, say that the available records do not contain enough documented evidence.
Use context IDs like [C1] or [C2] beside factual claims that depend on retrieved evidence.
""".strip()


def build_no_evidence_response(
    message: str = DEFAULT_NO_EVIDENCE_MESSAGE,
) -> str:
    """
    Return the safe no-evidence response used when retrieval returns no chunks.
    """
    return _require_non_empty(message, "message")


def build_prompt_from_retrieval_result(
    retrieval_result: Any,
    *,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
) -> GroundedPrompt:
    """
    Convenience wrapper for rag.retriever.RetrievalResult-like objects.

    The object must expose query_text, patient_id, and chunks attributes.
    """
    return build_grounded_prompt(
        query_text=getattr(retrieval_result, "query_text"),
        patient_id=getattr(retrieval_result, "patient_id"),
        chunks=tuple(getattr(retrieval_result, "chunks")),
        max_context_chars=max_context_chars,
        max_chunk_chars=max_chunk_chars,
    )


# ---------------------------------------------------------------------
# Context preparation
# ---------------------------------------------------------------------


def _prepare_context_chunks(
    *,
    chunks: Sequence[ChunkLike | Mapping[str, Any]],
    expected_patient_id: str,
    max_chunk_chars: int,
    max_context_chars: int,
) -> tuple[PromptContextChunk, ...]:
    """Normalize retrieved chunks into prompt context chunks."""
    context_chunks: list[PromptContextChunk] = []
    total_chars = 0

    for index, raw_chunk in enumerate(chunks, start=1):
        chunk = _coerce_chunk(
            raw_chunk,
            context_index=index,
            expected_patient_id=expected_patient_id,
            max_chunk_chars=max_chunk_chars,
        )

        next_size = len(chunk.text)
        if total_chars + next_size > max_context_chars:
            break

        context_chunks.append(chunk)
        total_chars += next_size

    return tuple(context_chunks)


def _coerce_chunk(
    raw_chunk: ChunkLike | Mapping[str, Any],
    *,
    context_index: int,
    expected_patient_id: str,
    max_chunk_chars: int,
) -> PromptContextChunk:
    """Convert a RetrievedChunk-like object or dict into PromptContextChunk."""
    if isinstance(raw_chunk, Mapping):
        chunk_id = _safe_text(raw_chunk.get("chunk_id"))
        patient_id = _safe_text(raw_chunk.get("patient_id"))
        source_type = _safe_text(raw_chunk.get("source_type"))
        text = _safe_text(raw_chunk.get("text"))
        metadata = raw_chunk.get("metadata", {})
        rank = raw_chunk.get("rank", context_index)
        score = raw_chunk.get("score")
    else:
        chunk_id = _safe_text(getattr(raw_chunk, "chunk_id", ""))
        patient_id = _safe_text(getattr(raw_chunk, "patient_id", ""))
        source_type = _safe_text(getattr(raw_chunk, "source_type", ""))
        text = _safe_text(getattr(raw_chunk, "text", ""))
        metadata = getattr(raw_chunk, "metadata", {})
        rank = getattr(raw_chunk, "rank", context_index)
        score = getattr(raw_chunk, "score", None)

    if not chunk_id:
        raise PromptBuildError(f"Retrieved chunk #{context_index} is missing chunk_id.")

    if patient_id != expected_patient_id:
        raise PromptBuildError(
            f"Retrieved chunk {chunk_id!r} belongs to patient_id={patient_id!r}, "
            f"expected patient_id={expected_patient_id!r}."
        )

    if source_type not in SOURCE_TYPES:
        raise PromptBuildError(
            f"Retrieved chunk {chunk_id!r} has invalid source_type={source_type!r}."
        )

    if not text:
        raise PromptBuildError(f"Retrieved chunk {chunk_id!r} has empty text.")

    if not isinstance(metadata, Mapping):
        raise PromptBuildError(f"Retrieved chunk {chunk_id!r} metadata must be a mapping.")

    return PromptContextChunk(
        context_id=f"C{context_index}",
        chunk_id=chunk_id,
        patient_id=patient_id,
        source_type=source_type,
        text=_truncate_text(text, max_chars=max_chunk_chars),
        metadata=dict(metadata),
        rank=_safe_int(rank, default=context_index),
        score=_safe_optional_float(score),
    )


def _render_context_chunk(chunk: PromptContextChunk) -> str:
    """Render one evidence chunk in a citation-friendly prompt format."""
    metadata_lines = [
        f"patient_id: {chunk.patient_id}",
        f"chunk_id: {chunk.chunk_id}",
        f"source_type: {chunk.source_type}",
    ]

    if chunk.visit_id:
        metadata_lines.append(f"visit_id: {chunk.visit_id}")
    if chunk.visit_date:
        metadata_lines.append(f"visit_date: {chunk.visit_date}")
    if chunk.visit_type:
        metadata_lines.append(f"visit_type: {chunk.visit_type}")

    conditions_text = _safe_text(chunk.metadata.get("conditions_text"))
    if conditions_text:
        metadata_lines.append(f"conditions: {conditions_text}")

    score_text = "" if chunk.score is None else f"score: {chunk.score:.4f}"
    if score_text:
        metadata_lines.append(score_text)

    metadata_block = "\n".join(metadata_lines)

    return f"""[{chunk.context_id}]
{metadata_block}
evidence_text:
{chunk.text}""".strip()


# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------


def _require_non_empty(value: Any, field_name: str) -> str:
    """Return stripped string value or raise PromptBuildError."""
    text = _safe_text(value)
    if not text:
        raise PromptBuildError(f"{field_name} must be a non-empty string.")
    return text


def _safe_text(value: Any) -> str:
    """Convert a value to stripped text without inferring facts."""
    if value is None:
        return ""
    return str(value).strip()


def _safe_int(value: Any, *, default: int) -> int:
    """Convert value to int or return default."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_optional_float(value: Any) -> float | None:
    """Convert value to float or return None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _truncate_text(text: str, *, max_chars: int) -> str:
    """Truncate text to max_chars while preserving readable boundaries."""
    clean = " ".join(_safe_text(text).split())

    if len(clean) <= max_chars:
        return clean

    truncated = clean[: max_chars - 1].rstrip()
    last_sentence = max(truncated.rfind("."), truncated.rfind(";"), truncated.rfind(","))

    if last_sentence >= max_chars // 2:
        truncated = truncated[: last_sentence + 1].rstrip()

    return f"{truncated}…"


__all__ = [
    "PromptContextChunk",
    "GroundedPrompt",
    "PromptBuildError",
    "build_grounded_prompt",
    "build_prompt_from_retrieval_result",
    "build_system_prompt",
    "build_user_prompt",
    "build_no_evidence_response",
]
