"""
rag/retriever.py  —  Step 18A

Patient-scoped ChromaDB retrieval for the clinical RAG pipeline.

Safety contract:
- patient_id filter is ALWAYS in the ChromaDB where clause (never post-hoc).
- source_type routing is a soft optimization — caller can override.
- distance scores are always returned for downstream grounding enforcement.
- No LLM calls, no writes to ChromaDB, no SOAP/chunk/metadata modification.

Run for manual testing:
    PYTHONPATH=. clinical-rag-env/bin/python3 -m rag.retriever \\
        --patient-id PAT-MOD-001 --query "What medications does this patient take?"
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.constants import EMBEDDING_MODEL_NAME
from config.paths import CHROMADB_DIR

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

COLLECTION_NAME    = "clinical_records_v17_lite"
MODEL_NAME         = EMBEDDING_MODEL_NAME          # "sentence-transformers/all-MiniLM-L6-v2"
CHROMA_PERSIST_DIR = CHROMADB_DIR

# ---------------------------------------------------------------------------
# Source-type routing rules  (checked in priority order — first match wins)
# ---------------------------------------------------------------------------

_ROUTING_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        ("allerg", "allergic", "reaction to", "sensitive to",
         "allergy history", "drug allergy", "known allergy"),
        "allergy",
    ),
    (
        ("lab result", "test result", "blood test", "laboratory",
         "hba1c", "creatinine", "hemoglobin", "ldl", "fbg", "ferritin",
         "kidney test", "renal test", "blood sugar level", "cholesterol level",
         "anemia test", "iron level"),
        "lab_result",
    ),
    (
        ("hospital", "admitted", "discharge", "inpatient",
         "hospitali", "ward", "after leaving hospital"),
        "discharge_summary",
    ),
    (
        ("medication", "prescribed", "prescription", "taking", "drug",
         "dose", "tablet", "medicine", "started taking", "added",
         "course completed", "antibiotic", "inhaler"),
        "prescription",
    ),
]

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class RetrievedChunk:
    """One retrieved chunk with metadata and distance score."""
    chunk_id:    str
    text:        str
    metadata:    dict[str, Any]
    distance:    float
    patient_id:  str
    source_type: str
    visit_id:    str | None
    visit_date:  str | None
    visit_role:  str | None


@dataclass
class RetrievalResult:
    """Complete result of one retrieval call."""
    query:                str
    patient_id:           str
    source_type_hint:     str | None
    chunks:               list[RetrievedChunk]
    total_retrieved:      int
    filtered_by_distance: int   # chunks dropped by distance threshold
    model_name:           str


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------

class RetrieverError(RuntimeError):
    """Raised when retrieval cannot proceed safely."""


# ---------------------------------------------------------------------------
# Lazy singletons — model and collection
# ---------------------------------------------------------------------------

_model = None


def _get_model():
    """Lazy-load SentenceTransformer once per process."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _get_collection(
    persist_dir: Path = CHROMA_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
):
    """Return a ChromaDB collection handle (lazy — not called at import time)."""
    import chromadb
    if not persist_dir.exists():
        raise RetrieverError(
            f"ChromaDB directory not found: {persist_dir}. "
            "Run ingestion before retrieval."
        )
    client = chromadb.PersistentClient(path=str(persist_dir))
    try:
        return client.get_collection(name=collection_name)
    except Exception as exc:
        raise RetrieverError(
            f"Cannot open collection {collection_name!r}. "
            "Run ingestion first."
        ) from exc


# ---------------------------------------------------------------------------
# Routing inference
# ---------------------------------------------------------------------------

def infer_source_type_hint(query: str) -> str | None:
    """
    Return a source_type hint based on query keywords, or None if no match.

    Checks _ROUTING_RULES in priority order — first match wins.
    """
    normalized = query.lower()
    for keywords, source_type in _ROUTING_RULES:
        if any(kw in normalized for kw in keywords):
            return source_type
    return None


# ---------------------------------------------------------------------------
# Where-clause construction
# ---------------------------------------------------------------------------

def _build_where_clause(
    patient_id: str,
    source_type: str | None,
) -> dict:
    """
    Build a ChromaDB where clause.

    Always includes patient_id. Adds source_type as second filter if provided.
    """
    if source_type is not None:
        return {
            "$and": [
                {"patient_id": {"$eq": patient_id}},
                {"source_type": {"$eq": source_type}},
            ]
        }
    return {"patient_id": {"$eq": patient_id}}


# ---------------------------------------------------------------------------
# Raw retrieval helper
# ---------------------------------------------------------------------------

def _query_collection(
    collection,
    query: str,
    where: dict,
    top_k: int,
) -> list[dict]:
    """Embed query and retrieve top_k chunks from ChromaDB."""
    model = _get_model()
    embedding = model.encode(query, normalize_embeddings=True)
    total = collection.count()
    n = min(top_k, max(total, 1))

    raw = collection.query(
        query_embeddings=[embedding.tolist()],
        n_results=n,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    results = []
    for i in range(len(raw["ids"][0])):
        meta = raw["metadatas"][0][i] or {}
        # Normalize "" → None for allergy chunks (no visit)
        visit_id   = meta.get("visit_id") or None
        visit_date = meta.get("visit_date") or None
        visit_role = meta.get("visit_role") or None
        if isinstance(visit_id, str) and visit_id.strip() == "":
            visit_id = None
        if isinstance(visit_date, str) and visit_date.strip() == "":
            visit_date = None
        if isinstance(visit_role, str) and visit_role.strip() == "":
            visit_role = None

        results.append(RetrievedChunk(
            chunk_id    = raw["ids"][0][i],
            text        = raw["documents"][0][i],
            metadata    = dict(meta),
            distance    = float(raw["distances"][0][i]),
            patient_id  = str(meta.get("patient_id", "")),
            source_type = str(meta.get("source_type", "")),
            visit_id    = visit_id,
            visit_date  = visit_date,
            visit_role  = visit_role,
        ))
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def retrieve(
    query: str,
    patient_id: str,
    *,
    source_type: str | None = None,
    top_k: int = 5,
    distance_threshold: float | None = None,
    use_routing: bool = True,
    persist_dir: Path = CHROMA_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
) -> list[RetrievedChunk]:
    """
    Primary retrieval function.

    patient_id filter is always enforced in the ChromaDB where clause.
    source_type routing fires when source_type=None and use_routing=True.
    """
    if not query or not query.strip():
        raise RetrieverError("query must be a non-empty string.")
    if not patient_id or not patient_id.strip():
        raise RetrieverError("patient_id is required.")

    # Determine effective source_type
    effective_st = source_type
    if effective_st is None and use_routing:
        effective_st = infer_source_type_hint(query)

    where = _build_where_clause(patient_id, effective_st)
    collection = _get_collection(persist_dir, collection_name)

    try:
        chunks = _query_collection(collection, query, where, top_k)
    except Exception as exc:
        # Empty patient returns zero results — not an error
        if "no results" in str(exc).lower() or chunks is None:
            return []
        raise RetrieverError(f"Retrieval failed: {exc}") from exc

    # Distance threshold filter
    if distance_threshold is not None:
        chunks = [c for c in chunks if c.distance <= distance_threshold]

    return chunks


def retrieve_by_source_type(
    query: str,
    patient_id: str,
    source_type: str,
    *,
    top_k: int = 3,
    distance_threshold: float | None = None,
    persist_dir: Path = CHROMA_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
) -> list[RetrievedChunk]:
    """Retrieve with explicit source_type — bypasses routing entirely."""
    return retrieve(
        query,
        patient_id,
        source_type=source_type,
        top_k=top_k,
        distance_threshold=distance_threshold,
        use_routing=False,
        persist_dir=persist_dir,
        collection_name=collection_name,
    )


def get_patient_chunk_count(
    patient_id: str,
    persist_dir: Path = CHROMA_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
) -> int:
    """Return total chunk count for patient across all source_types."""
    collection = _get_collection(persist_dir, collection_name)
    raw = collection.get(
        where={"patient_id": {"$eq": patient_id}},
        include=[],
    )
    return len(raw.get("ids", []))


def get_patient_source_types(
    patient_id: str,
    persist_dir: Path = CHROMA_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
) -> set[str]:
    """Return the set of source_types present for the patient."""
    collection = _get_collection(persist_dir, collection_name)
    raw = collection.get(
        where={"patient_id": {"$eq": patient_id}},
        include=["metadatas"],
    )
    return {
        str(m.get("source_type", ""))
        for m in (raw.get("metadatas") or [])
        if m.get("source_type")
    }


def retrieve_with_metadata(
    query: str,
    patient_id: str,
    *,
    source_type: str | None = None,
    top_k: int = 5,
    distance_threshold: float | None = None,
    use_routing: bool = True,
    persist_dir: Path = CHROMA_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
) -> RetrievalResult:
    """
    Same as retrieve() but returns RetrievalResult with full diagnostic metadata.
    Used by diagnostics and the answer generator for logging.
    """
    effective_st = source_type
    if effective_st is None and use_routing:
        effective_st = infer_source_type_hint(query)

    where = _build_where_clause(patient_id, effective_st)
    collection = _get_collection(persist_dir, collection_name)
    raw_chunks = _query_collection(collection, query, where, top_k)
    total_retrieved = len(raw_chunks)

    filtered = raw_chunks
    if distance_threshold is not None:
        filtered = [c for c in raw_chunks if c.distance <= distance_threshold]
    filtered_count = total_retrieved - len(filtered)

    return RetrievalResult(
        query                = query,
        patient_id           = patient_id,
        source_type_hint     = effective_st,
        chunks               = filtered,
        total_retrieved      = total_retrieved,
        filtered_by_distance = filtered_count,
        model_name           = MODEL_NAME,
    )


# ---------------------------------------------------------------------------
# Backward-compatible aliases (used by answer_generator / prompt_builder)
# ---------------------------------------------------------------------------

def retrieve_patient_chunks(
    *,
    query_text: str,
    patient_id: str,
    source_types: tuple[str, ...] | None = None,
    top_k: int = 5,
    **_kwargs,
) -> list[RetrievedChunk]:
    """
    Legacy alias kept for backward compatibility with answer_generator.py.
    Wraps retrieve() / retrieve_by_source_type().
    """
    st = source_types[0] if source_types and len(source_types) == 1 else None
    return retrieve(
        query_text,
        patient_id,
        source_type=st,
        top_k=top_k,
        use_routing=(st is None),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Step 18A — Retriever CLI")
    p.add_argument("--patient-id", required=True)
    p.add_argument("--query", required=True)
    p.add_argument("--source-type", default=None)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--distance-threshold", type=float, default=None)
    p.add_argument("--no-routing", action="store_true")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    try:
        result = retrieve_with_metadata(
            args.query,
            args.patient_id,
            source_type=args.source_type,
            top_k=args.top_k,
            distance_threshold=args.distance_threshold,
            use_routing=not args.no_routing,
        )
    except RetrieverError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"\nQuery:           {result.query}")
    print(f"Patient:         {result.patient_id}")
    print(f"Source hint:     {result.source_type_hint or 'none (all types)'}")
    print(f"Retrieved:       {result.total_retrieved}")
    print(f"After threshold: {len(result.chunks)}")
    print(f"Dropped:         {result.filtered_by_distance}")
    for i, c in enumerate(result.chunks, 1):
        print(f"\n[{i}] {c.chunk_id}  dist={c.distance:.4f}")
        print(f"     source_type={c.source_type}  visit_role={c.visit_role}")
        print(f"     {c.text[:200]!r}")
    return 0


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    "RetrieverError",
    "RetrievedChunk",
    "RetrievalResult",
    "COLLECTION_NAME",
    "MODEL_NAME",
    "CHROMA_PERSIST_DIR",
    "infer_source_type_hint",
    "retrieve",
    "retrieve_by_source_type",
    "retrieve_with_metadata",
    "get_patient_chunk_count",
    "get_patient_source_types",
    "retrieve_patient_chunks",
]


if __name__ == "__main__":
    raise SystemExit(main())
