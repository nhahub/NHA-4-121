"""
generators/allergy_generator.py

Deterministic allergy registry generation.

The allergy registry is manually designed so that no allergy allergen exactly
matches a generated medication name. V2 still validates this after generation.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def add_allergies_to_patient(patient: dict[str, Any]) -> dict[str, Any]:
    """
    Return a patient copy with deterministic allergy_registry entries.
    """
    updated = deepcopy(patient)

    if not updated.get("visits"):
        updated["allergy_registry"] = []
        return updated

    first_visit = updated["visits"][0]
    patient_id = updated["patient_id"]

    allergy_map: dict[str, list[dict[str, Any]]] = {
        "PAT-NRM-001": [],
        "PAT-NRM-002": [
            {
                "allergen": "Penicillin",
                "reaction": "skin rash",
                "severity": "mild",
                "recorded_date": first_visit["visit_date"],
                "source_visit_id": first_visit["visit_id"],
            }
        ],
        "PAT-MOD-001": [
            {
                "allergen": "Sulfa",
                "reaction": "itching",
                "severity": "moderate",
                "recorded_date": first_visit["visit_date"],
                "source_visit_id": first_visit["visit_id"],
            }
        ],
        "PAT-MOD-002": [],
        "PAT-CHR-001": [
            {
                "allergen": "Penicillin",
                "reaction": "generalized rash",
                "severity": "moderate",
                "recorded_date": first_visit["visit_date"],
                "source_visit_id": first_visit["visit_id"],
            }
        ],
    }

    updated["allergy_registry"] = allergy_map.get(patient_id, [])
    return updated