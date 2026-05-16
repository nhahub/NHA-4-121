"""
generators/allergy_generator.py

Deterministic allergy registry generation.

The allergy registry is generated from safe non-medication allergens so that
no allergy allergen exactly matches a generated medication name.

V2 validation still verifies medication/allergy conflicts after generation.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from config.constants import (
    ALLERGY_REACTION_MAP,
    ALLERGY_SEVERITY_MAP,
    MEDICATION_NAMES,
    SAFE_ALLERGEN_POOL,
)


def add_allergies_to_patient(patient: dict[str, Any]) -> dict[str, Any]:
    """
    Return a patient copy with deterministic allergy_registry entries.

    Allergy records are patient-level, but each record references the first
    visit as its source_visit_id for citation and timeline anchoring.
    """
    updated = deepcopy(patient)

    visits = updated.get("visits", [])
    if not visits:
        updated["allergy_registry"] = []
        return updated

    first_visit = visits[0]
    patient_id = str(updated["patient_id"])

    updated["allergy_registry"] = _allergies_for_patient(
        patient_id=patient_id,
        recorded_date=str(first_visit["visit_date"]),
        source_visit_id=str(first_visit["visit_id"]),
    )

    return updated


def _allergies_for_patient(
    patient_id: str,
    recorded_date: str,
    source_visit_id: str,
) -> list[dict[str, Any]]:
    """
    Generate deterministic allergy records for a patient.

    The pattern intentionally gives some patients no allergies and gives
    selected patients one safe allergy record. This supports allergy retrieval
    without making every patient artificially allergic.
    """
    patient_number = _patient_number(patient_id)

    # Deterministic sparse distribution:
    # approximately 40% of patients receive one documented allergy.
    if patient_number % 5 in {1, 3, 4}:
        return []

    allergen = _select_safe_allergen(patient_number)

    return [
        _allergy_record(
            allergen=allergen,
            recorded_date=recorded_date,
            source_visit_id=source_visit_id,
        )
    ]


def _select_safe_allergen(patient_number: int) -> str:
    """
    Select a deterministic allergen from SAFE_ALLERGEN_POOL.

    Medication names are explicitly excluded to protect V2.
    """
    medication_names_lower = {name.lower() for name in MEDICATION_NAMES}
    safe_allergens = [
        allergen
        for allergen in SAFE_ALLERGEN_POOL
        if allergen.lower() not in medication_names_lower
    ]

    if not safe_allergens:
        raise ValueError("SAFE_ALLERGEN_POOL contains no medication-safe allergens.")

    return safe_allergens[(patient_number - 1) % len(safe_allergens)]


def _allergy_record(
    allergen: str,
    recorded_date: str,
    source_visit_id: str,
) -> dict[str, Any]:
    """
    Build a schema-compatible allergy record.
    """
    if allergen not in ALLERGY_REACTION_MAP:
        raise ValueError(f"Missing allergy reaction mapping for allergen: {allergen}")

    if allergen not in ALLERGY_SEVERITY_MAP:
        raise ValueError(f"Missing allergy severity mapping for allergen: {allergen}")

    return {
        "allergen": allergen,
        "reaction": ALLERGY_REACTION_MAP[allergen],
        "severity": ALLERGY_SEVERITY_MAP[allergen],
        "recorded_date": recorded_date,
        "source_visit_id": source_visit_id,
    }


def _patient_number(patient_id: str) -> int:
    """
    Extract the numeric suffix from PAT-NRM-001 / PAT-MOD-001 / PAT-CHR-001.
    """
    return int(patient_id.split("-")[-1])