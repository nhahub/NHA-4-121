"""
generators/medication_generator.py

Deterministic medication generation from the locked whitelist only.

This module does not prescribe or recommend medication. It creates synthetic,
predefined medication records for academic testing.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from config.constants import MEDICATION_WHITELIST


def add_medications_to_patient(patient: dict[str, Any]) -> dict[str, Any]:
    """
    Return a patient copy with visit-level medication lists.

    Medications are deterministic and whitelisted.
    """
    updated = deepcopy(patient)
    conditions = set(updated.get("conditions", []))

    for index, visit in enumerate(updated["visits"]):
        visit["medications"] = _medications_for_visit(
            conditions=conditions,
            visit_date=visit["visit_date"],
            visit_index=index,
            patient_id=updated["patient_id"],
        )

    return updated


def _medications_for_visit(
    conditions: set[str],
    visit_date: str,
    visit_index: int,
    patient_id: str,
) -> list[dict[str, Any]]:
    medications: list[dict[str, Any]] = []

    if "T2DM" in conditions:
        medications.append(_medication("Metformin", visit_date))

        if patient_id == "PAT-CHR-001" and visit_index >= 2:
            medications.append(_medication("Glibenclamide", visit_date))

    if "HTN" in conditions:
        medications.append(_medication("Lisinopril", visit_date))

        if patient_id == "PAT-CHR-001" and visit_index >= 3:
            medications.append(_medication("Amlodipine", visit_date))

    if "Asthma" in conditions:
        medications.append(_medication("Salbutamol inhaler", visit_date))

        if visit_index >= 1:
            medications.append(_medication("Budesonide inhaler", visit_date))

    if "IDA" in conditions:
        stop_date = None if visit_index < 3 else visit_date
        medications.append(_medication("Ferrous sulfate", visit_date, stop_date=stop_date))

    if "GERD" in conditions:
        medications.append(_medication("Omeprazole", visit_date))

    return medications


def _medication(
    medication_name: str,
    start_date: str,
    stop_date: str | None = None,
) -> dict[str, Any]:
    if medication_name not in MEDICATION_WHITELIST:
        raise ValueError(f"Medication is not whitelisted: {medication_name}")

    spec = MEDICATION_WHITELIST[medication_name]

    return {
        "medication_name": medication_name,
        "medication_class": spec["medication_class"],
        "dose": spec["default_dose"],
        "frequency": spec["frequency"],
        "route": spec["route"],
        "start_date": start_date,
        "stop_date": stop_date,
    }