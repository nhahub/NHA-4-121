"""
backend/app/schemas.py  —  Step 19

Pydantic request and response models for the clinical RAG backend.
All validation rules are enforced here — routes stay thin.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from config.constants import SOURCE_TYPES

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

_PATIENT_ID_PATTERN = r"^PAT-(NRM|MOD|CHR)-\d{3}$"


class QueryRequest(BaseModel):
    patient_id: Annotated[str, Field(pattern=_PATIENT_ID_PATTERN)]
    question:   Annotated[str, Field(min_length=5)]
    top_k:      Annotated[int, Field(ge=1, le=20)] = 5
    source_type_hint: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "patient_id": "PAT-MOD-001",
                "question": "What medications is this patient taking?",
                "top_k": 5,
                "source_type_hint": None,
            }
        }
    )

    def model_post_init(self, __context) -> None:
        if self.source_type_hint is not None:
            if self.source_type_hint not in SOURCE_TYPES:
                raise ValueError(
                    f"source_type_hint {self.source_type_hint!r} is not a valid source type. "
                    f"Allowed: {sorted(SOURCE_TYPES)}"
                )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class CitationResponse(BaseModel):
    chunk_id:    str
    patient_id:  str
    visit_id:    str | None
    visit_date:  str | None
    source_type: str
    visit_role:  str | None
    excerpt:     str


class QueryResponse(BaseModel):
    patient_id:    str
    question:      str
    answer:        str
    citations:     list[CitationResponse]
    grounded:      bool
    chunks_used:   int
    no_evidence:   bool
    model_name:    str
    timestamp_utc: str


class VisitSummary(BaseModel):
    visit_id:             str
    visit_date:           str
    visit_type:           str
    visit_role:           str
    diagnoses:            list[str]
    has_labs:             bool
    has_medications:      bool
    clinical_event_label: str


class TimelineResponse(BaseModel):
    patient_id:   str
    total_visits: int
    visits:       list[VisitSummary]


class PatientSummary(BaseModel):
    patient_id:       str
    conditions:       list[str]
    tier:             str
    total_visits:     int
    has_allergy:      bool
    semantic_focus:   str
    timeline_pattern: str


class PatientsResponse(BaseModel):
    total:    int
    patients: list[PatientSummary]


class HealthResponse(BaseModel):
    status:          str   # "ok" or "degraded"
    chromadb:        str   # "available" or "unavailable"
    chunk_count:     int
    offline_mode:    bool
    dataset_version: str
    timestamp_utc:   str


__all__ = [
    "QueryRequest",
    "CitationResponse",
    "QueryResponse",
    "VisitSummary",
    "TimelineResponse",
    "PatientSummary",
    "PatientsResponse",
    "HealthResponse",
]
