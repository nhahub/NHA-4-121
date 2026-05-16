"""
soap/soap_renderers.py

Deterministic SOAP fact rendering utilities.

Phase 1 / Phase 2 preparation purpose:
    Centralize formatting and fact-context construction for SOAP generation
    without changing generated SOAP wording, formatting, schema behavior,
    validation behavior, or RAG ingestion behavior.

Important safety rules:
    - No LLM calls.
    - No randomization.
    - No template diversification logic.
    - No style profile logic.
    - No medical logic changes.
    - No normalization changes.
    - No wording changes.
    - Preserve deterministic SOAP output behavior.

This module owns fact extraction and exact formatting only.

Architecture role:
    soap_contract.py   -> owns shared SOAP sections/types/template dataclass
    soap_renderers.py  -> owns fact extraction and exact formatting
    soap_templates.py  -> owns template registry only
    soap_selector.py   -> owns deterministic template selection only
    soap_generator.py  -> owns final SOAP assembly/rendering
    soap_auditor.py    -> owns safety checks

Important:
    SoapFactContext intentionally remains in this module because it represents
    rendered fact output from structured patient JSON, not the shared template
    contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

from config.constants import DATE_FORMAT


class SoapFactContext(TypedDict):
    """
    Rendered and raw facts used by deterministic SOAP generation.

    This context intentionally contains both:
        1. Raw structured values from the patient JSON.
        2. Pre-rendered strings used by SOAP generation.

    Safety rule:
        Values in this context must preserve the exact formatting behavior
        of the deterministic SOAP pipeline.
    """

    # Identifiers
    patient_id: str
    visit_id: str

    # Routing / selection facts
    tier: str

    # Raw demographics / visit facts
    date_of_birth: str
    visit_date: str
    sex: str
    visit_type: str
    conditions: list[Any]
    diagnoses: list[Any]
    vitals: dict[str, Any]
    labs: list[dict[str, Any]]
    medications: list[dict[str, Any]]
    linked_documents: list[Any]
    prior_visit_id: Any

    # Rendered patient / visit facts
    age: int
    condition_text: str
    diagnosis_text: str
    lab_text: str
    medication_text: str
    linked_documents_text: str
    prior_text: str

    # Rendered / directly accessed vital components
    bp_systolic: Any
    bp_diastolic: Any
    heart_rate: Any
    weight_kg: Any
    bmi: Any
    bp_text: str


def build_fact_context(
    patient: dict[str, Any],
    visit: dict[str, Any],
) -> SoapFactContext:
    """
    Build a deterministic fact context from structured patient and visit data.

    This function centralizes fact extraction and formatting for SOAP generation.

    It must not:
        - modify patient data,
        - infer missing medical facts,
        - normalize values,
        - change wording,
        - change formatting,
        - introduce template variation,
        - perform template selection,
        - call an LLM.

    Args:
        patient: Patient JSON dictionary.
        visit: Visit dictionary from patient["visits"].

    Returns:
        SoapFactContext containing raw and rendered facts for SOAP generation.
    """
    demographics = patient["demographics"]
    metadata = patient["metadata"]

    conditions = patient.get("conditions", [])
    diagnoses = visit.get("diagnoses", [])
    vitals = visit.get("vitals", {})
    labs = visit.get("labs", [])
    medications = visit.get("medications", [])
    linked_documents = visit.get("linked_documents", [])

    age = _age_at_visit(
        demographics["date_of_birth"],
        visit["visit_date"],
    )

    bp_systolic = vitals.get("bp_systolic")
    bp_diastolic = vitals.get("bp_diastolic")

    prior_text = (
        f"Prior visit reference is {visit['prior_visit_id']}."
        if visit.get("prior_visit_id")
        else "This is the first recorded visit in the synthetic record."
    )

    return {
        # Identifiers
        "patient_id": str(patient.get("patient_id", "")),
        "visit_id": str(visit.get("visit_id", "")),

        # Routing / selection facts
        "tier": str(metadata["tier"]),

        # Raw demographics / visit facts
        "date_of_birth": demographics["date_of_birth"],
        "visit_date": visit["visit_date"],
        "sex": demographics["sex"],
        "visit_type": visit["visit_type"],
        "conditions": conditions,
        "diagnoses": diagnoses,
        "vitals": vitals,
        "labs": labs,
        "medications": medications,
        "linked_documents": linked_documents,
        "prior_visit_id": visit.get("prior_visit_id"),

        # Rendered patient / visit facts
        "age": age,
        "condition_text": _format_list(
            conditions,
            empty_text="no chronic conditions",
        ),
        "diagnosis_text": _format_list(
            diagnoses,
            empty_text="no chronic diagnosis listed",
        ),
        "lab_text": _format_labs(labs),
        "medication_text": _format_medications(medications),
        "linked_documents_text": _format_list(linked_documents),
        "prior_text": prior_text,

        # Rendered / directly accessed vital components
        "bp_systolic": bp_systolic,
        "bp_diastolic": bp_diastolic,
        "heart_rate": vitals.get("heart_rate"),
        "weight_kg": vitals.get("weight_kg"),
        "bmi": vitals.get("bmi"),
        "bp_text": f"{bp_systolic}/{bp_diastolic} mmHg",
    }


def _format_labs(labs: list[dict[str, Any]]) -> str:
    """
    Format visit lab records exactly as the deterministic SOAP pipeline expects.

    Empty-state output:
        "no lab results recorded"

    Non-empty output format:
        "{lab_type} {value} {unit} ({flag}); ..."

    Args:
        labs: List of lab result dictionaries.

    Returns:
        Deterministic lab summary string.
    """
    if not labs:
        return "no lab results recorded"

    return "; ".join(
        f"{lab['lab_type']} {lab['value']} {lab['unit']} ({lab['flag']})"
        for lab in labs
    )


def _format_medications(medications: list[dict[str, Any]]) -> str:
    """
    Format visit medication records exactly as the deterministic SOAP pipeline expects.

    Empty-state output:
        "no active whitelisted medications recorded"

    Non-empty output format:
        "{medication_name} {dose} {frequency} via {route}; ..."

    Args:
        medications: List of medication dictionaries.

    Returns:
        Deterministic medication summary string.
    """
    if not medications:
        return "no active whitelisted medications recorded"

    return "; ".join(
        f"{med['medication_name']} {med['dose']} "
        f"{med['frequency']} via {med['route']}"
        for med in medications
    )


def _format_list(values: list[Any], empty_text: str = "none") -> str:
    """
    Format a list exactly as the deterministic SOAP pipeline expects.

    Empty-state default output:
        "none"

    Non-empty output format:
        comma-separated string conversion of each value.

    Args:
        values: List of values to format.
        empty_text: Text returned when values is empty.

    Returns:
        Deterministic list summary string.
    """
    if not values:
        return empty_text

    return ", ".join(str(value) for value in values)


def _age_at_visit(date_of_birth: str, visit_date: str) -> int:
    """
    Calculate patient age at visit date.

    Args:
        date_of_birth: Patient date of birth using DATE_FORMAT.
        visit_date: Visit date using DATE_FORMAT.

    Returns:
        Integer age at the time of the visit.
    """
    dob = datetime.strptime(date_of_birth, DATE_FORMAT).date()
    visit = datetime.strptime(visit_date, DATE_FORMAT).date()

    years = visit.year - dob.year
    before_birthday = (visit.month, visit.day) < (dob.month, dob.day)
    return years - int(before_birthday)


__all__ = [
    "SoapFactContext",
    "build_fact_context",
    "_format_labs",
    "_format_medications",
    "_format_list",
    "_age_at_visit",
]
