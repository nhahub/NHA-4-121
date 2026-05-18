"""
soap/soap_renderers.py

Deterministic SOAP fact and semantic-context rendering utilities.

Purpose:
    Centralize structured fact extraction, exact clinical formatting, and
    deterministic condition-aware semantic context construction for SOAP
    generation.

This module owns:
    - raw patient/visit fact extraction,
    - exact lab formatting,
    - exact medication formatting,
    - exact list formatting,
    - age-at-visit calculation,
    - deterministic semantic context fields produced from documented facts.

Safety contract:
    - No LLM calls.
    - No randomization.
    - No template registry.
    - No template selection.
    - No SOAP assembly.
    - No SOAP auditing.
    - No mutation of structured patient JSON facts.
    - No diagnosis inference.
    - No medication selection.
    - No lab selection.
    - No vital sign selection.
    - No clinical status interpretation.

Architecture role:
    soap_contract.py   -> owns shared SOAP sections/types/template dataclass
    soap_semantics.py  -> owns condition-aware semantic phrase construction
    soap_renderers.py  -> owns fact extraction + exact formatting + semantic context merge
    soap_templates.py  -> owns template registry only
    soap_selector.py   -> owns deterministic template selection only
    soap_generator.py  -> owns final SOAP assembly/rendering
    soap_auditor.py    -> owns safety checks

Important:
    SoapFactContext intentionally remains in this module because it represents
    rendered output from structured patient JSON, not the shared template
    contract.

    Medical truth must still come only from structured patient JSON. Semantic
    fields are descriptive strings derived from documented facts only.

    This module expects records to have passed validators.validate before SOAP
    generation. The lightweight guards below exist only to produce clear error
    messages if an invalid record reaches SOAP rendering unexpectedly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

from config.constants import DATE_FORMAT
from soap.soap_semantics import SoapSemanticContext, build_soap_semantic_context


class SoapFactContext(SoapSemanticContext):
    """
    Rendered, semantic, and raw facts used by deterministic SOAP generation.

    This context intentionally contains:
        1. Raw structured values from the patient JSON.
        2. Exact pre-rendered clinical strings used by SOAP generation.
        3. Deterministic condition-aware semantic strings for stronger RAG
           retrieval quality.

    Safety rule:
        Values in this context must preserve structured patient facts and must
        not infer undocumented medical meaning.
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

    # Inherited semantic fields from SoapSemanticContext:
    # condition_focus_text: str
    # diagnosis_focus_text: str
    # monitoring_focus_text: str
    # medication_focus_text: str
    # visit_context_text: str
    # timeline_context_text: str
    # retrieval_focus_text: str


def build_fact_context(
    patient: dict[str, Any],
    visit: dict[str, Any],
) -> SoapFactContext:
    """
    Build a deterministic fact context from structured patient and visit data.

    This function centralizes fact extraction, exact formatting, and semantic
    context preparation for SOAP generation.

    It must not:
        - modify patient data,
        - infer missing medical facts,
        - normalize clinical values,
        - select templates,
        - render SOAP sections,
        - perform audit checks,
        - call an LLM.

    Args:
        patient: Validated patient JSON dictionary.
        visit: Validated visit dictionary from patient["visits"].

    Returns:
        SoapFactContext containing raw, rendered, and semantic fields for SOAP
        template rendering.

    Raises:
        ValueError: If an unvalidated or malformed record reaches SOAP rendering.
    """
    _require_mapping(patient, "patient")
    _require_mapping(visit, "visit")

    patient_id = _optional_string(patient.get("patient_id", ""))
    visit_id = _optional_string(visit.get("visit_id", ""))

    demographics = _require_mapping(
        _required_value(patient, "demographics", "patient"),
        "patient.demographics",
    )
    metadata = _require_mapping(
        _required_value(patient, "metadata", "patient"),
        "patient.metadata",
    )

    conditions = _require_list(
        _required_value(patient, "conditions", "patient"),
        "patient.conditions",
    )
    diagnoses = _require_list(
        _required_value(visit, "diagnoses", "visit"),
        "visit.diagnoses",
    )
    vitals = _require_mapping(
        _required_value(visit, "vitals", "visit"),
        "visit.vitals",
    )
    labs = _require_list(
        _required_value(visit, "labs", "visit"),
        "visit.labs",
    )
    medications = _require_list(
        _required_value(visit, "medications", "visit"),
        "visit.medications",
    )
    linked_documents = _require_list(
        _required_value(visit, "linked_documents", "visit"),
        "visit.linked_documents",
    )

    date_of_birth = _require_non_empty_string(
        _required_value(demographics, "date_of_birth", "patient.demographics"),
        "patient.demographics.date_of_birth",
    )
    visit_date = _require_non_empty_string(
        _required_value(visit, "visit_date", "visit"),
        "visit.visit_date",
    )
    sex = _require_non_empty_string(
        _required_value(demographics, "sex", "patient.demographics"),
        "patient.demographics.sex",
    )
    tier = _require_non_empty_string(
        _required_value(metadata, "tier", "patient.metadata"),
        "patient.metadata.tier",
    )
    visit_type = _require_non_empty_string(
        _required_value(visit, "visit_type", "visit"),
        "visit.visit_type",
    )

    age = _age_at_visit(date_of_birth, visit_date)

    bp_systolic = _required_value(vitals, "bp_systolic", "visit.vitals")
    bp_diastolic = _required_value(vitals, "bp_diastolic", "visit.vitals")
    heart_rate = _required_value(vitals, "heart_rate", "visit.vitals")
    weight_kg = _required_value(vitals, "weight_kg", "visit.vitals")
    bmi = _required_value(vitals, "bmi", "visit.vitals")

    prior_visit_id = visit.get("prior_visit_id")
    prior_text = (
        f"Prior visit reference is {prior_visit_id}."
        if prior_visit_id
        else "This is the first recorded visit in the available record."
    )

    semantic_context = build_soap_semantic_context(
        conditions=conditions,
        diagnoses=diagnoses,
        labs=_typed_mapping_list(labs, "visit.labs"),
        medications=_typed_mapping_list(medications, "visit.medications"),
        visit_type=visit_type,
        prior_visit_id=prior_visit_id,
    )

    return {
        # Identifiers
        "patient_id": patient_id,
        "visit_id": visit_id,

        # Routing / selection facts
        "tier": tier,

        # Raw demographics / visit facts
        "date_of_birth": date_of_birth,
        "visit_date": visit_date,
        "sex": sex,
        "visit_type": visit_type,
        "conditions": conditions,
        "diagnoses": diagnoses,
        "vitals": vitals,
        "labs": _typed_mapping_list(labs, "visit.labs"),
        "medications": _typed_mapping_list(medications, "visit.medications"),
        "linked_documents": linked_documents,
        "prior_visit_id": prior_visit_id,

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
        "lab_text": _format_labs(_typed_mapping_list(labs, "visit.labs")),
        "medication_text": _format_medications(
            _typed_mapping_list(medications, "visit.medications")
        ),
        "linked_documents_text": _format_list(linked_documents),
        "prior_text": prior_text,

        # Rendered / directly accessed vital components
        "bp_systolic": bp_systolic,
        "bp_diastolic": bp_diastolic,
        "heart_rate": heart_rate,
        "weight_kg": weight_kg,
        "bmi": bmi,
        "bp_text": f"{bp_systolic}/{bp_diastolic} mmHg",

        # Deterministic semantic context for stronger RAG retrieval.
        **semantic_context,
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

    rendered_labs: list[str] = []

    for index, lab in enumerate(labs):
        location = f"visit.labs[{index}]"
        rendered_labs.append(
            f"{_required_value(lab, 'lab_type', location)} "
            f"{_required_value(lab, 'value', location)} "
            f"{_required_value(lab, 'unit', location)} "
            f"({_required_value(lab, 'flag', location)})"
        )

    return "; ".join(rendered_labs)


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

    rendered_medications: list[str] = []

    for index, medication in enumerate(medications):
        location = f"visit.medications[{index}]"
        rendered_medications.append(
            f"{_required_value(medication, 'medication_name', location)} "
            f"{_required_value(medication, 'dose', location)} "
            f"{_required_value(medication, 'frequency', location)} via "
            f"{_required_value(medication, 'route', location)}"
        )

    return "; ".join(rendered_medications)


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

    Raises:
        ValueError: If dates are malformed. This should normally be caught by V8.
    """
    try:
        dob = datetime.strptime(date_of_birth, DATE_FORMAT).date()
        visit = datetime.strptime(visit_date, DATE_FORMAT).date()
    except ValueError as exc:
        raise ValueError(
            "Invalid date reached SOAP rendering. Expected validated "
            f"{DATE_FORMAT!r} dates for date_of_birth={date_of_birth!r} "
            f"and visit_date={visit_date!r}. Run validators.validate before SOAP."
        ) from exc

    years = visit.year - dob.year
    before_birthday = (visit.month, visit.day) < (dob.month, dob.day)
    return years - int(before_birthday)


def _required_value(mapping: dict[str, Any], key: str, location: str) -> Any:
    """
    Return a required field or raise a clear pre-SOAP validation error.
    """
    if key not in mapping:
        raise ValueError(
            f"Missing required field {location}.{key} before SOAP rendering. "
            "Run validators.validate before generating SOAP notes."
        )

    return mapping[key]


def _require_mapping(value: Any, location: str) -> dict[str, Any]:
    """
    Validate that a value is a dictionary-like JSON object.
    """
    if not isinstance(value, dict):
        raise ValueError(
            f"Expected {location} to be an object before SOAP rendering, "
            f"got {type(value).__name__}. Run validators.validate first."
        )

    return value


def _require_list(value: Any, location: str) -> list[Any]:
    """
    Validate that a value is a JSON array.
    """
    if not isinstance(value, list):
        raise ValueError(
            f"Expected {location} to be an array before SOAP rendering, "
            f"got {type(value).__name__}. Run validators.validate first."
        )

    return value


def _typed_mapping_list(values: list[Any], location: str) -> list[dict[str, Any]]:
    """
    Validate and cast a list expected to contain object dictionaries.
    """
    typed_values: list[dict[str, Any]] = []

    for index, value in enumerate(values):
        typed_values.append(_require_mapping(value, f"{location}[{index}]"))

    return typed_values


def _require_non_empty_string(value: Any, location: str) -> str:
    """
    Validate that a required field is a non-empty string.
    """
    if not isinstance(value, str):
        raise ValueError(
            f"Expected {location} to be a string before SOAP rendering, "
            f"got {type(value).__name__}. Run validators.validate first."
        )

    cleaned = value.strip()

    if not cleaned:
        raise ValueError(
            f"Expected {location} to be non-empty before SOAP rendering. "
            "Run validators.validate first."
        )

    return cleaned


def _optional_string(value: Any) -> str:
    """
    Convert optional display identifiers into strings without inferring facts.
    """
    return "" if value is None else str(value)


__all__ = [
    "SoapFactContext",
    "build_fact_context",
    "_format_labs",
    "_format_medications",
    "_format_list",
    "_age_at_visit",
]
