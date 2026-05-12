"""
soap/soap_generator.py

SOAP narrative generation support.

This implementation is deterministic and offline. It generates SOAP narrative
text only from existing structured data. It never selects medications, labs,
diagnoses, vitals, or conditions.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from config.constants import DATE_FORMAT


def add_soap_notes_to_patient(patient: dict[str, Any]) -> dict[str, Any]:
    """
    Return a patient copy with SOAP notes populated for each visit.

    Structured facts are not modified.
    """
    updated = deepcopy(patient)

    for visit in updated.get("visits", []):
        visit["soap_note"] = generate_soap_note(patient=updated, visit=visit)

    return updated


def generate_soap_note(
    patient: dict[str, Any],
    visit: dict[str, Any],
) -> dict[str, str]:
    """
    Generate SOAP sections from existing structured data only.
    """
    demographics = patient["demographics"]
    conditions = patient.get("conditions", [])
    vitals = visit.get("vitals", {})
    labs = visit.get("labs", [])
    medications = visit.get("medications", [])

    age = _age_at_visit(
        demographics["date_of_birth"],
        visit["visit_date"],
    )

    condition_text = _format_list(conditions, empty_text="no chronic conditions")
    lab_text = _format_labs(labs)
    medication_text = _format_medications(medications)
    prior_text = (
        f"Prior visit reference is {visit['prior_visit_id']}."
        if visit.get("prior_visit_id")
        else "This is the first recorded visit in the synthetic record."
    )

    subjective = (
        f"The synthetic record documents a {age}-year-old {demographics['sex']} patient "
        f"attending a {visit['visit_type']} visit. The structured condition list records "
        f"{condition_text}. The note is generated only from stored synthetic facts and does "
        f"not add diagnosis, prediction, or clinical judgment beyond the record."
    )

    objective = (
        f"Objective structured data records blood pressure "
        f"{vitals.get('bp_systolic')}/{vitals.get('bp_diastolic')} mmHg, heart rate "
        f"{vitals.get('heart_rate')} bpm, weight {vitals.get('weight_kg')} kg, and BMI "
        f"{vitals.get('bmi')}. Laboratory data for this visit: {lab_text}. "
        f"Linked document references: {_format_list(visit.get('linked_documents', []))}."
    )

    assessment = (
        f"The assessment section summarizes only documented diagnoses for this visit: "
        f"{_format_list(visit.get('diagnoses', []), empty_text='no chronic diagnosis listed')}. "
        f"The visit remains grounded in the structured JSON record and does not infer "
        f"unstated conditions."
    )

    plan = (
        f"The documented plan records the whitelisted medication list exactly as stored: "
        f"{medication_text}. {prior_text} Follow-up context should be interpreted only "
        f"as part of this synthetic academic dataset, not as medical advice."
    )

    return {
        "subjective": subjective,
        "objective": objective,
        "assessment": assessment,
        "plan": plan,
    }


def _format_labs(labs: list[dict[str, Any]]) -> str:
    if not labs:
        return "no lab results recorded"

    return "; ".join(
        f"{lab['lab_type']} {lab['value']} {lab['unit']} ({lab['flag']})"
        for lab in labs
    )


def _format_medications(medications: list[dict[str, Any]]) -> str:
    if not medications:
        return "no active whitelisted medications recorded"

    return "; ".join(
        f"{med['medication_name']} {med['dose']} "
        f"{med['frequency']} via {med['route']}"
        for med in medications
    )


def _format_list(values: list[Any], empty_text: str = "none") -> str:
    if not values:
        return empty_text

    return ", ".join(str(value) for value in values)


def _age_at_visit(date_of_birth: str, visit_date: str) -> int:
    dob = datetime.strptime(date_of_birth, DATE_FORMAT).date()
    visit = datetime.strptime(visit_date, DATE_FORMAT).date()

    years = visit.year - dob.year
    before_birthday = (visit.month, visit.day) < (dob.month, dob.day)
    return years - int(before_birthday)