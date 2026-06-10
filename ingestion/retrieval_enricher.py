"""
ingestion/retrieval_enricher.py

Deterministic Retrieval Enrichment Layer — Step 12.

Builds retrieval-oriented text from documented structured patient facts.
This module is intentionally deterministic and does NOT:
  - call any LLM or external API
  - mutate patient JSON
  - build embeddings or write to ChromaDB
  - invent medical facts, diagnoses, lab values, or medications
  - exceed three sentences per enrichment output

Source truth remains: validated patient JSON + deterministic SOAP notes.
Enrichment text is retrieval support only.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from config.constants import (
    CORE_SOURCE_TYPES,
    LAB_FOCUS_BY_CONDITION,
    MEDICATION_NAMES,
)
from config.patient_blueprints import BLUEPRINT_BY_ID, PatientBlueprint


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class RetrievalEnrichmentError(ValueError):
    """Raised when build_retrieval_text is called with invalid arguments."""


# ---------------------------------------------------------------------------
# Visit-role vocabulary — mirrors soap_semantics.VISIT_ROLE_VOCABULARY.
# Reproduced here so the enrichment layer has no runtime dependency on the
# SOAP generation layer.  Must stay in sync with soap_semantics.py.
# ---------------------------------------------------------------------------

_VISIT_ROLE_PHRASES: dict[str, tuple[str, ...]] = {
    "initial_diagnosis": (
        "initial diagnosis was documented",
        "baseline management plan established",
    ),
    "baseline_assessment": (
        "baseline assessment conducted",
        "initial laboratory and clinical data reviewed",
    ),
    "routine_follow_up": (
        "routine follow-up visit",
        "ongoing medication review conducted",
    ),
    "partial_adherence": (
        "reported partial adherence",
        "missed doses noted",
        "adherence counselling provided",
    ),
    "poor_adherence": (
        "documented poor medication adherence",
        "patient reported inconsistent medication use",
    ),
    "lab_trend_review": (
        "laboratory trend reviewed",
        "results compared with prior documented values",
    ),
    "medication_started": (
        "new medication initiated",
        "treatment commenced at this visit",
    ),
    "medication_continued": (
        "current medication regimen continued",
        "no changes to prescribed therapy",
    ),
    "dose_adjustment": (
        "dose adjustment documented",
        "medication regimen modified at this visit",
    ),
    "second_medication_added": (
        "second medication added to regimen",
        "combination therapy initiated",
    ),
    "acute_treatment_started": (
        "acute treatment course initiated",
        "short-course therapy commenced",
    ),
    "course_completed": (
        "treatment course completed",
        "short-course therapy concluded at this visit",
    ),
    "symptom_flare": (
        "symptom flare documented",
        "exacerbation of existing condition noted",
    ),
    "symptom_control_review": (
        "symptom control reviewed",
        "clinical response to therapy assessed",
    ),
    "emergency_exacerbation": (
        "emergency presentation documented",
        "acute exacerbation requiring urgent management",
    ),
    "hospitalization": (
        "inpatient hospitalization documented",
        "hospital admission recorded for this encounter",
    ),
    "post_discharge_stabilization": (
        "following recent hospitalization",
        "post-discharge review conducted",
        "discharge medications reviewed",
    ),
    "ckd_monitoring": (
        "CKD monitoring visit",
        "renal function parameters reviewed",
        "kidney function test results reviewed at this visit",
    ),
    "medication_reconciliation": (
        "medication reconciliation performed",
        "post-discharge medication list verified",
    ),
    "recovery_confirmed": (
        "recovery confirmed at this visit",
        "resolution of acute episode documented",
    ),
}

# Condition → human-readable retrieval label
_CONDITION_LABELS: dict[str, str] = {
    "T2DM": "type 2 diabetes",
    "HTN": "hypertension",
    "CKD": "chronic kidney disease",
    "IDA": "iron deficiency anemia",
    "Dyslipidemia": "dyslipidemia",
    "Asthma": "asthma",
    "GERD": "gastroesophageal reflux disease",
    "Allergic_Rhinitis": "allergic rhinitis",
    "UTI": "urinary tract infection",
    "Acute_URTI": "acute upper respiratory infection",
}

# Condition → lab semantic label (matches LAB_FOCUS_BY_CONDITION)
_LAB_CONDITION_RETRIEVAL_LABELS: dict[str, str] = {
    "T2DM": "diabetes-related",
    "HTN": "hypertension-related",
    "CKD": "CKD-related",
    "IDA": "anemia-related",
    "Dyslipidemia": "dyslipidaemia-related",
}

# medication_status / trajectory_event → query-aligned status phrase
_MED_STATUS_PHRASE: dict[str, str] = {
    "started": "first prescribed at this visit",
    "added": "newly added at this visit",
    "completed": "course completed at this visit",
}

_MED_TRAJECTORY_PHRASE: dict[str, str] = {
    "adherence_interruption": "missed doses documented",
    "post_discharge_reconciliation": "reviewed during post-discharge reconciliation",
    "course_completed": "course completed at this visit",
    "second_medication_added": "newly added at this visit",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_retrieval_text(
    patient: dict,
    visit: dict | None,
    source_type: str,
) -> str:
    """
    Build deterministic retrieval-oriented text for one supported source type.

    Args:
        patient:     Full patient JSON dictionary.
        visit:       Visit dictionary. Required for doctor_note, lab_result,
                     and prescription. Ignored for allergy.
        source_type: One of CORE_SOURCE_TYPES.

    Returns:
        Retrieval support text as a plain string (max three sentences).

    Raises:
        RetrievalEnrichmentError: Invalid source_type or missing visit.
    """
    if source_type not in CORE_SOURCE_TYPES:
        raise RetrievalEnrichmentError(
            f"Unsupported source_type {source_type!r}. "
            f"Expected one of: {', '.join(CORE_SOURCE_TYPES)}"
        )

    if source_type == "allergy":
        return _build_allergy_enrichment(patient)

    if visit is None:
        raise RetrievalEnrichmentError(
            f"source_type={source_type!r} requires a visit dictionary. "
            "Only source_type='allergy' supports visit=None."
        )

    if source_type == "doctor_note":
        return _build_doctor_note_enrichment(patient, visit)

    if source_type == "lab_result":
        return _build_lab_result_enrichment(patient, visit)

    # prescription
    return _build_prescription_enrichment(patient, visit)


def build_all_retrieval_texts(
    patient: dict,
    blueprint: PatientBlueprint | None = None,
) -> dict[str, list[str]]:
    """
    Build all retrieval enrichment texts for a patient.

    Returns:
        Dict mapping source_type → list of enrichment strings.
        Visit-level types have one entry per visit.
        lab_result only includes visits that have documented labs.
        allergy has exactly one entry per patient.
    """
    result: dict[str, list[str]] = {
        "doctor_note": [],
        "lab_result": [],
        "prescription": [],
        "allergy": [],
    }

    for visit in _safe_visits(patient):
        result["doctor_note"].append(
            build_retrieval_text(patient, visit, "doctor_note")
        )
        if _visit_lab_names(visit):
            result["lab_result"].append(
                build_retrieval_text(patient, visit, "lab_result")
            )
        result["prescription"].append(
            build_retrieval_text(patient, visit, "prescription")
        )

    result["allergy"].append(build_retrieval_text(patient, None, "allergy"))
    return result


# ---------------------------------------------------------------------------
# Source-type builders (max 3 sentences each)
# ---------------------------------------------------------------------------

def _build_doctor_note_enrichment(patient: dict, visit: dict) -> str:
    """Build doctor_note enrichment — exactly 3 sentences."""
    patient_id = _s(patient.get("patient_id"))
    visit_id   = _s(visit.get("visit_id"))
    visit_date = _s(visit.get("visit_date"))
    visit_type = _s(visit.get("visit_type", ""))
    visit_role = _s(visit.get("visit_role", ""))

    conditions = _combined_conditions(patient, visit)
    med_names  = _visit_medication_names(visit)
    lab_names  = _visit_lab_names(visit)
    has_vitals = bool(visit.get("vitals"))

    cond_label     = _condition_display(conditions)
    visit_type_txt = visit_type.replace("_", " ") if visit_type else "encounter"

    # Sentence 1: header + key clinical facts
    header = (
        f"Doctor note retrieval context for {patient_id} visit {visit_id} "
        f"on {visit_date}: "
    )
    s1_facts = [f"{cond_label} {visit_type_txt} encounter"]
    if has_vitals:
        s1_facts.append("vitals documented")
    if lab_names:
        s1_facts.append(f"labs: {_comma(lab_names)}")
    if med_names:
        s1_facts.append(f"medications: {_comma(med_names)}")
    s1 = header + "; ".join(s1_facts) + "."

    # Sentence 2: visit_role vocabulary re-injection (required)
    role_phrases = _VISIT_ROLE_PHRASES.get(visit_role, ())
    if role_phrases:
        raw = role_phrases[0].rstrip(",").rstrip(".")
        s2 = raw[0].upper() + raw[1:] + "."
    else:
        role_txt = visit_role.replace("_", " ") if visit_role else "clinical"
        s2 = f"This visit is documented as a {role_txt} encounter."

    # Sentence 3: monitoring context
    lab_labels = _lab_condition_labels_for(lab_names, conditions)
    if lab_labels:
        s3 = (
            f"Laboratory trend monitoring for "
            f"{_and(lab_labels)} documented at this visit."
        )
    elif med_names:
        s3 = (
            f"Medication documentation for {cond_label} "
            "updated at this visit."
        )
    else:
        s3 = (
            f"Clinical findings for {cond_label} documented at "
            f"this {visit_type_txt} encounter."
        )

    return f"{s1} {s2} {s3}"


def _build_lab_result_enrichment(patient: dict, visit: dict) -> str:
    """Build lab_result enrichment — exactly 3 sentences. 'trend' must appear."""
    patient_id = _s(patient.get("patient_id"))
    visit_id   = _s(visit.get("visit_id"))
    visit_date = _s(visit.get("visit_date"))

    conditions = _combined_conditions(patient, visit)
    lab_names  = _visit_lab_names(visit)
    cond_label = _condition_display(conditions)

    # Condition-specific vocabulary bridge for kidney/renal queries.
    # When CKD is documented, the lab chunk must win over doctor_note for
    # queries like "kidney test results" / "renal function test".
    has_ckd = "CKD" in conditions

    # Sentence 1: header + lab names  [+ kidney-test bridge if CKD patient]
    header = (
        f"Lab result retrieval context for {patient_id} visit {visit_id} "
        f"on {visit_date}: "
    )
    if lab_names:
        base = f"{_and(list(lab_names))} documented"
        if has_ckd:
            s1 = header + base + (" — kidney function test results and renal function test "
                                   "values recorded at this visit.")
        else:
            s1 = header + base + "."
    else:
        s1 = header + "No laboratory results documented at this visit."

    # Sentence 2: condition-lab semantic labels
    label_parts: list[str] = []
    for condition in conditions:
        focus = LAB_FOCUS_BY_CONDITION.get(condition, ())
        relevant = [lb for lb in focus if lb in lab_names]
        if not relevant:
            continue
        lbl = _LAB_CONDITION_RETRIEVAL_LABELS.get(condition, "")
        if lbl:
            label_parts.append(f"{_and(relevant)} is {lbl}")

    if label_parts:
        s2 = "; ".join(label_parts) + " monitoring."
        if has_ckd and "CKD-related" in s2:
            # Inject renal-test retrieval bridge into S2 for CKD
            s2 = s2.rstrip(".") + "; Creatinine is a kidney function blood test result."
    elif lab_names:
        s2 = f"Laboratory values for {cond_label} documented at this visit."
    else:
        s2 = "No condition-specific laboratory documentation at this visit."

    # Sentence 3: must contain the word "trend"
    if lab_names:
        s3 = (
            f"Laboratory trend tracked at this scheduled visit "
            f"for {cond_label}."
        )
    else:
        s3 = "No laboratory trend data available at this visit."

    return f"{s1} {s2} {s3}"


def _build_prescription_enrichment(patient: dict, visit: dict) -> str:
    """Build prescription enrichment — exactly 3 sentences."""
    patient_id = _s(patient.get("patient_id"))
    visit_id   = _s(visit.get("visit_id"))
    visit_date = _s(visit.get("visit_date"))

    conditions  = _combined_conditions(patient, visit)
    medications = _safe_medications(visit)
    med_names   = [
        _s(m.get("medication_name"))
        for m in medications
        if _s(m.get("medication_name"))
    ]
    cond_label = _condition_display(conditions)

    # Sentence 1: header + medication names
    header = (
        f"Prescription retrieval context for {patient_id} visit {visit_id} "
        f"on {visit_date}: "
    )
    if med_names:
        s1 = header + f"{_and(med_names)} documented."
    else:
        s1 = header + "No medications documented at this visit."

    # Sentence 2: per-medication status phrases
    status_parts: list[str] = []
    for med in medications:
        name = _s(med.get("medication_name"))
        if not name:
            continue
        status     = _s(med.get("medication_status", ""))
        trajectory = _s(med.get("trajectory_event", ""))
        phrase     = _med_status_phrase(status, trajectory)
        status_parts.append(f"{name} {phrase}")

    if status_parts:
        s2 = "; ".join(status_parts) + "."
    elif med_names:
        s2 = f"{_and(med_names)} continued from prior visit."
    else:
        s2 = "No medication status changes documented at this visit."

    # Sentence 3: conditions treated
    if conditions and med_names:
        s3 = f"Medications prescribed for {cond_label} management."
    elif med_names:
        s3 = "Prescription documentation updated at this visit."
    else:
        s3 = "No prescription updates at this visit."

    return f"{s1} {s2} {s3}"


def _build_allergy_enrichment(patient: dict) -> str:
    """Build allergy enrichment — patient-level (no visit required)."""
    patient_id = _s(patient.get("patient_id"))
    allergies  = _safe_dict_list(patient.get("allergy_registry"))

    header = (
        f"Allergy retrieval context for {patient_id}: "
        if patient_id
        else "Allergy retrieval context: "
    )

    if not allergies:
        return header + "No documented allergies recorded in the available records."

    allergy_sentences: list[str] = []
    for allergy in allergies:
        allergen  = _s(allergy.get("allergen", ""))
        reaction  = _s(allergy.get("reaction", ""))
        severity  = _s(allergy.get("severity", ""))

        parts: list[str] = []
        if allergen:
            parts.append(f"{allergen} allergy documented")
        if reaction:
            parts.append(f"with {reaction} reaction")
        if severity:
            parts.append(f"severity {severity}")
        if parts:
            allergy_sentences.append(", ".join(parts) + ".")

    # Sentence 1: header + first allergy detail
    if allergy_sentences:
        s1 = header + allergy_sentences[0]
    else:
        s1 = header + "Allergy entry documented in this patient record."

    # Sentence 2: "documented allergy history" framing
    allergen_names = [
        _s(a.get("allergen", ""))
        for a in allergies
        if _s(a.get("allergen", ""))
    ]
    if allergen_names:
        s2 = (
            f"The documented allergy history for this patient includes "
            f"{_and(allergen_names)}."
        )
    else:
        s2 = "The documented allergy history for this patient is recorded above."

    return f"{s1} {s2}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _med_status_phrase(status: str, trajectory: str) -> str:
    """Return a query-aligned phrase for a medication's status/trajectory."""
    # trajectory takes precedence for specific trajectory events
    if trajectory in _MED_TRAJECTORY_PHRASE:
        return _MED_TRAJECTORY_PHRASE[trajectory]
    if status in _MED_STATUS_PHRASE:
        return _MED_STATUS_PHRASE[status]
    return "continued from prior visit"


def _combined_conditions(patient: dict, visit: dict) -> tuple[str, ...]:
    """Return ordered unique conditions from patient + visit diagnoses."""
    patient_conds = tuple(
        c for c in (patient.get("conditions") or [])
        if isinstance(c, str) and c.strip()
    )
    visit_diags = tuple(
        d for d in (visit.get("diagnoses") or [])
        if isinstance(d, str) and d.strip()
    )
    seen: set[str] = set()
    out: list[str] = []
    for c in (*patient_conds, *visit_diags):
        if c not in seen:
            seen.add(c)
            out.append(c)
    return tuple(out)


def _visit_medication_names(visit: dict) -> tuple[str, ...]:
    """Return medication names documented in the visit."""
    names: list[str] = []
    seen: set[str] = set()
    for med in _safe_medications(visit):
        name = _s(med.get("medication_name", ""))
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return tuple(names)


def _visit_lab_names(visit: dict) -> tuple[str, ...]:
    """Return lab_type names documented in the visit."""
    names: list[str] = []
    seen: set[str] = set()
    for lab in _safe_dict_list(visit.get("labs")):
        name = _s(lab.get("lab_type", ""))
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return tuple(names)


def _lab_condition_labels_for(
    lab_names: tuple[str, ...],
    conditions: tuple[str, ...],
) -> list[str]:
    """Return semantic label strings like 'diabetes-related' for matched labs."""
    labels: list[str] = []
    seen: set[str] = set()
    for condition in conditions:
        lbl = _LAB_CONDITION_RETRIEVAL_LABELS.get(condition, "")
        if not lbl:
            continue
        if any(lb in lab_names for lb in LAB_FOCUS_BY_CONDITION.get(condition, ())):
            if lbl not in seen:
                seen.add(lbl)
                labels.append(lbl)
    return labels


def _condition_display(conditions: tuple[str, ...]) -> str:
    """Return a comma-and joined human-readable condition string."""
    labels = [_CONDITION_LABELS.get(c, c.replace("_", " ")) for c in conditions]
    if not labels:
        return "documented conditions"
    return _and(labels)


def _safe_visits(patient: dict) -> list[dict]:
    visits = patient.get("visits") or []
    return [v for v in visits if isinstance(v, dict)]


def _safe_medications(visit: dict) -> list[dict]:
    return _safe_dict_list(visit.get("medications"))


def _safe_dict_list(value: Any) -> list[dict]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _s(value: Any) -> str:
    """Convert to stripped string; return empty string for None."""
    if value is None:
        return ""
    return str(value).strip()


def _comma(items: tuple[str, ...] | list[str]) -> str:
    return ", ".join(items)


def _and(items: list[str] | tuple[str, ...]) -> str:
    """Join with Oxford-style 'and'."""
    lst = list(items)
    if not lst:
        return ""
    if len(lst) == 1:
        return lst[0]
    if len(lst) == 2:
        return f"{lst[0]} and {lst[1]}"
    return f"{', '.join(lst[:-1])}, and {lst[-1]}"


__all__ = [
    "RetrievalEnrichmentError",
    "build_retrieval_text",
    "build_all_retrieval_texts",
]
