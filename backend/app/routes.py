"""
backend/app/routes.py  —  Step 19

FastAPI route definitions. Routes are thin — all logic lives in services.py.
"""

from __future__ import annotations

from fastapi import APIRouter

from . import services
from .schemas import (
    HealthResponse,
    PatientsResponse,
    QueryRequest,
    QueryResponse,
    TimelineResponse,
)

router = APIRouter()

SUMMARY_QUERY = "Provide a summary of this patient's documented medical history."


# ---------------------------------------------------------------------------
# POST /query
# ---------------------------------------------------------------------------

@router.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest) -> QueryResponse:
    """
    Ask a grounded RAG question about a specific patient.

    patient_id is validated against ^PAT-(NRM|MOD|CHR)-\\d{3}$ before the
    request reaches this handler. The ChromaDB where clause then enforces
    patient scoping at the embedding index level.
    """
    return services.run_query(request)


# ---------------------------------------------------------------------------
# GET /patients
# ---------------------------------------------------------------------------

@router.get("/patients", response_model=PatientsResponse)
async def list_patients() -> PatientsResponse:
    """Return summary metadata for all 15 synthetic patients."""
    return services.get_patients()


# ---------------------------------------------------------------------------
# GET /timeline/{patient_id}
# ---------------------------------------------------------------------------

@router.get("/timeline/{patient_id}", response_model=TimelineResponse)
async def get_timeline(patient_id: str) -> TimelineResponse:
    """
    Return chronological visit history reconstructed from visits[] in patient JSON.
    404 if patient file is not found.
    """
    return services.get_patient_timeline(patient_id)


# ---------------------------------------------------------------------------
# GET /summary/{patient_id}
# ---------------------------------------------------------------------------

@router.get("/summary/{patient_id}", response_model=QueryResponse)
async def get_summary(patient_id: str) -> QueryResponse:
    """
    Generate a grounded patient summary by running a fixed RAG query.
    Retrieves across all source_types. 404 if patient not found.
    """
    # Verify patient exists before calling generate_answer
    services._load_patient_json(patient_id)   # raises 404 if missing

    request = QueryRequest(
        patient_id        = patient_id,
        question          = SUMMARY_QUERY,
        top_k             = 5,
        source_type_hint  = None,
    )
    return services.run_query(request)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    System health check. Always returns HTTP 200.
    ChromaDB unavailability is reported in the response body as status='degraded'.
    """
    return services.get_health()


__all__ = ["router"]
