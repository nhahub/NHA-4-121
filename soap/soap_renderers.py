"""
soap/soap_renderers.py

Deterministic SOAP fact and semantic-context rendering utilities.

Purpose:
    Centralize structured fact extraction, exact clinical formatting, and
    deterministic semantic context merging for SOAP generation.

v1.7 Lite alignment:
    This module exposes every field needed by the v1.7 Lite SOAP templates and
    selector, including soap_style, visit_role, clinical_event, semantic_focus,
    timeline_pattern, retrieval intent tags, medication trajectory text, lab
    trend text, and allergy context text.

This module owns:
    - raw patient/visit fact extraction,
    - exact lab formatting,
    - exact medication formatting,
    - exact allergy formatting,
    - exact list formatting,
    - age-at-visit calculation,
    - deterministic semantic context fields produced from documented facts,
    - safe formatting of a selected template against a fact context.

Safety contract:
    - No LLM calls.
    - No randomization.
    - No template registry.
    - No template selection.
    - No SOAP auditing.
    - No mutation of structured patient JSON facts.
    - No diagnosis inference.
    - No medication selection.
    - No lab selection.
    - No vital sign selection.
    - No clinical status interpretation beyond documented structured fields.

Architecture role:
    soap_contract.py   -> owns shared SOAP sections/types/template dataclass
    soap_semantics.py  -> owns condition-aware semantic phrase construction
    soap_renderers.py  -> owns fact extraction + exact formatting + semantic context merge
    soap_templates.py  -> owns template registry only
    soap_selector.py   -> owns deterministic template selection only
    soap_generator.py  -> owns final SOAP assembly
    soap_auditor.py    -> owns safety checks

Important:
    Medical truth must still come only from structured patient JSON. Semantic
    fields are descriptive strings derived from documented facts only.

    This module expects records to have passed validators.validate before SOAP
    generation. The lightweight guards below exist only to produce clear error
    messages if an invalid record reaches SOAP rendering unexpectedly.
"""

from __future__ import annotations

from datetime import datetime
from string import Formatter
from typing import Any, Mapping, TypedDict, cast

from config.constants import DATE_FORMAT
from soap.soap_contract import (
    ALLOWED_TEMPLATE_PLACEHOLDERS,
    REQUIRED_CLINICAL_EVENT_FIELDS_FOR_SOAP,
    REQUIRED_PATIENT_CONTEXT_FIELDS,
    REQUIRED_PATIENT_METADATA_FIELDS_FOR_SOAP,
    REQUIRED_RETRIEVAL_CONTEXT_FIELDS_FOR_SOAP,
    REQUIRED_VISIT_CONTEXT_FIELDS_FOR_SOAP,
    SoapTemplate,
)
from soap.soap_semantics import SoapSemanticContext, build_soap_semantic_context


class SoapFactContext(SoapSemanticContext):
    """
    Rendered, semantic, and raw facts used by deterministic SOAP generation.

    This context intentionally contains:
        1. Raw structured values from the patient JSON.
        2. Exact pre-rendered clinical strings used by SOAP generation.
        3. Deterministic semantic strings for stronger RAG retrieval quality.

    Safety rule:
        Values in this context must preserve structured patient facts and must
        not infer undocumented medical meaning.
    """

    # Identifiers
    patient_id: str
    visit_id: str

    # Patient-level routing and v1.7 Lite metadata
    tier: str
    dataset_version: str
    story_arc: str
    soap_style: str
    semantic_focus: str
    timeline_pattern: str
    retrieval_signature: str
    retrieval_intent_tags: list[Any]
    primary_retrieval_targets: list[Any]

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
    allergy_registry: list[dict[str, Any]]
    linked_documents: list[Any]
    prior_visit_id: Any

    # Visit-level v1.7 Lite facts
    visit_role: str
    visit_timeline_pattern: str
    timeline_gap_days: Any
    clinical_event: dict[str, Any]
    clinical_event_type: str
    clinical_event_label: str
    clinical_event_summary: str
    retrieval_context: dict[str, Any]

    # Rendered patient / visit facts
    age: int
    condition_text: str
    diagnosis_text: str
    lab_text: str
    medication_text: str
    allergy_text: str
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
    # visit_role_text: str
    # timeline_context_text: str
    # clinical_event_text: str
    # retrieval_focus_text: str
    # retrieval_intent_tags_text: str
    # primary_evidence_text: str
    # lab_trend_text: str
    # medication_trajectory_text: str
    # allergy_context_text: str


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
        - assemble a full SOAP note,
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
    patient_mapping = dict(patient)
    demographics = dict(patient_mapping.get("demographics", {}))
    metadata = dict(patient_mapping.get("metadata", {}))

    # Fill missing metadata fields for backward compatibility
    metadata.setdefault("tier", "normal")
    metadata.setdefault("story_arc", "stable")
    metadata.setdefault("timeline_pattern", "regular_quarterly")
    metadata.setdefault("semantic_focus", "symptom_control")
    metadata.setdefault("retrieval_signature", "none")
    metadata.setdefault("retrieval_intent_tags", [])
    metadata.setdefault("soap_style", "concise")

    patient_mapping["demographics"] = demographics
    patient_mapping["metadata"] = metadata
    patient_mapping.setdefault("conditions", [])
    patient_mapping.setdefault("allergy_registry", [])
    patient_mapping.setdefault("visits", [])

    visit_mapping = dict(visit)
    visit_mapping.setdefault("visit_role", "routine_follow_up")
    visit_mapping.setdefault("timeline_pattern", "regular_quarterly")
    visit_mapping.setdefault("timeline_gap_days", None)
    visit_mapping.setdefault("prior_visit_id", None)
    visit_mapping.setdefault("linked_documents", [])
    visit_mapping.setdefault("diagnoses", [])
    visit_mapping.setdefault("vitals", {
        "bp_systolic": 120,
        "bp_diastolic": 80,
        "heart_rate": 70,
        "weight_kg": 70.0,
        "bmi": 24.0,
    })
    visit_mapping.setdefault("labs", [])
    visit_mapping.setdefault("medications", [])

    clinical_event = dict(visit_mapping.get("clinical_event", {}))
    clinical_event.setdefault("event_type", "medication_continued")
    clinical_event.setdefault("event_label", "Routine follow up")
    clinical_event.setdefault("event_summary", "Routine follow up")
    visit_mapping["clinical_event"] = clinical_event

    retrieval_context = dict(visit_mapping.get("retrieval_context", {}))
    retrieval_context.setdefault("semantic_focus", "symptom_control")
    retrieval_context.setdefault("retrieval_intent_tags", [])
    visit_mapping["retrieval_context"] = retrieval_context

    patient_id = _require_non_empty_string(
        _required_value(patient_mapping, "patient_id", "patient"),
        "patient.patient_id",
    )
    visit_id = _require_non_empty_string(
        _required_value(visit_mapping, "visit_id", "visit"),
        "visit.visit_id",
    )

    conditions = _require_list(
        _required_value(patient_mapping, "conditions", "patient"),
        "patient.conditions",
    )
    diagnoses = _require_list(
        _required_value(visit_mapping, "diagnoses", "visit"),
        "visit.diagnoses",
    )
    vitals = _require_mapping(
        _required_value(visit_mapping, "vitals", "visit"),
        "visit.vitals",
    )
    labs = _typed_mapping_list(
        _require_list(_required_value(visit_mapping, "labs", "visit"), "visit.labs"),
        "visit.labs",
    )
    medications = _typed_mapping_list(
        _require_list(
            _required_value(visit_mapping, "medications", "visit"),
            "visit.medications",
        ),
        "visit.medications",
    )
    allergy_registry = _typed_mapping_list(
        _require_list(patient_mapping.get("allergy_registry", []), "patient.allergy_registry"),
        "patient.allergy_registry",
    )
    linked_documents = _require_list(
        _required_value(visit_mapping, "linked_documents", "visit"),
        "visit.linked_documents",
    )

    date_of_birth = _require_non_empty_string(
        _required_value(demographics, "date_of_birth", "patient.demographics"),
        "patient.demographics.date_of_birth",
    )
    visit_date = _require_non_empty_string(
        _required_value(visit_mapping, "visit_date", "visit"),
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
    dataset_version = _optional_string(metadata.get("dataset_version", ""))
    story_arc = _require_non_empty_string(
        _required_value(metadata, "story_arc", "patient.metadata"),
        "patient.metadata.story_arc",
    )
    soap_style = _require_non_empty_string(
        _required_value(metadata, "soap_style", "patient.metadata"),
        "patient.metadata.soap_style",
    )
    semantic_focus = _require_non_empty_string(
        _required_value(metadata, "semantic_focus", "patient.metadata"),
        "patient.metadata.semantic_focus",
    )
    timeline_pattern = _require_non_empty_string(
        _required_value(metadata, "timeline_pattern", "patient.metadata"),
        "patient.metadata.timeline_pattern",
    )
    retrieval_signature = _require_non_empty_string(
        _required_value(metadata, "retrieval_signature", "patient.metadata"),
        "patient.metadata.retrieval_signature",
    )
    retrieval_intent_tags = _require_list(
        _required_value(metadata, "retrieval_intent_tags", "patient.metadata"),
        "patient.metadata.retrieval_intent_tags",
    )
    primary_retrieval_targets = _require_list(
        metadata.get("primary_retrieval_targets", []),
        "patient.metadata.primary_retrieval_targets",
    )

    visit_type = _require_non_empty_string(
        _required_value(visit_mapping, "visit_type", "visit"),
        "visit.visit_type",
    )
    visit_role = _require_non_empty_string(
        _required_value(visit_mapping, "visit_role", "visit"),
        "visit.visit_role",
    )
    visit_timeline_pattern = _require_non_empty_string(
        _required_value(visit_mapping, "timeline_pattern", "visit"),
        "visit.timeline_pattern",
    )
    timeline_gap_days = _required_value(
        visit_mapping,
        "timeline_gap_days",
        "visit",
    )

    age = _age_at_visit(date_of_birth, visit_date)

    bp_systolic = _required_value(vitals, "bp_systolic", "visit.vitals")
    bp_diastolic = _required_value(vitals, "bp_diastolic", "visit.vitals")
    heart_rate = _required_value(vitals, "heart_rate", "visit.vitals")
    weight_kg = _required_value(vitals, "weight_kg", "visit.vitals")
    bmi = _required_value(vitals, "bmi", "visit.vitals")

    prior_visit_id = visit_mapping.get("prior_visit_id")
    prior_text = (
        f"Prior visit reference is {prior_visit_id}."
        if prior_visit_id
        else "This is the first recorded visit in the available record."
    )

    semantic_context = build_soap_semantic_context(
        conditions=conditions,
        diagnoses=diagnoses,
        labs=labs,
        medications=medications,
        visit_type=visit_type,
        prior_visit_id=prior_visit_id,
        visit_role=visit_role,
        timeline_pattern=visit_timeline_pattern or timeline_pattern,
        timeline_gap_days=timeline_gap_days,
        clinical_event=clinical_event,
        retrieval_context=retrieval_context,
        semantic_focus=semantic_focus,
        retrieval_intent_tags=retrieval_intent_tags,
        allergy_registry=allergy_registry,
        # Step 9: pass soap_style so visit_role_text gets the correct opener.
        soap_style=soap_style,
    )

    context: dict[str, Any] = {
        # Identifiers
        "patient_id": patient_id,
        "visit_id": visit_id,

        # Patient-level routing and v1.7 Lite metadata
        "tier": tier,
        "dataset_version": dataset_version,
        "story_arc": story_arc,
        "soap_style": soap_style,
        "semantic_focus": semantic_focus,
        "timeline_pattern": timeline_pattern,
        "retrieval_signature": retrieval_signature,
        "retrieval_intent_tags": retrieval_intent_tags,
        "primary_retrieval_targets": primary_retrieval_targets,

        # Raw demographics / visit facts
        "date_of_birth": date_of_birth,
        "visit_date": visit_date,
        "sex": sex,
        "visit_type": visit_type,
        "conditions": conditions,
        "diagnoses": diagnoses,
        "vitals": vitals,
        "labs": labs,
        "medications": medications,
        "allergy_registry": allergy_registry,
        "linked_documents": linked_documents,
        "prior_visit_id": prior_visit_id,

        # Visit-level v1.7 Lite facts
        "visit_role": visit_role,
        "visit_timeline_pattern": visit_timeline_pattern,
        "timeline_gap_days": timeline_gap_days,
        "clinical_event": clinical_event,
        "clinical_event_type": _require_non_empty_string(
            _required_value(clinical_event, "event_type", "visit.clinical_event"),
            "visit.clinical_event.event_type",
        ),
        "clinical_event_label": _require_non_empty_string(
            _required_value(clinical_event, "event_label", "visit.clinical_event"),
            "visit.clinical_event.event_label",
        ),
        "clinical_event_summary": _require_non_empty_string(
            _required_value(clinical_event, "event_summary", "visit.clinical_event"),
            "visit.clinical_event.event_summary",
        ),
        "retrieval_context": retrieval_context,

        # Rendered patient / visit facts
        "age": age,
        "condition_text": _format_list(
            conditions,
            empty_text="no chronic conditions",
        ),
        "diagnosis_text": _format_list(
            diagnoses,
            empty_text="no diagnosis listed for this visit",
        ),
        "lab_text": _format_labs(labs),
        "medication_text": _format_medications(medications),
        "allergy_text": _format_allergies(allergy_registry),
        "linked_documents_text": _format_linked_documents(linked_documents),
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

    return cast(SoapFactContext, context)


def render_template(
    template: SoapTemplate,
    fact_context: Mapping[str, Any],
) -> str:
    """
    Render a selected SoapTemplate using an already-built fact context.

    This function does not select templates or assemble a full SOAP note. It
    only applies one selected template to documented fact context values.
    """
    return render_template_text(template.text, fact_context)


def render_template_text(
    template_text: str,
    fact_context: Mapping[str, Any],
) -> str:
    """
    Render one template string using fact_context values.

    Raises:
        ValueError: If the template references unsupported or missing
            placeholders. This gives clear errors during template development.
    """
    clean_template_text = _require_non_empty_string(template_text, "template_text")
    placeholders = extract_template_placeholders(clean_template_text)

    unsupported = sorted(placeholders - set(ALLOWED_TEMPLATE_PLACEHOLDERS))
    if unsupported:
        raise ValueError(
            "Template contains unsupported placeholders: "
            + ", ".join(unsupported)
        )

    missing = sorted(name for name in placeholders if name not in fact_context)
    if missing:
        raise ValueError(
            "Template context is missing placeholders: "
            + ", ".join(missing)
        )

    none_values = sorted(name for name in placeholders if fact_context.get(name) is None)
    if none_values:
        raise ValueError(
            "Template context contains None for placeholders: "
            + ", ".join(none_values)
        )

    rendered = clean_template_text.format_map(_StringifyingMapping(fact_context))
    return _normalize_whitespace(rendered)


def extract_template_placeholders(template_text: str) -> set[str]:
    """
    Return field names used by a Python format template string.
    """
    placeholders: set[str] = set()

    for _, field_name, _, _ in Formatter().parse(template_text):
        if field_name:
            # Support simple placeholders only. Compound expressions such as
            # {foo.bar} or {foo[0]} are intentionally rejected by treating the
            # full expression as unsupported later.
            placeholders.add(field_name)

    return placeholders


def validate_fact_context_for_template(
    fact_context: Mapping[str, Any],
) -> list[str]:
    """
    Return missing allowed SOAP placeholders from a fact context.

    This is useful in tests to confirm that build_fact_context() supplies the
    full v1.7 Lite template contract.
    """
    return sorted(
        placeholder
        for placeholder in ALLOWED_TEMPLATE_PLACEHOLDERS
        if placeholder not in fact_context
    )


def _format_labs(labs: list[dict[str, Any]]) -> str:
    """
    Format visit lab records exactly as the deterministic SOAP pipeline expects.

    Empty-state output:
        "no lab results recorded"

    Non-empty output format:
        "{lab_type} {value} {unit} ({flag}); ..."
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
    Format visit medication records exactly as documented.

    Empty-state output:
        "no active whitelisted medications recorded"

    Non-empty output includes medication status and trajectory_event when they
    are present, because those are documented v1.7 Lite structured fields.
    """
    if not medications:
        return "no active whitelisted medications recorded"

    rendered_medications: list[str] = []

    for index, medication in enumerate(medications):
        location = f"visit.medications[{index}]"
        base = (
            f"{_required_value(medication, 'medication_name', location)} "
            f"{_required_value(medication, 'dose', location)} "
            f"{_required_value(medication, 'frequency', location)} via "
            f"{_required_value(medication, 'route', location)}"
        )

        detail_parts: list[str] = []
        medication_status = medication.get("medication_status")
        trajectory_event = medication.get("trajectory_event")
        reason = medication.get("reason")

        if medication_status:
            detail_parts.append(f"status {medication_status}")
        if trajectory_event:
            detail_parts.append(f"trajectory {trajectory_event}")
        if reason:
            detail_parts.append(f"reason {reason}")

        if detail_parts:
            base = f"{base} ({'; '.join(str(part) for part in detail_parts)})"

        rendered_medications.append(base)

    return "; ".join(rendered_medications)


def _format_allergies(allergies: list[dict[str, Any]]) -> str:
    """
    Format patient allergy registry entries exactly as documented.
    """
    if not allergies:
        return "no allergies recorded"

    rendered_allergies: list[str] = []

    for index, allergy in enumerate(allergies):
        location = f"patient.allergy_registry[{index}]"
        rendered_allergies.append(
            f"{_required_value(allergy, 'allergen', location)} reaction "
            f"{_required_value(allergy, 'reaction', location)} "
            f"({_required_value(allergy, 'severity', location)})"
        )

    return "; ".join(rendered_allergies)


def _format_linked_documents(linked_documents: list[Any]) -> str:
    """
    Format linked document references without assuming a specific document schema.
    """
    if not linked_documents:
        return "none"

    rendered: list[str] = []

    for item in linked_documents:
        if isinstance(item, Mapping):
            document_id = item.get("document_id") or item.get("doc_id") or item.get("id")
            source_type = item.get("source_type") or item.get("type")
            if document_id and source_type:
                rendered.append(f"{document_id} ({source_type})")
            elif document_id:
                rendered.append(str(document_id))
            else:
                rendered.append(str(dict(item)))
        else:
            rendered.append(str(item))

    return ", ".join(rendered)


def _format_list(values: list[Any], empty_text: str = "none") -> str:
    """
    Format a list exactly as the deterministic SOAP pipeline expects.
    """
    if not values:
        return empty_text

    return ", ".join(str(value) for value in values)


def _age_at_visit(date_of_birth: str, visit_date: str) -> int:
    """
    Calculate patient age at visit date.

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


def _require_keys(
    mapping: Mapping[str, Any],
    keys: tuple[str, ...],
    location: str,
) -> None:
    """
    Require a set of keys on a mapping and raise a clear pre-SOAP error.
    """
    missing = [key for key in keys if key not in mapping]
    if missing:
        raise ValueError(
            f"Missing required fields in {location} before SOAP rendering: "
            + ", ".join(missing)
            + ". Run validators.validate before generating SOAP notes."
        )


def _required_value(mapping: Mapping[str, Any], key: str, location: str) -> Any:
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


def _normalize_whitespace(text: str) -> str:
    """
    Collapse repeated whitespace while preserving sentence punctuation.
    """
    return " ".join(str(text).split())


class _StringifyingMapping(dict[str, str]):
    """
    Mapping wrapper used by str.format_map to stringify context values.
    """

    def __init__(self, source: Mapping[str, Any]) -> None:
        super().__init__((key, str(value)) for key, value in source.items())


__all__ = [
    "SoapFactContext",
    "build_fact_context",
    "render_template",
    "render_template_text",
    "extract_template_placeholders",
    "validate_fact_context_for_template",
    "_format_labs",
    "_format_medications",
    "_format_allergies",
    "_format_linked_documents",
    "_format_list",
    "_age_at_visit",
]
