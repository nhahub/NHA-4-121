"""
ingestion/ingest.py  —  Step 15

ChromaDB ingestion pipeline for validated synthetic clinical records.

Design contract
---------------
* Accepts pre-built chunk dicts and pre-validated metadata dicts from Steps 13–14.
* Does NOT call any LLM.
* Does NOT call the chunker or metadata builder — those are caller responsibilities.
* Does NOT modify patient records.
* Does NOT write to ChromaDB unless all pre-ingestion checks pass.
* Embeddings use sentence-transformers/all-MiniLM-L6-v2 with normalize_embeddings=True.
* Collection uses cosine distance (hnsw:space = cosine).
* Patient-scoped retrieval is enforced by default in all query helpers.
* clean=True performs atomic collection reset before any upsert.
* Post-ingestion count verification is mandatory — not optional.

Public API
----------
ingest_chunks(chunks, metadata_list, ...)          -> IngestionResult
reset_collection(...)                              -> None
query_patient_chunks(query_text, patient_id, ...)  -> list[dict]
get_all_patient_chunks(patient_id, ...)            -> list[dict]
IngestionError
IngestionResult
_validate_ingestion_inputs(chunks, metadata_list)  -> None  (public for testing)
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.constants import EMBEDDING_MODEL_NAME
from config.paths import CHROMADB_DIR

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

COLLECTION_NAME: str = "clinical_records_v17_lite"
CHROMA_PERSIST_DIR: Path = CHROMADB_DIR
BATCH_SIZE: int = 50

# Forbidden metadata keys checked case-insensitively in pre-ingestion gate.
# Mirrors the set in metadata_builder.py — kept separate so ingest.py can
# be imported without requiring metadata_builder in every test.
_FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "bp", "blood_pressure", "bp_systolic", "bp_diastolic",
    "systolic", "diastolic", "sbp", "dbp",
    "lab_value", "lab_numeric_value",
    "full_soap_text", "retrieval_signature", "safe_distractor_text",
    "age", "date_of_birth", "name", "sex",
})

_SCALAR_TYPES = (str, int, float, bool)


# ---------------------------------------------------------------------------
# Public exception and result dataclass
# ---------------------------------------------------------------------------

class IngestionError(RuntimeError):
    """Raised when ingestion cannot complete safely."""


@dataclass
class IngestionResult:
    """Summary of one completed ingestion run."""
    collection_name:  str
    chunks_ingested:  int
    chunks_by_type:   dict[str, int]
    patients_covered: int
    persist_dir:      Path
    model_name:       str
    collection_count: int   # verified count after ingestion
    clean_run:        bool
    timestamp_utc:    str


# ---------------------------------------------------------------------------
# Public API — primary ingestion entry point
# ---------------------------------------------------------------------------

def ingest_chunks(
    chunks: list[dict],
    metadata_list: list[dict],
    *,
    persist_dir: Path = CHROMA_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
    clean: bool = False,
    batch_size: int = BATCH_SIZE,
    show_progress: bool = True,
) -> IngestionResult:
    """
    Embed all chunk texts and upsert into a local persistent ChromaDB collection.

    Parameters
    ----------
    chunks        : List of chunk dicts produced by ingestion/chunker.py.
    metadata_list : Corresponding validated metadata dicts from metadata_builder.py.
                    Must be in the same order and same length as chunks.
    persist_dir   : ChromaDB persistence directory (default: data/chromadb/).
    collection_name : Target collection name.
    clean         : If True, drop and recreate the collection before upserting.
                    Recommended for all production ingestion runs.
    batch_size    : Chunks per upsert call (default: 50).
    show_progress : Display sentence-transformers progress bar while encoding.

    Returns
    -------
    IngestionResult describing counts and verification outcome.

    Raises
    ------
    IngestionError on any pre-ingestion check failure or post-ingestion count mismatch.
    """
    # --- Pre-ingestion validation gate (non-negotiable) ---
    _validate_ingestion_inputs(chunks, metadata_list)

    # --- Import dependencies ---
    chromadb_mod = _import_chromadb()
    SentenceTransformer = _import_sentence_transformers()

    # --- Connect to ChromaDB ---
    persist_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb_mod.PersistentClient(path=str(persist_dir))

    # --- Optionally reset collection ---
    if clean:
        _delete_collection_if_exists(client, collection_name)

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    # --- Embed chunk texts ---
    if show_progress:
        print(f"Embedding {len(chunks)} chunks with {EMBEDDING_MODEL_NAME} …")

    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    texts = [c["text"] for c in chunks]
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=batch_size,
        show_progress_bar=show_progress,
    )

    # --- Batch upsert ---
    for start in range(0, len(chunks), batch_size):
        end = min(start + batch_size, len(chunks))
        _upsert_batch(collection, chunks, metadata_list, embeddings, start, end)

    # --- Post-ingestion count verification ---
    actual_count = collection.count()
    if actual_count < len(chunks):
        # With upsert, count can be >= len(chunks) if prior stale chunks exist.
        # A count less than chunks means something was silently dropped.
        raise IngestionError(
            f"Post-ingestion count mismatch: upserted {len(chunks)} chunks but "
            f"collection.count() = {actual_count}. "
            f"Use clean=True to reset before ingesting."
        )

    # --- Build result ---
    chunks_by_type: dict[str, int] = {}
    patient_ids: set[str] = set()
    for c in chunks:
        st = c.get("source_type", "unknown")
        chunks_by_type[st] = chunks_by_type.get(st, 0) + 1
        pid = c.get("patient_id", "")
        if pid:
            patient_ids.add(pid)

    return IngestionResult(
        collection_name=collection_name,
        chunks_ingested=len(chunks),
        chunks_by_type=chunks_by_type,
        patients_covered=len(patient_ids),
        persist_dir=persist_dir,
        model_name=EMBEDDING_MODEL_NAME,
        collection_count=actual_count,
        clean_run=clean,
        timestamp_utc=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


# ---------------------------------------------------------------------------
# Public API — collection reset
# ---------------------------------------------------------------------------

def reset_collection(
    *,
    persist_dir: Path = CHROMA_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
) -> None:
    """
    Drop and recreate the named ChromaDB collection.

    Used by scripts/reset_chromadb.py and by ingest_chunks(clean=True).
    After reset, the collection exists but contains zero chunks.
    """
    chromadb_mod = _import_chromadb()
    persist_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb_mod.PersistentClient(path=str(persist_dir))
    _delete_collection_if_exists(client, collection_name)
    client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# Public API — patient-scoped query helper
# ---------------------------------------------------------------------------

def query_patient_chunks(
    query_text: str,
    patient_id: str,
    *,
    persist_dir: Path = CHROMA_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
    source_type: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    """
    Embed query_text and retrieve the top-k most similar chunks for patient_id.

    Patient-scoped filter is always applied — this is non-negotiable. Results
    will only contain chunks where metadata["patient_id"] == patient_id.

    Parameters
    ----------
    query_text    : Natural language query string.
    patient_id    : Patient ID to restrict results to (e.g. "PAT-CHR-005").
    persist_dir   : ChromaDB persistence directory.
    collection_name : Collection to query.
    source_type   : Optional additional filter on metadata["source_type"].
    top_k         : Maximum number of results to return.

    Returns
    -------
    List of result dicts, each containing:
        {"chunk_id": str, "text": str, "metadata": dict, "distance": float}
    Empty list if no results match.
    """
    chromadb_mod = _import_chromadb()
    SentenceTransformer = _import_sentence_transformers()

    client = chromadb_mod.PersistentClient(path=str(persist_dir))
    collection = client.get_collection(name=collection_name)

    # Build where filter
    if source_type is not None:
        where: dict[str, Any] = {
            "$and": [
                {"patient_id": {"$eq": patient_id}},
                {"source_type": {"$eq": source_type}},
            ]
        }
    else:
        where = {"patient_id": {"$eq": patient_id}}

    # Embed the query text
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    qemb = model.encode([query_text], normalize_embeddings=True).tolist()

    # Clamp n_results to available count to avoid ChromaDB errors
    total = collection.count()
    n_results = min(top_k, max(total, 1))

    raw = collection.query(
        query_embeddings=qemb,
        n_results=n_results,
        where=where,
        include=["metadatas", "documents", "distances"],
    )

    results: list[dict] = []
    ids_list      = raw.get("ids", [[]])[0]
    docs_list     = raw.get("documents", [[]])[0]
    metas_list    = raw.get("metadatas", [[]])[0]
    dists_list    = raw.get("distances", [[]])[0]

    for chunk_id, doc, meta, dist in zip(ids_list, docs_list, metas_list, dists_list):
        results.append({
            "chunk_id": chunk_id,
            "text":     doc,
            "metadata": meta,
            "distance": dist,
        })

    return results


# ---------------------------------------------------------------------------
# Public API — get all chunks for a patient
# ---------------------------------------------------------------------------

def get_all_patient_chunks(
    patient_id: str,
    *,
    persist_dir: Path = CHROMA_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
) -> list[dict]:
    """
    Return all stored chunks for a patient, regardless of source_type.

    Uses ChromaDB get() (no embedding needed) — faster than query().
    Used by the PAT-CHR-005 smoke test and retrieval challenge tests.

    Returns
    -------
    List of result dicts:
        {"chunk_id": str, "text": str, "metadata": dict}
    """
    chromadb_mod = _import_chromadb()
    client = chromadb_mod.PersistentClient(path=str(persist_dir))
    collection = client.get_collection(name=collection_name)

    raw = collection.get(
        where={"patient_id": {"$eq": patient_id}},
        include=["metadatas", "documents"],
    )

    results: list[dict] = []
    ids_list   = raw.get("ids", [])
    docs_list  = raw.get("documents", [])
    metas_list = raw.get("metadatas", [])

    for chunk_id, doc, meta in zip(ids_list, docs_list, metas_list):
        results.append({
            "chunk_id": chunk_id,
            "text":     doc,
            "metadata": meta,
        })

    return results


# ---------------------------------------------------------------------------
# Public API — pre-ingestion validation gate (also public for testing)
# ---------------------------------------------------------------------------

def _validate_ingestion_inputs(
    chunks: list[dict],
    metadata_list: list[dict],
) -> None:
    """
    Hard-gate validation. Raises IngestionError on first failure.

    Checks (in order):
      1.  chunks and metadata_list have the same length.
      2.  Every chunk has chunk_id, text, patient_id, source_type.
      3.  Every chunk text is non-empty.
      4.  Every chunk text first sentence contains patient_id (retrieval anchor).
      5.  No metadata dict contains a forbidden key (BP, demographics).
      6.  All metadata values are scalar types (str, int, float, bool) — no lists, no None.
      7.  Chunk IDs are unique within the input set.
    """
    # Check 1 — equal length
    if len(chunks) != len(metadata_list):
        raise IngestionError(
            f"Length mismatch: {len(chunks)} chunks but {len(metadata_list)} "
            f"metadata dicts. They must be in the same order and same length."
        )

    seen_ids: set[str] = set()

    for idx, (chunk, meta) in enumerate(zip(chunks, metadata_list)):
        chunk_id    = chunk.get("chunk_id", "")
        text        = chunk.get("text", "")
        patient_id  = chunk.get("patient_id", "")
        source_type = chunk.get("source_type", "")

        # Check 2 — required chunk fields
        for field, val in [("chunk_id", chunk_id), ("text", text),
                            ("patient_id", patient_id), ("source_type", source_type)]:
            if not val or not str(val).strip():
                raise IngestionError(
                    f"Chunk[{idx}]: required field {field!r} is missing or empty."
                )

        # Check 3 — text non-empty (redundant with above but explicit)
        if not text.strip():
            raise IngestionError(
                f"Chunk {chunk_id!r} (index {idx}): text is empty."
            )

        # Check 4 — retrieval anchor: first sentence must contain patient_id
        first_sentence = text.split(".")[0]
        if patient_id not in first_sentence:
            raise IngestionError(
                f"Chunk {chunk_id!r} (index {idx}): retrieval anchor enforcement FAIL — "
                f"first sentence does not contain patient_id {patient_id!r}. "
                f"First sentence: {first_sentence!r}"
            )

        # Check 5 — no forbidden metadata keys
        for key in meta:
            if key.lower() in _FORBIDDEN_KEYS:
                raise IngestionError(
                    f"Chunk {chunk_id!r} (index {idx}): forbidden metadata key "
                    f"{key!r} detected. BP and demographic fields must never be "
                    f"stored in ChromaDB metadata."
                )

        # Check 6 — scalar metadata values only (no lists, no None, no dicts)
        for key, val in meta.items():
            if val is None:
                raise IngestionError(
                    f"Chunk {chunk_id!r} (index {idx}): metadata key {key!r} "
                    f"has value None. Use empty string \"\" for absent fields."
                )
            if not isinstance(val, _SCALAR_TYPES):
                raise IngestionError(
                    f"Chunk {chunk_id!r} (index {idx}): metadata key {key!r} "
                    f"has non-scalar value of type {type(val).__name__}. "
                    f"Only str, int, float, bool are accepted by ChromaDB."
                )

        # Check 7 — unique chunk IDs
        if chunk_id in seen_ids:
            raise IngestionError(
                f"Duplicate chunk_id {chunk_id!r} at index {idx}. "
                f"All chunk IDs must be unique within the ingestion batch."
            )
        seen_ids.add(chunk_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _upsert_batch(
    collection: Any,
    chunks: list[dict],
    metadata_list: list[dict],
    embeddings: Any,
    start_idx: int,
    end_idx: int,
) -> None:
    """Upsert one batch slice into the ChromaDB collection."""
    collection.upsert(
        ids=[c["chunk_id"] for c in chunks[start_idx:end_idx]],
        embeddings=embeddings[start_idx:end_idx].tolist(),
        documents=[c["text"] for c in chunks[start_idx:end_idx]],
        metadatas=metadata_list[start_idx:end_idx],
    )


def _delete_collection_if_exists(client: Any, collection_name: str) -> None:
    """Drop a collection if it exists; ignore not-found errors."""
    try:
        client.delete_collection(name=collection_name)
    except Exception:
        # ChromaDB raises different exception types across versions for
        # not-found. For reset/clean mode, not-found is acceptable.
        pass


def _import_chromadb() -> Any:
    """Import chromadb with a clear installation error."""
    try:
        import chromadb  # type: ignore
        return chromadb
    except ImportError as exc:
        raise IngestionError(
            "chromadb is not installed. Install project requirements: "
            "pip install chromadb"
        ) from exc


def _import_sentence_transformers() -> Any:
    """Import SentenceTransformer with a clear installation error."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        return SentenceTransformer
    except ImportError as exc:
        raise IngestionError(
            "sentence-transformers is not installed. Install project requirements: "
            "pip install sentence-transformers"
        ) from exc


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    "COLLECTION_NAME",
    "CHROMA_PERSIST_DIR",
    "BATCH_SIZE",
    "IngestionError",
    "IngestionResult",
    "ingest_chunks",
    "reset_collection",
    "query_patient_chunks",
    "get_all_patient_chunks",
    "_validate_ingestion_inputs",
]
