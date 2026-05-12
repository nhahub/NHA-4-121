"""
generators/visit_generator.py

Visit timeline and vitals generation.

Important BP rule:
Blood pressure is generated only inside visit["vitals"].
This module never writes BP into labs, metadata, or any other field.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from config.constants import (
    ATTENDING_PHYSICIANS,
    DATE_FORMAT,
    EMPTY_SOAP_NOTE,
    REQUIRED_VITAL_FIELDS,
    TIER_TO_ID_PREFIX,
    VISIT_DATE_OFFSETS_DAYS,
)
from generators.patient_generator import PatientBlueprint


def add_visits_to_patient(
    patient: dict[str, Any],
    blueprint: PatientBlueprint,
) -> dict[str, Any]:
    """
    Return a copy of patient with deterministic visits added.

    Existing patient is not modified in-place.
    """
    updated = deepcopy(patient)
    tier_prefix = TIER_TO_ID_PREFIX[blueprint.tier]
    patient_number = blueprint.patient_id.split("-")[-1]
    first_date = datetime.strptime(blueprint.first_visit_date, DATE_FORMAT).date()

    visits: list[dict[str, Any]] = []
    previous_visit_id: str | None = None

    for index in range(blueprint.visit_count):
        visit_number = index + 1
        visit_date = _visit_date_for_tier(first_date, blueprint.tier, index)
        visit_id = f"VST-{tier_prefix}-{patient_number}-{visit_number:03d}"
        document_id = f"DOC-{tier_prefix}-{patient_number}-{visit_number:03d}"

        visit = {
            "visit_id": visit_id,
            "visit_date": visit_date.strftime(DATE_FORMAT),
            "visit_type": _visit_type_for_tier(blueprint.tier, index),
            "attending_physician": ATTENDING_PHYSICIANS[index % len(ATTENDING_PHYSICIANS)],
            "diagnoses": list(blueprint.conditions),
            "vitals": _generate_vitals(blueprint, index),
            "labs": [],
            "medications": [],
            "soap_note": dict(EMPTY_SOAP_NOTE),
            "linked_documents": [document_id],
            "prior_visit_id": previous_visit_id,
        }

        _assert_vitals_shape(visit["vitals"])
        visits.append(visit)
        previous_visit_id = visit_id

    updated["visits"] = visits
    return updated


def _visit_date_for_tier(
    first_date,
    tier: str,
    index: int,
):
    """
    Generate deterministic visit date using tier-specific offset patterns.

    The offset patterns live in config/constants.py so visit count and
    visit spacing stay synchronized.
    """
    if tier not in VISIT_DATE_OFFSETS_DAYS:
        raise ValueError(f"Unsupported tier: {tier}")

    offsets = VISIT_DATE_OFFSETS_DAYS[tier]

    if index >= len(offsets):
        raise ValueError(
            f"Visit index {index} is out of range for tier '{tier}'. "
            f"Configured offsets support {len(offsets)} visits."
        )

    return first_date + timedelta(days=offsets[index])


def _visit_type_for_tier(tier: str, index: int) -> str:
    """Assign allowed visit_type enum values."""
    if index == 0:
        return "initial"

    if tier == "chronic" and index == 3:
        return "hospitalization"

    return "follow_up"


def _generate_vitals(blueprint: PatientBlueprint, index: int) -> dict[str, float | int]:
    """
    Generate realistic but deterministic vital signs within V3 bounds.

    BP remains only in this vitals object.
    """
    conditions = set(blueprint.conditions)

    if blueprint.tier == "normal":
        return {
            "bp_systolic": 118 + index,
            "bp_diastolic": 76 + index,
            "heart_rate": 74 - index,
            "weight_kg": 74.0 if blueprint.sex == "male" else 62.0,
            "bmi": 23.8 if blueprint.sex == "male" else 22.6,
        }

    if "HTN" in conditions:
        systolic_values = [152, 148, 144, 158, 140, 136]
        diastolic_values = [94, 92, 90, 96, 88, 84]
    else:
        systolic_values = [126, 124, 122, 120, 120, 118]
        diastolic_values = [82, 80, 78, 78, 76, 76]

    return {
        "bp_systolic": systolic_values[min(index, len(systolic_values) - 1)],
        "bp_diastolic": diastolic_values[min(index, len(diastolic_values) - 1)],
        "heart_rate": 82 - min(index, 4),
        "weight_kg": _weight_for_patient(blueprint, index),
        "bmi": _bmi_for_patient(blueprint, index),
    }


def _weight_for_patient(blueprint: PatientBlueprint, index: int) -> float:
    if blueprint.patient_id == "PAT-MOD-001":
        return round(88.0 - index * 1.2, 1)

    if blueprint.patient_id == "PAT-MOD-002":
        return round(66.0 - index * 0.2, 1)

    if blueprint.patient_id == "PAT-CHR-001":
        return round(91.0 - index * 0.8, 1)

    return 70.0


def _bmi_for_patient(blueprint: PatientBlueprint, index: int) -> float:
    if blueprint.patient_id == "PAT-MOD-001":
        return round(29.1 - index * 0.3, 1)

    if blueprint.patient_id == "PAT-MOD-002":
        return round(24.8 - index * 0.1, 1)

    if blueprint.patient_id == "PAT-CHR-001":
        return round(30.2 - index * 0.2, 1)

    return 23.5


def _assert_vitals_shape(vitals: dict[str, Any]) -> None:
    """Internal safety check: vitals must contain only expected vital fields."""
    missing = set(REQUIRED_VITAL_FIELDS) - set(vitals.keys())
    if missing:
        raise ValueError(f"Generated vitals missing fields: {sorted(missing)}")

    forbidden_lab_like_keys = {"lab_type", "flag", "reference_range"}
    overlap = forbidden_lab_like_keys.intersection(vitals.keys())
    if overlap:
        raise ValueError(f"Generated vitals contain lab-like keys: {sorted(overlap)}")