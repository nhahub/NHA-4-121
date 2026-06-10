"""
ingestion/chunker.py  —  Step 13

Deterministic patient-record chunking with retrieval-anchor enforcement.

Design contract
---------------
* Every chunk text MUST begin with a retrieval anchor sentence that
  contains patient_id, source_type label, and the primary clinical evidence.
  This is a hard constraint enforced by validate_chunk().
* Option C construction:  anchor sentence → evidence text → enrichment (≤3 sentences).
* Outputs plain dicts — NOT dataclasses, NOT ChromaDB documents.
* Does NOT write to ChromaDB (that belongs to ingestion/ingest.py).
* Does NOT call any LLM.
* Does NOT modify patient records.
* Metadata follows MINIMAL_CHROMA_METADATA_FIELDS_V17_LITE from constants.
* BP values must NEVER appear in chunk metadata.
* Chunk IDs are deterministic and match CHUNK_ID_REGEX (visit-level) or
  ALLERGY_CHUNK_ID_PATTERN (patient-level allergy).

Supported chunk types
---------------------
Core   (all patients):   doctor_note · lab_result · prescription · allergy
Optional (conditional):  discharge_summary · medication_reconciliation
"""

from __future__ import annotations

import re
from typing import Any

from config.constants import (
    CHUNK_ID_REGEX,
    FORBIDDEN_CHROMA_METADATA_FIELDS_V17_LITE,
    MEDICATION_CHANGE_STATUSES,
    MINIMAL_CHROMA_METADATA_FIELDS_V17_LITE,
    SOURCE_TYPES,
)
from config.patient_blueprints import BLUEPRINT_BY_ID, PatientBlueprint
from ingestion.retrieval_enricher import RetrievalEnrichmentError, build_retrieval_text


# ---------------------------------------------------------------------------
# Allergy chunk IDs use a patient-prefix format, not the visit-prefix format
# ---------------------------------------------------------------------------
_ALLERGY_CHUNK_ID_RE = re.compile(
    r"^PAT-(NRM|MOD|CHR)-\d{3}-allergy-\d{2}$"
)
_VISIT_CHUNK_ID_RE = re.compile(CHUNK_ID_REGEX)

_FORBIDDEN_META_SET: frozenset[str] = frozenset(
    k.lower() for k in FORBIDDEN_CHROMA_METADATA_FIELDS_V17_LITE
)

# Source-type display labels used in anchor sentences
_SOURCE_LABEL: dict[str, str] = {
    "doctor_note":              "Doctor note",
    "lab_result":               "Lab result",
    "prescription":             "Prescription record",
    "allergy":                  "Allergy record",
    "discharge_summary":        "Discharge summary",
    "medication_reconciliation": "Medication reconciliation",
}


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------

class ChunkerError(ValueError):
    """Raised when chunk construction or validation fails."""


# Keep legacy name for backward compatibility
ChunkingError = ChunkerError


# ---------------------------------------------------------------------------
# Public validation gate
# ---------------------------------------------------------------------------

def validate_chunk(chunk: dict, *, patient_id: str) -> None:
    """
    Hard-gate validation.  Raises ChunkerError on any failure.

    Checks (in order):
      1. chunk_id non-empty and matches the correct ID regex.
      2. patient_id in chunk matches expected patient_id.
      3. source_type is in SOURCE_TYPES.
      4. text is non-empty.
      5. First sentence of text contains patient_id (retrieval anchor enforcement).
      6. metadata contains all MINIMAL_CHROMA_METADATA_FIELDS_V17_LITE fields.
      7. No forbidden metadata key is present.
      8. metadata["conditions"] is a pipe-separated string, not a list/comma-only.
    """
    cid = chunk.get("chunk_id", "")
    if not cid:
        raise ChunkerError("chunk_id is empty.")

    source_type = chunk.get("source_type", "")

    # Regex: allergy chunks use patient-prefix; all others use visit-prefix
    if source_type == "allergy":
        if not _ALLERGY_CHUNK_ID_RE.match(cid):
            raise ChunkerError(
                f"Chunk {cid!r}: chunk_id does not match allergy ID pattern "
                f"PAT-(NRM|MOD|CHR)-NNN-allergy-NN."
            )
    else:
        if not _VISIT_CHUNK_ID_RE.match(cid):
            raise ChunkerError(
                f"Chunk {cid!r}: chunk_id does not match CHUNK_ID_REGEX."
            )

    # Check 2: patient_id match
    if chunk.get("patient_id") != patient_id:
        raise ChunkerError(
            f"Chunk {cid!r}: patient_id {chunk.get('patient_id')!r} "
            f"does not match expected {patient_id!r}."
        )

    # Check 3: source_type
    if source_type not in SOURCE_TYPES:
        raise ChunkerError(
            f"Chunk {cid!r}: source_type {source_type!r} not in SOURCE_TYPES."
        )

    # Check 4: text non-empty
    text = chunk.get("text", "")
    if not text or not text.strip():
        raise ChunkerError(f"Chunk {cid!r}: text is empty.")

    # Check 5: retrieval anchor — first sentence must contain patient_id
    first_sentence = text.split(".")[0]
    if patient_id not in first_sentence:
        raise ChunkerError(
            f"Chunk {cid!r}: retrieval anchor enforcement FAIL — "
            f"first sentence does not contain patient_id {patient_id!r}. "
            f"First sentence: {first_sentence!r}"
        )

    # Check 6: required metadata fields
    meta = chunk.get("metadata", {})
    for field in MINIMAL_CHROMA_METADATA_FIELDS_V17_LITE:
        if field not in meta:
            raise ChunkerError(
                f"Chunk {cid!r}: metadata missing required field {field!r}."
            )

    # Check 7: forbidden metadata keys
    for key in meta:
        if key.lower() in _FORBIDDEN_META_SET:
            raise ChunkerError(
                f"Chunk {cid!r}: forbidden metadata key {key!r} detected. "
                f"BP and clinical-value keys must never appear in metadata."
            )

    # Check 8: conditions format
    conds = meta.get("conditions", "")
    if not isinstance(conds, str):
        raise ChunkerError(
            f"Chunk {cid!r}: metadata['conditions'] must be a str; "
            f"got {type(conds).__name__}."
        )
    # If there's a comma but no pipe it's likely a list serialized as string
    if "," in conds and "|" not in conds:
        raise ChunkerError(
            f"Chunk {cid!r}: metadata['conditions'] must be pipe-separated, "
            f"not comma-separated. Got: {conds!r}."
        )


# ---------------------------------------------------------------------------
# Primary public entry point
# ---------------------------------------------------------------------------

def build_chunks_for_patient(
    patient: dict,
    blueprint: PatientBlueprint | None = None,
) -> list[dict]:
    """
    Build all chunks for one patient.  Returns a flat list of chunk dicts.
    Does not write to ChromaDB.
    """
    patient_id: str = patient["patient_id"]
    if blueprint is None:
        blueprint = BLUEPRINT_BY_ID.get(patient_id)

    visits: list[dict] = patient.get("visits", [])
    chunks: list[dict] = []

    for idx, visit in enumerate(visits):
        # --- doctor_note (all visits) ---
        dn = build_doctor_note_chunk(patient, blueprint, visit, idx)
        _validate_and_append(chunks, dn, patient_id)

        # --- lab_result (only if labs present) ---
        if visit.get("labs"):
            lr = build_lab_result_chunk(patient, blueprint, visit, idx)
            _validate_and_append(chunks, lr, patient_id)

        # --- prescription (only if medications present) ---
        if visit.get("medications"):
            rx = build_prescription_chunk(patient, blueprint, visit, idx)
            _validate_and_append(chunks, rx, patient_id)

        # --- discharge_summary (hospitalization visits only) ---
        if visit.get("visit_type") == "hospitalization":
            ds = build_discharge_summary_chunk(patient, blueprint, visit, idx)
            _validate_and_append(chunks, ds, patient_id)

        # --- medication_reconciliation (reconciliation visits only) ---
        if visit.get("visit_role") == "medication_reconciliation":
            mr = build_medication_reconciliation_chunk(patient, blueprint, visit, idx)
            _validate_and_append(chunks, mr, patient_id)

    # --- allergy (one per patient, always) ---
    al = build_allergy_chunk(patient, blueprint)
    _validate_and_append(chunks, al, patient_id)

    _assert_unique_chunk_ids(chunks, patient_id)
    return chunks


def build_all_chunks(
    patients: list[dict],
    blueprint_map: dict[str, PatientBlueprint] | None = None,
) -> list[dict]:
    """Build chunks for all patients.  Returns flat list."""
    all_chunks: list[dict] = []
    for patient in patients:
        bp = (blueprint_map or {}).get(patient["patient_id"])
        all_chunks.extend(build_chunks_for_patient(patient, bp))
    return all_chunks


# ---------------------------------------------------------------------------
# Per-source-type builders
# ---------------------------------------------------------------------------

def build_doctor_note_chunk(
    patient: dict,
    blueprint: PatientBlueprint | None,
    visit: dict,
    visit_index: int,
) -> dict:
    """One doctor_note chunk per visit."""
    patient_id = patient["patient_id"]
    visit_id   = visit["visit_id"]
    visit_date = visit["visit_date"]
    visit_role = visit.get("visit_role", "")
    source_type = "doctor_note"

    # Anchor sentence
    event_summary = _event_summary(visit)
    anchor = (
        f"Doctor note for {patient_id} {visit_role} visit on {visit_date}: "
        f"{event_summary}."
    )

    # Evidence: full SOAP
    soap = visit.get("soap_note") or {}
    evidence_parts: list[str] = []
    for section in ("subjective", "objective", "assessment", "plan"):
        text = (soap.get(section) or "").strip()
        if text:
            evidence_parts.append(f"{section.capitalize()}: {text}")
    evidence = "\n".join(evidence_parts)

    # Enrichment
    enrichment = _safe_enrichment(patient, visit, source_type)

    text = _join_parts([anchor, evidence, enrichment])

    return _make_chunk(
        chunk_id=f"{visit_id}-{source_type}-01",
        patient_id=patient_id,
        visit_id=visit_id,
        source_type=source_type,
        text=text,
        visit=visit,
        patient=patient,
        blueprint=blueprint,
    )


def build_lab_result_chunk(
    patient: dict,
    blueprint: PatientBlueprint | None,
    visit: dict,
    visit_index: int,
) -> dict:
    """One lab_result chunk per visit that has labs."""
    patient_id  = patient["patient_id"]
    visit_id    = visit["visit_id"]
    visit_date  = visit["visit_date"]
    source_type = "lab_result"
    labs        = visit.get("labs") or []

    # Anchor: list lab types + conditions
    lab_types  = [lb["lab_type"] for lb in labs if lb.get("lab_type")]
    conds      = _conditions_str(patient)
    lab_label  = _human_join(lab_types) if lab_types else "laboratory data"
    anchor = (
        f"Lab result for {patient_id} visit {visit_id} on {visit_date}: "
        f"{lab_label} documented for {conds} monitoring."
    )

    # Evidence: structured lab records
    lab_lines: list[str] = []
    for lb in labs:
        lt   = lb.get("lab_type", "")
        val  = lb.get("value", "")
        unit = lb.get("unit", "")
        flag = lb.get("flag", "")
        rr   = lb.get("reference_range", "")
        if rr:
            lab_lines.append(f"{lt}: {val} {unit} ({flag}; ref {rr})")
        else:
            lab_lines.append(f"{lt}: {val} {unit} ({flag})")
    evidence = "Documented laboratory results: " + "; ".join(lab_lines) + "."

    enrichment = _safe_enrichment(patient, visit, source_type)

    text = _join_parts([anchor, evidence, enrichment])

    return _make_chunk(
        chunk_id=f"{visit_id}-{source_type}-01",
        patient_id=patient_id,
        visit_id=visit_id,
        source_type=source_type,
        text=text,
        visit=visit,
        patient=patient,
        blueprint=blueprint,
    )


def build_prescription_chunk(
    patient: dict,
    blueprint: PatientBlueprint | None,
    visit: dict,
    visit_index: int,
) -> dict:
    """One prescription chunk per visit that has medications."""
    patient_id  = patient["patient_id"]
    visit_id    = visit["visit_id"]
    visit_date  = visit["visit_date"]
    source_type = "prescription"
    medications = visit.get("medications") or []

    # Anchor: highlight newly added / started meds, then rest
    added   = [m["medication_name"] for m in medications
               if m.get("medication_status") in ("started", "added")]
    others  = [m["medication_name"] for m in medications
               if m.get("medication_status") not in ("started", "added")
               and m.get("medication_name")]

    if added:
        added_label = _human_join(added)
        cont_label  = (f" {_human_join(others)} continued." if others else "")
        anchor_detail = f"{added_label} was newly added.{cont_label}"
    else:
        all_names = [m["medication_name"] for m in medications if m.get("medication_name")]
        anchor_detail = f"{_human_join(all_names)} documented."

    anchor = (
        f"Prescription record for {patient_id} visit {visit_id} on {visit_date}: "
        f"{anchor_detail}"
    )

    # Evidence: structured medication records
    med_lines: list[str] = []
    for m in medications:
        name   = m.get("medication_name", "")
        dose   = m.get("dose", "")
        freq   = m.get("frequency", "")
        route  = m.get("route", "")
        start  = m.get("start_date") or ""
        stop   = m.get("stop_date") or ""
        status = m.get("medication_status", "")
        traj   = m.get("trajectory_event", "")
        reason = m.get("reason", "")

        line = f"{name} {dose} {freq} via {route}"
        if start:
            line += f", start {start}"
        if stop:
            line += f", stop {stop}"
        line += f" (status: {status}; trajectory: {traj})"
        if reason:
            line += f"; reason: {reason}"
        med_lines.append(line)

    evidence = "Documented medications: " + "; ".join(med_lines) + "."

    enrichment = _safe_enrichment(patient, visit, source_type)

    text = _join_parts([anchor, evidence, enrichment])

    return _make_chunk(
        chunk_id=f"{visit_id}-{source_type}-01",
        patient_id=patient_id,
        visit_id=visit_id,
        source_type=source_type,
        text=text,
        visit=visit,
        patient=patient,
        blueprint=blueprint,
    )


def build_allergy_chunk(
    patient: dict,
    blueprint: PatientBlueprint | None,
) -> dict:
    """One patient-level allergy chunk per patient (always generated)."""
    patient_id      = patient["patient_id"]
    source_type     = "allergy"
    allergy_registry = patient.get("allergy_registry") or []

    # Anchor sentence
    if allergy_registry:
        first = allergy_registry[0]
        allergen  = first.get("allergen", "")
        reaction  = first.get("reaction", "")
        severity  = first.get("severity", "")
        rec_date  = first.get("recorded_date", "")
        anchor = (
            f"Allergy record for {patient_id}: {allergen} allergy with "
            f"{reaction} reaction, severity {severity}, recorded {rec_date}."
        )
    else:
        anchor = (
            f"Allergy record for {patient_id}: No documented allergies."
        )

    # Evidence: full allergy registry
    if allergy_registry:
        lines: list[str] = []
        for al in allergy_registry:
            allergen  = al.get("allergen", "")
            reaction  = al.get("reaction", "")
            severity  = al.get("severity", "")
            rec_date  = al.get("recorded_date", "")
            src_visit = al.get("source_visit_id", "")
            lines.append(
                f"{allergen}: reaction {reaction}, severity {severity}, "
                f"recorded {rec_date}, source visit {src_visit}"
            )
        evidence = "Documented allergy registry: " + "; ".join(lines) + "."
    else:
        evidence = "No documented allergies are recorded in the available synthetic patient record."

    # Enrichment (patient-level)
    enrichment = _safe_enrichment(patient, None, source_type)

    text = _join_parts([anchor, evidence, enrichment])

    # Patient-level metadata (no visit)
    conditions_pipe = _conditions_pipe(patient)
    meta_obj        = patient.get("metadata") or {}
    semantic_focus  = meta_obj.get("semantic_focus", "")
    timeline_pat    = meta_obj.get("timeline_pattern", "")

    metadata: dict[str, Any] = {
        "patient_id":            patient_id,
        "visit_id":              None,
        "visit_date":            None,
        "source_type":           source_type,
        "conditions":            conditions_pipe,
        "visit_type":            None,
        "visit_role":            None,
        "semantic_focus":        semantic_focus,
        "timeline_pattern":      timeline_pat,
        "has_medication_change": False,
        "has_hospitalization":   False,
        "has_lab_trend":         False,
    }

    return {
        "chunk_id":    f"{patient_id}-allergy-01",
        "patient_id":  patient_id,
        "visit_id":    None,
        "source_type": source_type,
        "text":        text,
        "metadata":    metadata,
    }


def build_discharge_summary_chunk(
    patient: dict,
    blueprint: PatientBlueprint | None,
    visit: dict,
    visit_index: int,
) -> dict:
    """
    Discharge summary chunk — only for visit_type == 'hospitalization'.
    Uses SOAP text reformatted as a discharge narrative.
    """
    patient_id  = patient["patient_id"]
    visit_id    = visit["visit_id"]
    visit_date  = visit["visit_date"]
    source_type = "discharge_summary"
    conds       = _conditions_str(patient)

    anchor = (
        f"Discharge summary for {patient_id} hospitalization visit {visit_id}: "
        f"{conds} with inpatient hospitalisation and post-discharge "
        f"stabilisation plan documented."
    )

    # Evidence: SOAP reformatted as discharge narrative
    soap  = visit.get("soap_note") or {}
    parts = []
    s = (soap.get("subjective") or "").strip()
    o = (soap.get("objective") or "").strip()
    a = (soap.get("assessment") or "").strip()
    p = (soap.get("plan") or "").strip()
    if s:
        parts.append(f"Admission presenting concern: {s}")
    if o:
        parts.append(f"Inpatient objective findings: {o}")
    if a:
        parts.append(f"Discharge assessment: {a}")
    if p:
        parts.append(f"Discharge plan: {p}")
    evidence = "\n".join(parts) if parts else "Discharge clinical documentation recorded."

    # Enrichment: use doctor_note enrichment (closest semantically)
    enrichment = _safe_enrichment(patient, visit, "doctor_note")

    text = _join_parts([anchor, evidence, enrichment])

    return _make_chunk(
        chunk_id=f"{visit_id}-{source_type}-01",
        patient_id=patient_id,
        visit_id=visit_id,
        source_type=source_type,
        text=text,
        visit=visit,
        patient=patient,
        blueprint=blueprint,
    )


def build_medication_reconciliation_chunk(
    patient: dict,
    blueprint: PatientBlueprint | None,
    visit: dict,
    visit_index: int,
) -> dict:
    """
    Medication reconciliation chunk — only for visit_role == 'medication_reconciliation'.
    Lists all active medications with post-discharge context.
    """
    patient_id  = patient["patient_id"]
    visit_id    = visit["visit_id"]
    visit_date  = visit["visit_date"]
    source_type = "medication_reconciliation"
    medications = visit.get("medications") or []

    med_names = [m["medication_name"] for m in medications if m.get("medication_name")]
    names_str = _human_join(med_names) if med_names else "medications"

    anchor = (
        f"Medication reconciliation for {patient_id} visit {visit_id}: "
        f"{names_str} reviewed during post-discharge reconciliation."
    )

    # Evidence: all active medications with trajectory context
    med_lines: list[str] = []
    for m in medications:
        name   = m.get("medication_name", "")
        dose   = m.get("dose", "")
        freq   = m.get("frequency", "")
        route  = m.get("route", "")
        status = m.get("medication_status", "")
        traj   = m.get("trajectory_event", "")
        line = f"{name} {dose} {freq} via {route} (status: {status}; trajectory: {traj})"
        med_lines.append(line)

    if med_lines:
        evidence = (
            "Post-discharge medication reconciliation: "
            + "; ".join(med_lines) + "."
        )
    else:
        evidence = "No medications documented during reconciliation visit."

    # Enrichment: use prescription enrichment (closest semantically)
    enrichment = _safe_enrichment(patient, visit, "prescription")

    text = _join_parts([anchor, evidence, enrichment])

    return _make_chunk(
        chunk_id=f"{visit_id}-{source_type}-01",
        patient_id=patient_id,
        visit_id=visit_id,
        source_type=source_type,
        text=text,
        visit=visit,
        patient=patient,
        blueprint=blueprint,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_chunk(
    *,
    chunk_id: str,
    patient_id: str,
    visit_id: str,
    source_type: str,
    text: str,
    visit: dict,
    patient: dict,
    blueprint: PatientBlueprint | None,
) -> dict:
    """Assemble a chunk dict with full metadata."""
    if not text.strip():
        raise ChunkerError(f"Chunk {chunk_id!r} has empty text.")

    meta_obj        = patient.get("metadata") or {}
    semantic_focus  = meta_obj.get("semantic_focus", "")
    timeline_pat    = meta_obj.get("timeline_pattern", "")
    conditions_pipe = _conditions_pipe(patient)

    visit_date  = visit.get("visit_date", "")
    visit_type  = visit.get("visit_type", "")
    visit_role  = visit.get("visit_role", "")
    medications = visit.get("medications") or []
    labs        = visit.get("labs") or []

    has_medication_change = any(
        m.get("medication_status") in MEDICATION_CHANGE_STATUSES
        for m in medications
    )
    has_hospitalization = (
        visit_type == "hospitalization" or visit_role == "hospitalization"
    )
    has_lab_trend = bool(labs)

    metadata: dict[str, Any] = {
        "patient_id":            patient_id,
        "visit_id":              visit_id,
        "visit_date":            visit_date,
        "source_type":           source_type,
        "conditions":            conditions_pipe,
        "visit_type":            visit_type,
        "visit_role":            visit_role,
        "semantic_focus":        semantic_focus,
        "timeline_pattern":      timeline_pat,
        "has_medication_change": has_medication_change,
        "has_hospitalization":   has_hospitalization,
        "has_lab_trend":         has_lab_trend,
    }

    return {
        "chunk_id":    chunk_id,
        "patient_id":  patient_id,
        "visit_id":    visit_id,
        "source_type": source_type,
        "text":        text.strip(),
        "metadata":    metadata,
    }


def _validate_and_append(
    chunks: list[dict],
    chunk: dict,
    patient_id: str,
) -> None:
    """Validate then append; raises ChunkerError on failure."""
    validate_chunk(chunk, patient_id=patient_id)
    chunks.append(chunk)


def _assert_unique_chunk_ids(chunks: list[dict], patient_id: str) -> None:
    seen: set[str] = set()
    for chunk in chunks:
        cid = chunk["chunk_id"]
        if cid in seen:
            raise ChunkerError(
                f"Duplicate chunk_id {cid!r} for patient {patient_id!r}."
            )
        seen.add(cid)


def _safe_enrichment(
    patient: dict,
    visit: dict | None,
    source_type: str,
) -> str:
    """Call build_retrieval_text; return empty string on any failure."""
    try:
        return build_retrieval_text(patient, visit, source_type)
    except (RetrievalEnrichmentError, Exception):
        return ""


def _conditions_pipe(patient: dict) -> str:
    conds = patient.get("conditions") or []
    return "|".join(str(c) for c in conds if str(c).strip())


def _conditions_str(patient: dict) -> str:
    conds = patient.get("conditions") or []
    cleaned = [str(c) for c in conds if str(c).strip()]
    if not cleaned:
        return "documented conditions"
    return _human_join(cleaned)


def _event_summary(visit: dict) -> str:
    ce = visit.get("clinical_event") or {}
    summary = (ce.get("event_summary") or "").strip()
    if summary:
        return summary.rstrip(".")
    return (visit.get("visit_role") or "clinical visit").replace("_", " ")


def _human_join(items: list[str]) -> str:
    cleaned = [s.strip() for s in items if s.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return ", ".join(cleaned[:-1]) + f", and {cleaned[-1]}"


def _join_parts(parts: list[str]) -> str:
    return "\n".join(p.strip() for p in parts if p and p.strip())


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    "ChunkerError",
    "ChunkingError",
    "validate_chunk",
    "build_chunks_for_patient",
    "build_all_chunks",
    "build_doctor_note_chunk",
    "build_lab_result_chunk",
    "build_prescription_chunk",
    "build_allergy_chunk",
    "build_discharge_summary_chunk",
    "build_medication_reconciliation_chunk",
]
