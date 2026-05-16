"""
generators/visit_generator.py

Visit timeline and vitals generation.

Important BP rule:
Blood pressure is generated only inside visit["vitals"].
This module never writes BP into labs, metadata, or any other field.

Freeze decision:
Vitals are condition-driven and deterministic.
Vitals do NOT depend on medications during the current implementation freeze.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any

from config.constants import (
    ATTENDING_PHYSICIANS,
    DATE_FORMAT,
    EMPTY_SOAP_NOTE,
    HTN_BASELINE_BP_PROFILES,
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
            "visit_type": _visit_type_for_blueprint(blueprint, index),
            "attending_physician": ATTENDING_PHYSICIANS[
                index % len(ATTENDING_PHYSICIANS)
            ],
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
    first_date: date,
    tier: str,
    index: int,
) -> date:
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


def _visit_type_for_blueprint(blueprint: PatientBlueprint, index: int) -> str:
    """
    Assign deterministic allowed visit_type values.

    Rules:
    - first visit is always initial
    - asthma patients receive one emergency visit
    - chronic patients receive one hospitalization visit
    - all other visits are follow_up
    """
    if index == 0:
        return "initial"

    conditions = set(blueprint.conditions)

    if "Asthma" in conditions and index == 2:
        return "emergency"

    if blueprint.tier == "chronic" and index == 3:
        return "hospitalization"

    return "follow_up"


def _generate_vitals(blueprint: PatientBlueprint, index: int) -> dict[str, float | int]:
    """
    Generate realistic but deterministic vital signs within V3 bounds.

    Vitals are condition-driven and do not depend on medication records.
    BP remains only in this vitals object.
    """
    bp_systolic, bp_diastolic = _bp_for_patient(blueprint, index)

    return {
        "bp_systolic": bp_systolic,
        "bp_diastolic": bp_diastolic,
        "heart_rate": _heart_rate_for_patient(blueprint, index),
        "weight_kg": _weight_for_patient(blueprint, index),
        "bmi": _bmi_for_patient(blueprint, index),
    }


def _bp_for_patient(blueprint: PatientBlueprint, index: int) -> tuple[int, int]:
    """
    Generate deterministic BP values.

    BP must remain only inside visit["vitals"].
    """
    patient_number = int(blueprint.patient_id.split("-")[-1])
    conditions = set(blueprint.conditions)

    if "HTN" in conditions:
        profile = HTN_BASELINE_BP_PROFILES[
            (patient_number - 1) % len(HTN_BASELINE_BP_PROFILES)
        ]

        baseline_systolic = int(profile["systolic"])
        baseline_diastolic = int(profile["diastolic"])

        systolic = baseline_systolic - (2 * min(index, 8))
        diastolic = baseline_diastolic - min(index, 8)

        if blueprint.tier == "chronic" and index == 3:
            systolic += 8
            diastolic += 4

        return max(systolic, 128), max(diastolic, 78)

    systolic = 122 + (patient_number % 4) - min(index, 5)
    diastolic = 78 + (patient_number % 3) - min(index, 4)

    return max(systolic, 116), max(diastolic, 74)


def _heart_rate_for_patient(blueprint: PatientBlueprint, index: int) -> int:
    """
    Generate deterministic heart rate within V3 bounds.
    """
    patient_number = int(blueprint.patient_id.split("-")[-1])
    conditions = set(blueprint.conditions)

    if "Asthma" in conditions and index == 2:
        return 96

    if blueprint.tier == "normal":
        return 72 + (patient_number % 5) - min(index, 2)

    if blueprint.tier == "chronic":
        return 84 - min(index, 5)

    return 82 - min(index, 4)


def _weight_for_patient(blueprint: PatientBlueprint, index: int) -> float:
    """
    Generate deterministic weight progression by condition, tier, sex, and visit index.

    This improves dataset diversity without medication dependency.
    """
    patient_number = int(blueprint.patient_id.split("-")[-1])
    conditions = set(blueprint.conditions)

    base_weight = 74.0 if blueprint.sex == "male" else 62.0

    if "T2DM" in conditions:
        base_weight += 4.0

    if "HTN" in conditions:
        base_weight += 2.0

    if "CKD" in conditions:
        base_weight += 1.0

    if "IDA" in conditions:
        base_weight -= 3.0

    if blueprint.tier == "chronic":
        base_weight += 3.0

    if "CKD" in conditions:
        progression = min(index, 8) * 0.7
    elif blueprint.tier in {"moderate", "chronic"}:
        progression = min(index, 6) * 0.4
    else:
        progression = 0.0

    variation = (patient_number % 4) * 1.1

    return round(base_weight + variation - progression, 1)


def _bmi_for_patient(blueprint: PatientBlueprint, index: int) -> float:
    """
    Generate deterministic BMI progression by condition, tier, sex, and visit index.
    """
    patient_number = int(blueprint.patient_id.split("-")[-1])
    conditions = set(blueprint.conditions)

    base_bmi = 23.6 if blueprint.sex == "male" else 22.4

    if "T2DM" in conditions:
        base_bmi += 1.2

    if "HTN" in conditions:
        base_bmi += 0.8

    if "CKD" in conditions:
        base_bmi += 0.5

    if "IDA" in conditions:
        base_bmi -= 1.0

    if blueprint.tier == "chronic":
        base_bmi += 1.0

    progression = min(index, 8) * 0.12
    variation = (patient_number % 3) * 0.25

    return round(base_bmi + variation - progression, 1)


def _assert_vitals_shape(vitals: dict[str, Any]) -> None:
    """
    Internal safety check: vitals must contain exactly the expected vital fields.
    """
    expected_fields = set(REQUIRED_VITAL_FIELDS)
    actual_fields = set(vitals.keys())

    missing = expected_fields - actual_fields
    if missing:
        raise ValueError(f"Generated vitals missing fields: {sorted(missing)}")

    extra = actual_fields - expected_fields
    if extra:
        raise ValueError(f"Generated vitals contain unexpected fields: {sorted(extra)}")

    forbidden_lab_like_keys = {"lab_type", "flag", "reference_range"}
    overlap = forbidden_lab_like_keys.intersection(actual_fields)
    if overlap:
        raise ValueError(f"Generated vitals contain lab-like keys: {sorted(overlap)}")