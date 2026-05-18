"""
generators/medication_generator.py

Deterministic medication generation from the locked whitelist only.

This module does not prescribe or recommend medication. It creates synthetic,
predefined medication records for academic testing.

Freeze decision:
Medication generation is condition-driven and deterministic.
Medication records must use MEDICATION_WHITELIST only.

Important timeline rule:
A medication's start_date is the date it first appears in the synthetic record,
not the current visit date repeated on every visit. This preserves a clean
medication timeline for retrieval questions such as "when was this medication
started?" and "what medication was added later?".
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

    Timeline behavior:
    - Baseline medications keep the first visit date as start_date.
    - Add-on medications keep the escalation visit date as start_date.
    - Ferrous sulfate keeps the first visit date as start_date and receives
      stop_date only at the configured stopping visit.
    """
    updated = deepcopy(patient)
    conditions = set(updated.get("conditions", []))
    visits = updated.get("visits", [])

    if not isinstance(visits, list):
        raise ValueError("patient['visits'] must be a list before medication generation.")

    visit_dates = _visit_dates_from_visits(visits)

    for index, visit in enumerate(visits):
        if not isinstance(visit, dict):
            raise ValueError(f"Visit at index {index} must be an object.")

        visit["medications"] = _medications_for_visit(
            conditions=conditions,
            visit_dates=visit_dates,
            visit_index=index,
        )

    return updated


def _medications_for_visit(
    conditions: set[str],
    visit_dates: tuple[str, ...],
    visit_index: int,
) -> list[dict[str, Any]]:
    """
    Generate deterministic medications for one visit.

    This function uses condition presence, visit dates, and visit index only.
    It does not use allergies, vitals, labs, or LLM output.
    """
    medications: list[dict[str, Any]] = []

    first_visit_date = _date_at_index(visit_dates, 0)

    if "T2DM" in conditions:
        medications.append(_medication("Metformin", first_visit_date))

        if _has_reached_visit(visit_dates, T2DM_ADD_ON_VISIT_INDEX, visit_index):
            medications.append(
                _medication(
                    "Glibenclamide",
                    _date_at_index(visit_dates, T2DM_ADD_ON_VISIT_INDEX),
                )
            )

    if "HTN" in conditions:
        medications.append(_medication("Lisinopril", first_visit_date))

        if _has_reached_visit(visit_dates, HTN_SECOND_DRUG_VISIT_INDEX, visit_index):
            medications.append(
                _medication(
                    "Amlodipine",
                    _date_at_index(visit_dates, HTN_SECOND_DRUG_VISIT_INDEX),
                )
            )

    if "Asthma" in conditions:
        medications.append(_medication("Salbutamol inhaler", first_visit_date))

        if _has_reached_visit(visit_dates, ASTHMA_CONTROLLER_VISIT_INDEX, visit_index):
            medications.append(
                _medication(
                    "Budesonide inhaler",
                    _date_at_index(visit_dates, ASTHMA_CONTROLLER_VISIT_INDEX),
                )
            )

    if "IDA" in conditions and visit_index <= IDA_STOP_AFTER_VISIT_INDEX:
        stop_date = None
        if visit_index == IDA_STOP_AFTER_VISIT_INDEX and _index_exists(
            visit_dates,
            IDA_STOP_AFTER_VISIT_INDEX,
        ):
            stop_date = _date_at_index(visit_dates, IDA_STOP_AFTER_VISIT_INDEX)

        medications.append(
            _medication(
                "Ferrous sulfate",
                first_visit_date,
                stop_date=stop_date,
            )
        )

    if "GERD" in conditions:
        medications.append(_medication("Omeprazole", first_visit_date))

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


def _visit_dates_from_visits(visits: list[Any]) -> tuple[str, ...]:
    """
    Extract visit dates in visit order.

    The visit generator is responsible for chronological ordering. This module
    preserves that order and uses the dates to anchor medication timelines.
    """
    visit_dates: list[str] = []

    for index, visit in enumerate(visits):
        if not isinstance(visit, dict):
            raise ValueError(f"Visit at index {index} must be an object.")

        visit_date = visit.get("visit_date")
        if not visit_date:
            raise ValueError(f"Visit at index {index} is missing visit_date.")

        visit_dates.append(str(visit_date))

    return tuple(visit_dates)


def _has_reached_visit(
    visit_dates: tuple[str, ...],
    target_index: int,
    current_index: int,
) -> bool:
    """
    Return True when the current visit has reached an escalation index.

    If the dataset has fewer visits than the configured escalation point, the
    add-on medication is not generated.
    """
    return _index_exists(visit_dates, target_index) and current_index >= target_index


def _index_exists(values: tuple[str, ...], index: int) -> bool:
    """Return True when index exists in a tuple."""
    return 0 <= index < len(values)


def _date_at_index(visit_dates: tuple[str, ...], index: int) -> str:
    """Return visit date at a specific index or fail with a clear message."""
    if not _index_exists(visit_dates, index):
        raise ValueError(
            f"Medication timeline requested visit index {index}, "
            f"but only {len(visit_dates)} visits exist."
        )

    return visit_dates[index]
