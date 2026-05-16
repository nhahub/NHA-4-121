"""
generators/medication_generator.py

Deterministic medication generation from the locked whitelist only.

This module does not prescribe or recommend medication. It creates synthetic,
predefined medication records for academic testing.

Freeze decision:
Medication generation is condition-driven and deterministic.
Medication records must use MEDICATION_WHITELIST only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from config.constants import (
    ASTHMA_CONTROLLER_VISIT_INDEX,
    HTN_SECOND_DRUG_VISIT_INDEX,
    IDA_STOP_AFTER_VISIT_INDEX,
    MEDICATION_WHITELIST,
    T2DM_ADD_ON_VISIT_INDEX,
)


def add_medications_to_patient(patient: dict[str, Any]) -> dict[str, Any]:
    """
    Return a patient copy with visit-level medication lists.

    Medications are deterministic, condition-driven, and whitelisted.
    """
    updated = deepcopy(patient)
    conditions = set(updated.get("conditions", []))

    for index, visit in enumerate(updated.get("visits", [])):
        visit["medications"] = _medications_for_visit(
            conditions=conditions,
            visit_date=str(visit["visit_date"]),
            visit_index=index,
        )

    return updated


def _medications_for_visit(
    conditions: set[str],
    visit_date: str,
    visit_index: int,
) -> list[dict[str, Any]]:
    """
    Generate deterministic medications for one visit.

    This function uses condition presence and visit index only.
    It does not use allergies, vitals, labs, or LLM output.
    """
    medications: list[dict[str, Any]] = []

    if "T2DM" in conditions:
        medications.append(_medication("Metformin", visit_date))

        if visit_index >= T2DM_ADD_ON_VISIT_INDEX:
            medications.append(_medication("Glibenclamide", visit_date))

    if "HTN" in conditions:
        medications.append(_medication("Lisinopril", visit_date))

        if visit_index >= HTN_SECOND_DRUG_VISIT_INDEX:
            medications.append(_medication("Amlodipine", visit_date))

    if "Asthma" in conditions:
        medications.append(_medication("Salbutamol inhaler", visit_date))

        if visit_index >= ASTHMA_CONTROLLER_VISIT_INDEX:
            medications.append(_medication("Budesonide inhaler", visit_date))

    if "IDA" in conditions and visit_index <= IDA_STOP_AFTER_VISIT_INDEX:
        stop_date = visit_date if visit_index == IDA_STOP_AFTER_VISIT_INDEX else None
        medications.append(
            _medication(
                "Ferrous sulfate",
                visit_date,
                stop_date=stop_date,
            )
        )

    if "GERD" in conditions:
        medications.append(_medication("Omeprazole", visit_date))

    return medications


def _medication(
    medication_name: str,
    start_date: str,
    stop_date: str | None = None,
) -> dict[str, Any]:
    """
    Build a schema-compatible medication object from MEDICATION_WHITELIST.
    """
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