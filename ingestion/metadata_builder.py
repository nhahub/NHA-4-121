"""
ingestion/metadata_builder.py  —  Step 14

Deterministic, ChromaDB-safe metadata construction and validation layer.

Purpose
-------
This module is the dedicated validation and normalization gate that sits between
the chunker (Step 13) and the ChromaDB ingestion script (Step 15).  It enforces
the exact metadata contract required by ChromaDB before any upsert occurs.

Design contract
---------------
* Does NOT build chunk text.
* Does NOT call any LLM.
* Does NOT write to ChromaDB.
* Does NOT modify patient records.
* Does NOT call the chunker.
* Metadata values must be ChromaDB-compatible scalars only: str, int, float, bool.
* Lists are forbidden — conditions must be pipe-separated strings.
* None values are forbidden — absent optional fields use empty string "".
* All nine MINIMAL_CHROMA_METADATA_FIELDS_V17_LITE fields are always present.
* All three OPTIONAL_CHROMA_METADATA_FIELDS_V17_LITE boolean fields are always present.
* BP keys and demographic keys are hard-forbidden in all metadata output.

Field normalization for allergy chunks
---------------------------------------
Allergy chunks have no visit anchor.  The chunker currently places None for
visit_id, visit_date, visit_type, and visit_role in allergy chunk metadata.
This module coerces those None values to empty string "" before validation.

Public API
----------
build_metadata(chunk, patient, visit)  → dict
build_metadata_for_all_chunks(chunks, patients)  → list[dict]
validate_metadata(metadata, *, source_type)  → None
summarize_metadata_set(metadata_list)  → dict
MetadataBuilderError
"""

from __future__ import annotations

import re
from typing import Any

from config.constants import (
    DATE_REGEX,
    MEDICATION_CHANGE_STATUSES,
    MINIMAL_CHROMA_METADATA_FIELDS_V17_LITE,
    OPTIONAL_CHROMA_METADATA_FIELDS_V17_LITE,
    SEMANTIC_FOCUS,
    SOURCE_TYPES,
    TIMELINE_PATTERNS,
    VISIT_ROLES,
    VISIT_TYPES,
)


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Scalar types accepted by ChromaDB
_SCALAR_TYPES = (str, int, float, bool)

# Compiled date-format regex
_DATE_RE = re.compile(DATE_REGEX)

# The three boolean enrichment field names (always present)
_BOOL_FIELDS: tuple[str, ...] = (
    "has_medication_change",
    "has_hospitalization",
    "has_lab_trend",
)

# Forbidden metadata keys — checked case-insensitively.
# Includes BP terms, large-blob terms, and demographic fields that must never
# be stored in ChromaDB (demographics belong only in structured patient JSON).
_FORBIDDEN_METADATA_KEYS: frozenset[str] = frozenset({
    # Blood pressure — never in metadata
    "bp",
    "blood_pressure",
    "bp_systolic",
    "bp_diastolic",
    "systolic",
    "diastolic",
    "sbp",
    "dbp",
    # Lab raw values — never in metadata
    "lab_value",
    "lab_numeric_value",
    # Large text blobs — never in metadata
    "full_soap_text",
    "retrieval_signature",
    "safe_distractor_text",
    # Demographics — privacy-sensitive; must never be stored in ChromaDB
    "age",
    "date_of_birth",
    "name",
    "sex",
})


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------

class MetadataBuilderError(ValueError):
    """Raised when metadata construction or validation fails."""


# ---------------------------------------------------------------------------
# Public API — primary entry point
# ---------------------------------------------------------------------------

def build_metadata(
    chunk: dict,
    patient: dict,
    visit: dict | None,
) -> dict:
    """
    Build and return a validated ChromaDB-ready metadata dict for one chunk.

    Parameters
    ----------
    chunk   : chunk dict produced by the chunker (ingestion/chunker.py).
    patient : patient dict (full patient record).
    visit   : visit dict for visit-level chunks; None for allergy chunks.

    Returns
    -------
    Validated metadata dict with all required fields, all bool fields, and no
    forbidden keys.

    Raises
    ------
    MetadataBuilderError on any validation failure.
    """
    patient_id  = _require_str(patient, "patient_id", "patient")
    source_type = _require_str(chunk,   "source_type", "chunk")

    # --- Patient-level metadata fields ---
    meta_obj       = patient.get("metadata") or {}
    semantic_focus = str(meta_obj.get("semantic_focus") or "")
    timeline_pat   = str(meta_obj.get("timeline_pattern") or "")

    # --- Conditions: always pipe-separated string ---
    conditions_pipe = _conditions_pipe(patient)

    # --- Visit-level fields (empty string for allergy chunks) ---
    is_allergy = (source_type == "allergy")

    if is_allergy or visit is None:
        visit_id   = ""
        visit_date = ""
        visit_type = ""
        visit_role = ""
        has_medication_change = False
        has_hospitalization   = False
        has_lab_trend         = False
    else:
        visit_id   = str(visit.get("visit_id")   or "")
        visit_date = str(visit.get("visit_date")  or "")
        visit_type = str(visit.get("visit_type")  or "")
        visit_role = str(visit.get("visit_role")  or "")

        # Boolean enrichment fields
        medications = visit.get("medications") or []
        labs        = visit.get("labs")        or []

        has_medication_change = bool(
            any(
                m.get("medication_status") in MEDICATION_CHANGE_STATUSES
                for m in medications
            )
        )
        has_hospitalization = bool(
            visit_type == "hospitalization" or visit_role == "hospitalization"
        )
        has_lab_trend = bool(labs)

    # --- Assemble metadata dict ---
    metadata: dict[str, Any] = {
        # Nine required fields from MINIMAL_CHROMA_METADATA_FIELDS_V17_LITE
        "patient_id":        patient_id,
        "visit_id":          visit_id,
        "visit_date":        visit_date,
        "source_type":       source_type,
        "conditions":        conditions_pipe,
        "visit_type":        visit_type,
        "visit_role":        visit_role,
        "semantic_focus":    semantic_focus,
        "timeline_pattern":  timeline_pat,
        # Three required boolean enrichment fields
        "has_medication_change": has_medication_change,
        "has_hospitalization":   has_hospitalization,
        "has_lab_trend":         has_lab_trend,
    }

    # --- Validate before returning ---
    validate_metadata(metadata, source_type=source_type)
    return metadata


# ---------------------------------------------------------------------------
# Public API — batch entry point
# ---------------------------------------------------------------------------

def build_metadata_for_all_chunks(
    chunks: list[dict],
    patients: list[dict],
) -> list[dict]:
    """
    Build metadata for every chunk in the list.

    Matches each chunk to its patient by patient_id, then matches to the
    correct visit by visit_id.  Any single failure raises MetadataBuilderError
    immediately.

    Returns
    -------
    List of metadata dicts in the same order as the input chunks.
    """
    # Build patient lookup map
    patient_map: dict[str, dict] = {
        p["patient_id"]: p for p in patients
    }

    # Build visit lookup: patient_id → visit_id → visit
    visit_map: dict[str, dict[str, dict]] = {}
    for p in patients:
        pid   = p["patient_id"]
        visits: list[dict] = p.get("visits") or []
        visit_map[pid] = {v["visit_id"]: v for v in visits}

    metadata_list: list[dict] = []

    for idx, chunk in enumerate(chunks):
        pid         = chunk.get("patient_id", "")
        chunk_vid   = chunk.get("visit_id")       # may be None for allergy
        source_type = chunk.get("source_type", "")

        patient = patient_map.get(pid)
        if patient is None:
            raise MetadataBuilderError(
                f"Chunk[{idx}] references unknown patient_id {pid!r}. "
                f"Patient not found in provided patients list."
            )

        # Resolve visit
        if source_type == "allergy" or chunk_vid is None:
            visit = None
        else:
            visit = visit_map.get(pid, {}).get(chunk_vid)
            if visit is None:
                raise MetadataBuilderError(
                    f"Chunk[{idx}] (patient {pid!r}) references unknown "
                    f"visit_id {chunk_vid!r}."
                )

        meta = build_metadata(chunk, patient, visit)
        metadata_list.append(meta)

    return metadata_list


# ---------------------------------------------------------------------------
# Public API — validate_metadata (callable independently for testing)
# ---------------------------------------------------------------------------

def validate_metadata(
    metadata: dict,
    *,
    source_type: str,
) -> None:
    """
    Validate one metadata dict against the full ChromaDB metadata contract.

    Checks (in order):
      1.  All nine required fields are present and non-None.
      2.  All three boolean fields are present and typed bool (not str, not int).
      3.  No forbidden key is present (case-insensitive).
      4.  conditions is a pipe-separated string (no commas, not a list).
      5.  source_type is in SOURCE_TYPES.
      6.  visit_date matches DATE_REGEX if non-empty.
      7.  semantic_focus is in SEMANTIC_FOCUS.
      8.  timeline_pattern is in TIMELINE_PATTERNS.
      9.  visit_type is in VISIT_TYPES if non-empty.
      10. visit_role is in VISIT_ROLES if non-empty.
      11. All metadata values are str, int, float, or bool (no lists, no None,
          no dicts, no other types).

    Raises MetadataBuilderError on first failure with a clear message.
    """
    # Check 11 first — catch None/list values before field-level checks,
    # since they would corrupt field-presence checks if left undetected.
    for key, val in metadata.items():
        if val is None:
            raise MetadataBuilderError(
                f"Metadata key {key!r} has value None. "
                f"Use empty string \"\" for absent optional fields."
            )
        if isinstance(val, (list, dict)):
            raise MetadataBuilderError(
                f"Metadata key {key!r} has non-scalar value of type "
                f"{type(val).__name__}. Only str, int, float, bool are allowed. "
                f"Use pipe-separated strings for lists."
            )
        if not isinstance(val, _SCALAR_TYPES):
            raise MetadataBuilderError(
                f"Metadata key {key!r} has value of unsupported type "
                f"{type(val).__name__}. Only str, int, float, bool are allowed."
            )

    # Check 1 — required fields present and non-empty (visit fields may be "")
    for field in MINIMAL_CHROMA_METADATA_FIELDS_V17_LITE:
        if field not in metadata:
            raise MetadataBuilderError(
                f"Metadata is missing required field {field!r}."
            )
        # patient_id, source_type, conditions, semantic_focus, timeline_pattern
        # must always be non-empty strings.
        if field in ("patient_id", "source_type", "conditions",
                     "semantic_focus", "timeline_pattern"):
            val = metadata[field]
            if not isinstance(val, str) or not val.strip():
                raise MetadataBuilderError(
                    f"Required metadata field {field!r} must be a non-empty string; "
                    f"got {val!r} (type={type(val).__name__})."
                )

    # Check 2 — boolean fields are actual bool
    for bool_key in _BOOL_FIELDS:
        if bool_key not in metadata:
            raise MetadataBuilderError(
                f"Metadata is missing required boolean field {bool_key!r}."
            )
        val = metadata[bool_key]
        if not isinstance(val, bool):
            raise MetadataBuilderError(
                f"Boolean field {bool_key!r} must be typed bool; "
                f"got {val!r} (type={type(val).__name__}). "
                f"Do not use strings or integers for boolean metadata fields."
            )

    # Check 3 — forbidden keys (case-insensitive)
    for key in metadata:
        if key.lower() in _FORBIDDEN_METADATA_KEYS:
            raise MetadataBuilderError(
                f"Forbidden metadata key {key!r} detected. "
                f"BP values and demographic fields must never be stored in "
                f"ChromaDB metadata."
            )

    # Check 4 — conditions is a pipe-separated string
    conditions = metadata.get("conditions", "")
    if not isinstance(conditions, str):
        raise MetadataBuilderError(
            f"'conditions' must be a str; got {type(conditions).__name__}."
        )
    if "," in conditions and "|" not in conditions:
        raise MetadataBuilderError(
            f"'conditions' must be pipe-separated, not comma-separated. "
            f"Got: {conditions!r}."
        )

    # Check 5 — source_type in SOURCE_TYPES
    st = metadata.get("source_type", "")
    if st not in SOURCE_TYPES:
        raise MetadataBuilderError(
            f"source_type {st!r} is not in SOURCE_TYPES {SOURCE_TYPES}."
        )

    # Check 6 — visit_date matches DATE_REGEX if non-empty
    visit_date = metadata.get("visit_date", "")
    if visit_date and not _DATE_RE.match(str(visit_date)):
        raise MetadataBuilderError(
            f"visit_date {visit_date!r} does not match YYYY-MM-DD format."
        )

    # Check 7 — semantic_focus in SEMANTIC_FOCUS
    sf = metadata.get("semantic_focus", "")
    if sf not in SEMANTIC_FOCUS:
        raise MetadataBuilderError(
            f"semantic_focus {sf!r} is not in SEMANTIC_FOCUS {SEMANTIC_FOCUS}."
        )

    # Check 8 — timeline_pattern in TIMELINE_PATTERNS
    tp = metadata.get("timeline_pattern", "")
    if tp not in TIMELINE_PATTERNS:
        raise MetadataBuilderError(
            f"timeline_pattern {tp!r} is not in TIMELINE_PATTERNS {TIMELINE_PATTERNS}."
        )

    # Check 9 — visit_type in VISIT_TYPES if non-empty
    vt = metadata.get("visit_type", "")
    if vt and vt not in VISIT_TYPES:
        raise MetadataBuilderError(
            f"visit_type {vt!r} is not in VISIT_TYPES {VISIT_TYPES}."
        )

    # Check 10 — visit_role in VISIT_ROLES if non-empty
    vr = metadata.get("visit_role", "")
    if vr and vr not in VISIT_ROLES:
        raise MetadataBuilderError(
            f"visit_role {vr!r} is not in VISIT_ROLES {VISIT_ROLES}."
        )


# ---------------------------------------------------------------------------
# Public API — summary helper
# ---------------------------------------------------------------------------

def summarize_metadata_set(
    metadata_list: list[dict],
) -> dict:
    """
    Return a summary dict useful for logging and final reports.

    Returns
    -------
    {
        "total":                       int,
        "by_source_type":              dict[str, int],
        "patients_covered":            int,
        "has_medication_change_count": int,
        "has_hospitalization_count":   int,
        "has_lab_trend_count":         int,
        "forbidden_field_violations":  int,   # always 0 if build_metadata passed
    }
    """
    total = len(metadata_list)
    by_source_type: dict[str, int] = {}
    patient_ids: set[str] = set()
    med_change_count = 0
    hosp_count       = 0
    lab_trend_count  = 0
    forbidden_violations = 0

    for meta in metadata_list:
        st = meta.get("source_type", "unknown")
        by_source_type[st] = by_source_type.get(st, 0) + 1

        pid = meta.get("patient_id", "")
        if pid:
            patient_ids.add(pid)

        if meta.get("has_medication_change") is True:
            med_change_count += 1
        if meta.get("has_hospitalization") is True:
            hosp_count += 1
        if meta.get("has_lab_trend") is True:
            lab_trend_count += 1

        # Count forbidden-key violations (should always be 0 post-validation)
        for key in meta:
            if key.lower() in _FORBIDDEN_METADATA_KEYS:
                forbidden_violations += 1

    return {
        "total":                       total,
        "by_source_type":              by_source_type,
        "patients_covered":            len(patient_ids),
        "has_medication_change_count": med_change_count,
        "has_hospitalization_count":   hosp_count,
        "has_lab_trend_count":         lab_trend_count,
        "forbidden_field_violations":  forbidden_violations,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _conditions_pipe(patient: dict) -> str:
    """Return patient conditions as a pipe-separated string."""
    conds = patient.get("conditions") or []
    return "|".join(str(c) for c in conds if str(c).strip())


def _require_str(obj: dict, key: str, location: str) -> str:
    """Extract a required non-empty string field, raising MetadataBuilderError."""
    val = obj.get(key)
    if not val or not str(val).strip():
        raise MetadataBuilderError(
            f"Required field {location}.{key!r} is missing or empty."
        )
    return str(val).strip()


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    "MetadataBuilderError",
    "build_metadata",
    "build_metadata_for_all_chunks",
    "validate_metadata",
    "summarize_metadata_set",
]
