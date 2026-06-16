"""
backend/app/services.py  —  Step 19

Service layer — calls RAG and data modules, translates outputs into
backend response schemas. Error handling lives here; routes stay thin.

Rules:
  - Never query ChromaDB directly (use rag.retriever).
  - Never call Groq directly (use rag.answer_generator).
  - Never run validation business logic (that lives in validators/).
  - OFFLINE_MODE=true bypasses Groq but still retrieves from ChromaDB.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from config.constants import DATASET_VERSION
from config.paths import PATIENTS_DIR
from rag.answer_generator import (
    AnswerGeneratorError,
    RAG_NO_EVIDENCE_RESPONSE,
    format_citations,
    generate_answer,
)
from rag.retriever import get_patient_chunk_count, retrieve

from .schemas import (
    CitationResponse,
    HealthResponse,
    PatientSummary,
    PatientsResponse,
    QueryRequest,
    QueryResponse,
    TimelineResponse,
    VisitSummary,
)

# ---------------------------------------------------------------------------
# Offline mode constants
# ---------------------------------------------------------------------------

OFFLINE_ANSWER = (
    "OFFLINE MODE: This response is a cached demonstration answer. "
    "Live Groq answer generation is disabled. "
    "The system retrieved {n} chunk(s) from ChromaDB for this query."
)


def _is_offline() -> bool:
    return os.environ.get("OFFLINE_MODE", "false").lower() == "true"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Query service
# ---------------------------------------------------------------------------

def run_query(request: QueryRequest) -> QueryResponse:
    """
    Run a grounded RAG query for one patient.

    In OFFLINE_MODE: retrieves chunks from ChromaDB but skips the Groq call.
    In live mode: calls generate_answer() which handles grounding + LLM.
    """
    if _is_offline():
        # Retrieve chunks but bypass LLM
        chunks = retrieve(
            request.question,
            request.patient_id,
            source_type=request.source_type_hint,
            top_k=request.top_k,
            distance_threshold=None,
            use_routing=(request.source_type_hint is None),
        )
        answer = OFFLINE_ANSWER.format(n=len(chunks))
        citations = [
            CitationResponse(
                chunk_id    = c.chunk_id,
                patient_id  = c.patient_id,
                visit_id    = c.visit_id,
                visit_date  = c.visit_date,
                source_type = c.source_type,
                visit_role  = c.visit_role,
                excerpt     = (c.text or "").strip()[:150],
            )
            for c in chunks
        ]
        return QueryResponse(
            patient_id    = request.patient_id,
            question      = request.question,
            answer        = answer,
            citations     = citations,
            grounded      = False,
            chunks_used   = len(chunks),
            no_evidence   = False,
            model_name    = "offline",
            timestamp_utc = _utc_now(),
        )

    # Live mode
    try:
        rag_resp = generate_answer(
            request.question,
            request.patient_id,
            source_type_hint=request.source_type_hint,
            top_k=request.top_k,
        )
    except AnswerGeneratorError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    citations = [
        CitationResponse(
            chunk_id    = c.chunk_id,
            patient_id  = c.patient_id,
            visit_id    = c.visit_id,
            visit_date  = c.visit_date,
            source_type = c.source_type,
            visit_role  = c.visit_role,
            excerpt     = c.excerpt,
        )
        for c in rag_resp.citations
    ]

    return QueryResponse(
        patient_id    = rag_resp.patient_id,
        question      = request.question,
        answer        = rag_resp.answer,
        citations     = citations,
        grounded      = rag_resp.grounded,
        chunks_used   = rag_resp.chunks_used,
        no_evidence   = rag_resp.no_evidence,
        model_name    = rag_resp.model_name,
        timestamp_utc = rag_resp.timestamp_utc,
    )


# ---------------------------------------------------------------------------
# Timeline service
# ---------------------------------------------------------------------------

def _load_patient_json(patient_id: str) -> dict:
    path = PATIENTS_DIR / f"{patient_id}.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Patient {patient_id} not found.",
        )
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def get_patient_timeline(patient_id: str) -> TimelineResponse:
    """
    Reconstruct chronological visit history from patient JSON visits[].
    Never reads from timeline_events — that field does not exist in v1.7-lite.
    """
    patient = _load_patient_json(patient_id)
    visits_raw = patient.get("visits", [])

    visits: list[VisitSummary] = []
    for v in visits_raw:
        ce = v.get("clinical_event") or {}
        visits.append(VisitSummary(
            visit_id             = v.get("visit_id", ""),
            visit_date           = v.get("visit_date", ""),
            visit_type           = v.get("visit_type", ""),
            visit_role           = v.get("visit_role", ""),
            diagnoses            = v.get("diagnoses") or [],
            has_labs             = len(v.get("labs") or []) > 0,
            has_medications      = len(v.get("medications") or []) > 0,
            clinical_event_label = ce.get("event_label", ""),
        ))

    return TimelineResponse(
        patient_id   = patient_id,
        total_visits = len(visits),
        visits       = visits,
    )


# ---------------------------------------------------------------------------
# Patients list service
# ---------------------------------------------------------------------------

def get_patients() -> PatientsResponse:
    """Return summary metadata for all 15 patients sorted by patient_id."""
    patient_files = sorted(PATIENTS_DIR.glob("PAT-*.json"))
    summaries: list[PatientSummary] = []

    for path in patient_files:
        try:
            with path.open(encoding="utf-8") as fh:
                p = json.load(fh)
        except Exception:
            continue

        meta = p.get("metadata") or {}
        summaries.append(PatientSummary(
            patient_id       = p.get("patient_id", path.stem),
            conditions       = p.get("conditions") or [],
            tier             = meta.get("tier", ""),
            total_visits     = len(p.get("visits") or []),
            has_allergy      = len(p.get("allergy_registry") or []) > 0,
            semantic_focus   = meta.get("semantic_focus", ""),
            timeline_pattern = meta.get("timeline_pattern", ""),
        ))

    return PatientsResponse(total=len(summaries), patients=summaries)


# ---------------------------------------------------------------------------
# Health service
# ---------------------------------------------------------------------------

def get_health() -> HealthResponse:
    """
    Check ChromaDB availability and return system health.
    Never returns 5xx — degraded state is reported in the response body.
    """
    chromadb_status = "unavailable"
    chunk_count = 0

    try:
        chunk_count = get_patient_chunk_count("PAT-MOD-001")
        # get_patient_chunk_count hitting ChromaDB without error means it's up
        # We need total count — use a rough heuristic: sum across known patients
        # The simplest correct approach is to use the collection directly
        from rag.retriever import _get_collection
        col = _get_collection()
        chunk_count = col.count()
        chromadb_status = "available"
    except Exception:
        chromadb_status = "unavailable"
        chunk_count = 0

    return HealthResponse(
        status          = "ok" if chromadb_status == "available" else "degraded",
        chromadb        = chromadb_status,
        chunk_count     = chunk_count,
        offline_mode    = _is_offline(),
        dataset_version = DATASET_VERSION,
        timestamp_utc   = _utc_now(),
    )


__all__ = [
    "run_query",
    "get_patient_timeline",
    "get_patients",
    "get_health",
]
