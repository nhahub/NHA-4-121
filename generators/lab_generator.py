"""
generators/lab_generator.py

Deterministic v1.7 Lite lab-result generator.

RESPONSIBILITY
--------------
This module populates patient["visits"][i]["labs"] in-place for every visit
in a patient shell that was already built by visit_generator.py.

It does NOT generate:
    - medications          (→ generators/medication_generator.py)
    - allergy records      (→ generators/allergy_generator.py)
    - SOAP prose           (→ soap/soap_generator.py)
    - ChromaDB chunks      (→ ingestion/chunker.py)
    - ChromaDB metadata    (→ ingestion/metadata_builder.py)

BLUEPRINT CONTRACT
------------------
blueprint.lab_focus is the single source of truth for which lab types appear.
LAB_FOCUS_BY_CONDITION may be used for validation but must NOT be used to
auto-add labs that are absent from blueprint.lab_focus.

BP RULE
-------
Blood pressure is a vital sign.  It must never be stored as a lab.
BP_FORBIDDEN_LAB_TERMS is checked on every lab_type before generation.

DETERMINISM
-----------
Patient-specific value series are defined in _PATIENT_LAB_SERIES.
All other patients use a generic progression formula.
No random module is used anywhere in this file.
"""

from __future__ import annotations

from typing import Any, Final

from config.constants import (
    BP_FORBIDDEN_LAB_TERMS,
    FLAGS,
    LAB_FOCUS_BY_CONDITION,
    LAB_REFERENCE_RANGES,
    LAB_TYPES,
    LAB_UNITS,
    REQUIRED_LAB_FIELDS,
)
from config.patient_blueprints import BLUEPRINT_BY_ID, PatientBlueprint


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

LabRecord = dict[str, Any]


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------

class LabGenerationError(ValueError):
    """Raised when a blueprint cannot safely produce lab records."""


# ---------------------------------------------------------------------------
# Primary public API
# ---------------------------------------------------------------------------

def generate_labs_for_patient(
    patient: dict,
    blueprint: PatientBlueprint | None = None,
) -> dict:
    """Populate patient['visits'][i]['labs'] in-place and return patient.

    This is the standard integration point:

        generate_visits_for_patient(patient, blueprint)
        generate_medications_for_patient(patient, blueprint)
        generate_labs_for_patient(patient, blueprint)

    Args:
        patient:   Patient dict with visits already populated.
        blueprint: PatientBlueprint.  If None, looked up by patient_id.

    Returns:
        The same patient dict with labs populated.
    """
    if blueprint is None:
        pid = patient.get("patient_id", "")
        if pid not in BLUEPRINT_BY_ID:
            raise LabGenerationError(
                f"No blueprint found for patient_id='{pid}'."
            )
        blueprint = BLUEPRINT_BY_ID[pid]

    _validate_preconditions(patient, blueprint)

    for visit_index, visit in enumerate(patient["visits"]):
        labs = generate_labs_for_visit(
            blueprint=blueprint,
            visit_index=visit_index + 1,   # 1-based for progression logic
            visit_date=visit["visit_date"],
            visit_role=visit["visit_role"],
            clinical_event=visit.get("clinical_event", {}),
        )
        visit["labs"] = labs

    return patient


def generate_labs_for_visit(
    *,
    blueprint: PatientBlueprint,
    visit_index: int,
    visit_date: str,
    visit_role: str,
    clinical_event: dict,
) -> list[LabRecord]:
    """Generate lab records for one visit from blueprint.lab_focus.

    Args:
        blueprint:      PatientBlueprint dataclass.
        visit_index:    1-based visit index.
        visit_date:     ISO visit date string (accepted for interface stability;
                        not stored in lab records, which follow REQUIRED_LAB_FIELDS).
        visit_role:     Visit role string from visit_generator.
        clinical_event: Clinical event dict from visit_generator.

    Returns:
        List of lab record dicts.  Empty list for patients with no lab_focus.
    """
    del visit_date   # not stored in lab records per current schema contract

    if not blueprint.lab_focus:
        return []

    _validate_lab_focus(blueprint)

    labs: list[LabRecord] = []
    for lab_type in blueprint.lab_focus:
        value = _deterministic_lab_value(
            blueprint=blueprint,
            lab_type=lab_type,
            visit_index=visit_index,
            visit_role=visit_role,
            clinical_event=clinical_event,
        )
        record: LabRecord = {
            "lab_type":        lab_type,
            "value":           value,
            "unit":            LAB_UNITS[lab_type],
            "reference_range": LAB_REFERENCE_RANGES[lab_type],
            "flag":            determine_lab_flag(lab_type, value),
        }
        _validate_lab_record(record, patient_id=blueprint.patient_id)
        labs.append(record)

    return labs


def determine_lab_flag(lab_type: str, value: int | float) -> str:
    """Return NORMAL / HIGH / LOW for a generated lab value."""
    if lab_type not in LAB_TYPES:
        raise LabGenerationError(f"Unsupported lab_type for flagging: {lab_type}")

    v = float(value)
    if lab_type == "HbA1c":
        flag = "HIGH" if v > 5.6 else "NORMAL"
    elif lab_type == "FBG":
        flag = "HIGH" if v > 99 else "NORMAL"
    elif lab_type == "Creatinine":
        flag = "HIGH" if v > 1.2 else "NORMAL"
    elif lab_type == "Hemoglobin":
        flag = "LOW" if v < 12.0 else "NORMAL"
    elif lab_type == "Ferritin":
        flag = "LOW" if v < 30 else "NORMAL"
    elif lab_type == "LDL":
        flag = "HIGH" if v >= 100 else "NORMAL"
    else:
        raise LabGenerationError(f"Cannot determine flag for lab_type: {lab_type}")

    if flag not in FLAGS:
        raise LabGenerationError(f"Generated invalid lab flag: {flag}")
    return flag


def lab_has_trend(labs: list[LabRecord]) -> bool:
    """Return True if the list contains at least one trend-oriented lab."""
    _TREND_LABS: frozenset[str] = frozenset({
        "HbA1c", "FBG", "Creatinine", "Hemoglobin", "Ferritin", "LDL"
    })
    return any(str(lab.get("lab_type", "")) in _TREND_LABS for lab in labs)


# ---------------------------------------------------------------------------
# Backward-compatible aliases
# ---------------------------------------------------------------------------

def generate_labs(
    *,
    blueprint: PatientBlueprint,
    visit_index: int,
    visit_date: str,
    visit_role: str,
    clinical_event: dict,
) -> list[LabRecord]:
    """Backward-compatible alias for generate_labs_for_visit."""
    return generate_labs_for_visit(
        blueprint=blueprint,
        visit_index=visit_index,
        visit_date=visit_date,
        visit_role=visit_role,
        clinical_event=clinical_event,
    )


def build_labs_for_visit(
    *,
    blueprint: PatientBlueprint,
    visit_index: int,
    visit_date: str,
    visit_role: str,
    clinical_event: dict,
) -> list[LabRecord]:
    """Backward-compatible alias for orchestration code using build_* naming."""
    return generate_labs_for_visit(
        blueprint=blueprint,
        visit_index=visit_index,
        visit_date=visit_date,
        visit_role=visit_role,
        clinical_event=clinical_event,
    )


def validate_lab_focus(blueprint: PatientBlueprint) -> None:
    """Validate blueprint.lab_focus without generating patient JSON."""
    _validate_lab_focus(blueprint)


# ---------------------------------------------------------------------------
# Patient-specific lab value series
# ---------------------------------------------------------------------------
# Each entry maps patient_id → lab_type → tuple of values, one per visit.
# Indices are 0-based; visit_index - 1 selects the correct value.
# Values are synthetic and designed for retrieval-optimised story arcs.
# ---------------------------------------------------------------------------

_PATIENT_LAB_SERIES: Final[dict[str, dict[str, tuple[int | float, ...]]]] = {
    "PAT-MOD-001": {
        # T2DM · 3 visits · lab_improvement arc — clear downward HbA1c trend
        "HbA1c": (8.4, 7.6, 7.2),
        "FBG":   (172, 146, 132),
    },
    "PAT-MOD-004": {
        # IDA · 2 visits · poor_adherence — slight dip at visit 2 (missed doses)
        "Hemoglobin": (9.6, 9.4),
        "Ferritin":   (10, 9),
    },
    "PAT-MOD-006": {
        # Dyslipidemia · 3 visits · lab_improvement — LDL falls with Atorvastatin
        "LDL": (168, 156, 128),
    },
    "PAT-MOD-009": {
        # T2DM+GERD · 3 visits · irregular_followup — moderate HbA1c improvement
        "HbA1c": (8.1, 7.8, 7.4),
        "FBG":   (165, 154, 140),
    },
    "PAT-CHR-001": {
        # T2DM+HTN · 5 visits · medication_escalation
        # HbA1c worsens at visit 2 (adherence), improves after Glibenclamide added.
        "HbA1c":     (8.7, 9.0, 8.5, 8.1, 7.8),
        "FBG":       (181, 190, 176, 165, 154),
        "Creatinine": (0.9, 1.0, 1.0, 0.9, 0.9),
    },
    "PAT-CHR-002": {
        # T2DM+HTN+CKD · 5 visits · ckd_monitoring — Creatinine trend
        "HbA1c":     (8.4, 8.1, 7.8, 7.7, 7.5),
        "FBG":       (172, 162, 150, 145, 140),
        "Creatinine": (1.4, 1.5, 1.6, 1.5, 1.4),
    },
    "PAT-CHR-003": {
        # Asthma+HTN · 5 visits · emergency arc — only Creatinine for HTN context
        "Creatinine": (0.9, 0.9, 1.0, 1.0, 0.9),
    },
    "PAT-CHR-004": {
        # T2DM+Dyslipidemia · 5 visits · dual_lab_trend
        "HbA1c": (8.2, 8.4, 7.9, 7.5, 7.2),
        "FBG":   (166, 174, 158, 145, 134),
        "LDL":   (168, 162, 145, 125, 108),
    },
    "PAT-CHR-005": {
        # T2DM+HTN+CKD · 5 visits · hospitalization_recovery
        # Creatinine peaks around hospitalisation (visit 3).
        "HbA1c":     (8.6, 9.0, 8.5, 8.7, 8.0),
        "FBG":       (180, 194, 176, 184, 160),
        "Creatinine": (1.5, 1.6, 1.7, 1.8, 1.6),
    },
}

# Generic fallback for patients not in the explicit series.
_GENERIC_BASELINES: Final[dict[str, int | float]] = {
    "HbA1c":     8.2,
    "FBG":       166,
    "Creatinine": 0.9,
    "Hemoglobin": 9.8,
    "Ferritin":   12,
    "LDL":        158,
}

# Reduction per visit for improving trends (positive = decreases with visits).
_GENERIC_STEPS: Final[dict[str, int | float]] = {
    "HbA1c":      0.35,
    "FBG":        10,
    "Creatinine":  0.0,
    "Hemoglobin": -0.55,   # negative: value rises (improvement for IDA)
    "Ferritin":   -7,
    "LDL":        15,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _deterministic_lab_value(
    *,
    blueprint: PatientBlueprint,
    lab_type: str,
    visit_index: int,
    visit_role: str,
    clinical_event: dict,
) -> int | float:
    """Return the deterministic lab value for one lab_type at one visit."""
    explicit_series = _PATIENT_LAB_SERIES.get(blueprint.patient_id, {}).get(lab_type)
    if explicit_series is not None:
        idx = min(visit_index - 1, len(explicit_series) - 1)
        return _normalize(lab_type, explicit_series[idx])

    return _normalize(
        lab_type,
        _generic_lab_value(
            blueprint=blueprint,
            lab_type=lab_type,
            visit_index=visit_index,
            visit_role=visit_role,
            clinical_event=clinical_event,
        ),
    )


def _generic_lab_value(
    *,
    blueprint: PatientBlueprint,
    lab_type: str,
    visit_index: int,
    visit_role: str,
    clinical_event: dict,
) -> int | float:
    conditions     = set(blueprint.conditions)
    semantic_focus = blueprint.semantic_focus
    event_type     = str(clinical_event.get("event_type", ""))

    baseline = float(_GENERIC_BASELINES[lab_type])
    step     = float(_GENERIC_STEPS[lab_type])

    if lab_type == "Creatinine" and "CKD" in conditions:
        ckd_fallback = (1.4, 1.5, 1.6, 1.5, 1.4)
        return ckd_fallback[min(visit_index - 1, len(ckd_fallback) - 1)]

    if lab_type in {"HbA1c", "FBG", "LDL"}:
        value = baseline - step * (visit_index - 1)
        if semantic_focus in {"poor_adherence", "medication_escalation"} and visit_index == 2:
            value += 0.3 if lab_type == "HbA1c" else 10
        if event_type in {"hospitalization", "emergency_visit"}:
            value += 0.2 if lab_type == "HbA1c" else 8
        return value

    if lab_type in {"Hemoglobin", "Ferritin"}:
        value = baseline - step * (visit_index - 1)
        if semantic_focus == "poor_adherence" and visit_index == 2:
            value -= 0.3 if lab_type == "Hemoglobin" else 3
        return value

    return baseline


def _normalize(lab_type: str, value: int | float) -> int | float:
    if lab_type in {"HbA1c", "Creatinine", "Hemoglobin"}:
        return round(float(value), 1)
    if lab_type in {"FBG", "Ferritin", "LDL"}:
        return int(round(float(value)))
    raise LabGenerationError(f"Unsupported lab_type for normalization: {lab_type}")


def _validate_preconditions(patient: dict, blueprint: PatientBlueprint) -> None:
    pid = patient.get("patient_id", "")
    if pid != blueprint.patient_id:
        raise LabGenerationError(
            f"patient_id mismatch: patient='{pid}', blueprint='{blueprint.patient_id}'."
        )
    if not patient.get("visits"):
        raise LabGenerationError(
            f"{blueprint.patient_id}: patient has no visits. "
            "Run generate_visits_for_patient first."
        )


def _validate_lab_focus(blueprint: PatientBlueprint) -> None:
    """Check every lab_type in blueprint.lab_focus is valid."""
    if not blueprint.lab_focus:
        return

    seen: set[str] = set()
    for lab_type in blueprint.lab_focus:
        if lab_type in seen:
            raise LabGenerationError(
                f"{blueprint.patient_id}: duplicate lab_type '{lab_type}' in lab_focus."
            )
        seen.add(lab_type)
        _validate_lab_type(blueprint.patient_id, lab_type)

    # Cross-check against what the conditions support (warning-level validation).
    allowed: set[str] = set()
    for cond in blueprint.conditions:
        allowed.update(LAB_FOCUS_BY_CONDITION.get(cond, ()))
    if allowed:
        for lab_type in blueprint.lab_focus:
            if lab_type not in allowed:
                raise LabGenerationError(
                    f"{blueprint.patient_id}: lab_type '{lab_type}' in lab_focus is not "
                    f"supported by conditions {blueprint.conditions}."
                )


def _validate_lab_type(patient_id: str, lab_type: str) -> None:
    """Ensure a lab_type is valid and not a BP alias."""
    if lab_type not in LAB_TYPES:
        raise LabGenerationError(
            f"{patient_id}: unsupported lab_type '{lab_type}'."
        )
    lowered = lab_type.lower().replace("-", "_").replace(" ", "_")
    for forbidden in BP_FORBIDDEN_LAB_TERMS:
        if lowered == forbidden.lower().replace("-", "_").replace(" ", "_"):
            raise LabGenerationError(
                f"{patient_id}: attempted to store blood pressure as a lab: '{lab_type}'."
            )
    if lab_type not in LAB_UNITS:
        raise LabGenerationError(f"Missing unit for lab_type: '{lab_type}'.")
    if lab_type not in LAB_REFERENCE_RANGES:
        raise LabGenerationError(f"Missing reference range for lab_type: '{lab_type}'.")


def _validate_lab_record(lab: LabRecord, *, patient_id: str) -> None:
    """Check one lab record satisfies REQUIRED_LAB_FIELDS and value rules."""
    missing = [f for f in REQUIRED_LAB_FIELDS if f not in lab]
    if missing:
        raise LabGenerationError(
            f"{patient_id}: lab record missing required fields: {missing}."
        )
    lab_type = str(lab["lab_type"])
    _validate_lab_type(patient_id, lab_type)

    if lab["unit"] != LAB_UNITS[lab_type]:
        raise LabGenerationError(
            f"{patient_id}: lab {lab_type} invalid unit '{lab['unit']}'."
        )
    if lab["reference_range"] != LAB_REFERENCE_RANGES[lab_type]:
        raise LabGenerationError(
            f"{patient_id}: lab {lab_type} invalid reference_range."
        )
    if lab["flag"] not in FLAGS:
        raise LabGenerationError(
            f"{patient_id}: lab {lab_type} invalid flag '{lab['flag']}'."
        )
    if not isinstance(lab["value"], (int, float)):
        raise LabGenerationError(
            f"{patient_id}: lab {lab_type} value must be numeric."
        )
