"""
soap/soap_semantics.py

Condition-aware deterministic SOAP semantic context utilities.

Purpose:
    Build retrieval-friendly semantic context strings from documented structured
    patient and visit facts.

This module improves RAG chunk quality by adding deterministic, condition-aware
phrasing while preserving the project's safety contract.

Design rules:
    - No LLM calls.
    - No randomization.
    - No template registry.
    - No template selection.
    - No SOAP rendering.
    - No audit logic.
    - No mutation of patient or visit dictionaries.
    - No diagnosis inference.
    - No medication recommendation.
    - No treatment recommendation.
    - No clinical status interpretation.
    - No symptom invention.
    - No use of facts that are not present in structured JSON.

Important:
    This module does not decide medical truth. It only converts documented
    structured facts into safer, more retrieval-friendly semantic phrases.

Intended integration:
    soap_renderers.py should call build_soap_semantic_context() inside
    build_fact_context(), then merge the returned fields into SoapFactContext.

Example future placeholders:
    - condition_focus_text
    - diagnosis_focus_text
    - monitoring_focus_text
    - medication_focus_text
    - visit_context_text
    - timeline_context_text
    - retrieval_focus_text
"""

from __future__ import annotations

from typing import Any, Final, Iterable, Mapping, TypedDict


class SoapSemanticContext(TypedDict):
    """
    Deterministic semantic strings derived from documented structured facts.

    These strings are intended to improve RAG retrieval quality by making SOAP
    chunks more semantically distinct across conditions and visit contexts.

    They must remain descriptive, grounded, and non-inferential.
    """

    condition_focus_text: str
    diagnosis_focus_text: str
    monitoring_focus_text: str
    medication_focus_text: str
    visit_context_text: str
    timeline_context_text: str
    retrieval_focus_text: str


# Canonical condition labels used only when the corresponding condition or
# diagnosis exists in the structured record.
CONDITION_LABELS: Final[Mapping[str, str]] = {
    "T2DM": "type 2 diabetes",
    "HTN": "hypertension",
    "Asthma": "asthma",
    "IDA": "iron-deficiency anemia",
    "GERD": "gastroesophageal reflux disease",
    "CKD": "chronic kidney disease",
}


# Lab families are condition-aware but still grounded: a family phrase is used
# only when at least one related lab type exists in the visit lab list.
CONDITION_LAB_KEYWORDS: Final[Mapping[str, tuple[str, ...]]] = {
    "T2DM": ("hba1c", "fbg"),
    "HTN": ("creatinine",),
    "CKD": ("creatinine",),
    "IDA": ("hemoglobin", "ferritin"),
}


# Medication families are condition-aware but still grounded: a family phrase is
# used only when at least one related medication name exists in the visit
# medication list.
CONDITION_MEDICATION_KEYWORDS: Final[Mapping[str, tuple[str, ...]]] = {
    "T2DM": ("metformin", "glibenclamide"),
    "HTN": ("lisinopril", "amlodipine", "losartan"),
    "Asthma": ("salbutamol", "budesonide", "inhaler"),
    "IDA": ("ferrous",),
    "GERD": ("omeprazole",),
}


VISIT_TYPE_TEXT: Final[Mapping[str, str]] = {
    "initial": "This is documented as the first encounter type in the visit record.",
    "follow_up": "This is documented as a follow-up encounter in the visit record.",
    "emergency": "This is documented as an emergency encounter in the visit record.",
    "hospitalization": "This is documented as a hospitalization encounter in the visit record.",
}


def build_soap_semantic_context(
    *,
    conditions: Iterable[Any],
    diagnoses: Iterable[Any],
    labs: Iterable[Mapping[str, Any]],
    medications: Iterable[Mapping[str, Any]],
    visit_type: Any,
    prior_visit_id: Any,
) -> SoapSemanticContext:
    """
    Build deterministic condition-aware semantic context strings.

    Args:
        conditions:
            Patient-level documented conditions.
        diagnoses:
            Visit-level documented diagnoses.
        labs:
            Visit-level lab result dictionaries.
        medications:
            Visit-level medication dictionaries.
        visit_type:
            Visit type from the structured visit record.
        prior_visit_id:
            Prior visit ID or None.

    Returns:
        SoapSemanticContext with retrieval-friendly semantic strings.

    Safety:
        The function only reflects documented values. It does not infer control,
        progression, severity, treatment need, symptom history, or diagnosis.
    """
    condition_values = _clean_values(conditions)
    diagnosis_values = _clean_values(diagnoses)
    lab_types = _lab_type_set(labs)
    medication_names = _medication_name_set(medications)
    clean_visit_type = str(visit_type).strip()

    return {
        "condition_focus_text": build_condition_focus_text(condition_values),
        "diagnosis_focus_text": build_diagnosis_focus_text(diagnosis_values),
        "monitoring_focus_text": build_monitoring_focus_text(
            conditions=condition_values,
            lab_types=lab_types,
        ),
        "medication_focus_text": build_medication_focus_text(
            conditions=condition_values,
            medication_names=medication_names,
        ),
        "visit_context_text": build_visit_context_text(clean_visit_type),
        "timeline_context_text": build_timeline_context_text(prior_visit_id),
        "retrieval_focus_text": build_retrieval_focus_text(
            conditions=condition_values,
            diagnoses=diagnosis_values,
            lab_types=lab_types,
            medication_names=medication_names,
            visit_type=clean_visit_type,
            prior_visit_id=prior_visit_id,
        ),
    }


def build_condition_focus_text(conditions: Iterable[str]) -> str:
    """
    Describe documented patient-level conditions using condition-aware wording.
    """
    condition_values = tuple(conditions)

    if not condition_values:
        return (
            "The record does not list chronic conditions in the patient-level "
            "condition field."
        )

    phrases = [
        _condition_phrase(condition)
        for condition in condition_values
    ]

    return (
        "The patient-level condition field documents "
        f"{_join_phrases(phrases)}."
    )


def build_diagnosis_focus_text(diagnoses: Iterable[str]) -> str:
    """
    Describe documented visit-level diagnoses using condition-aware wording.
    """
    diagnosis_values = tuple(diagnoses)

    if not diagnosis_values:
        return (
            "The visit diagnosis field does not list a chronic diagnosis for "
            "this encounter."
        )

    phrases = [
        _condition_phrase(diagnosis)
        for diagnosis in diagnosis_values
    ]

    return (
        "The visit diagnosis field documents "
        f"{_join_phrases(phrases)} for this encounter."
    )


def build_monitoring_focus_text(
    *,
    conditions: Iterable[str],
    lab_types: set[str],
) -> str:
    """
    Describe documented monitoring context from conditions and present labs.

    This function does not claim disease control, improvement, deterioration, or
    clinical progression. It only links documented conditions with lab families
    that are actually present in the visit.
    """
    condition_values = tuple(conditions)
    monitoring_parts: list[str] = []

    for condition in condition_values:
        keywords = CONDITION_LAB_KEYWORDS.get(condition, ())

        if not keywords:
            continue

        if any(keyword in lab_types for keyword in keywords):
            monitoring_parts.append(_monitoring_phrase(condition))

    if not monitoring_parts:
        if lab_types:
            return (
                "The visit includes laboratory entries documented in the "
                "objective data."
            )

        return (
            "No laboratory entries are documented for this visit."
        )

    return (
        "The visit contains documented monitoring context for "
        f"{_join_phrases(monitoring_parts)}."
    )


def build_medication_focus_text(
    *,
    conditions: Iterable[str],
    medication_names: set[str],
) -> str:
    """
    Describe documented medication context from present medication entries.

    This function does not recommend, prescribe, start, stop, or adjust any
    medication. It only states that medication entries are present in the visit
    record.
    """
    condition_values = tuple(conditions)
    medication_parts: list[str] = []

    for condition in condition_values:
        keywords = CONDITION_MEDICATION_KEYWORDS.get(condition, ())

        if not keywords:
            continue

        if any(_contains_keyword(medication_names, keyword) for keyword in keywords):
            medication_parts.append(_medication_phrase(condition))

    if not medication_parts:
        if medication_names:
            return (
                "The visit contains medication entries documented in the "
                "medication list."
            )

        return (
            "No active medication entries are documented for this visit."
        )

    return (
        "The medication list includes documented entries related to "
        f"{_join_phrases(medication_parts)}."
    )


def build_visit_context_text(visit_type: str) -> str:
    """
    Describe visit type without adding clinical meaning.
    """
    clean_visit_type = str(visit_type).strip()

    if clean_visit_type in VISIT_TYPE_TEXT:
        return VISIT_TYPE_TEXT[clean_visit_type]

    if clean_visit_type:
        return (
            "The encounter type is documented in the visit record as "
            f"{clean_visit_type}."
        )

    return "The encounter type is not documented in the visit record."


def build_timeline_context_text(prior_visit_id: Any) -> str:
    """
    Describe visit timeline context from prior_visit_id only.
    """
    if prior_visit_id:
        return (
            "This encounter is linked to a prior documented visit through "
            f"prior_visit_id {prior_visit_id}."
        )

    return (
        "This encounter has no prior_visit_id and is the first documented visit "
        "in the available timeline."
    )


def build_retrieval_focus_text(
    *,
    conditions: Iterable[str],
    diagnoses: Iterable[str],
    lab_types: set[str],
    medication_names: set[str],
    visit_type: str,
    prior_visit_id: Any,
) -> str:
    """
    Build a compact retrieval-oriented semantic summary.

    The wording is intentionally broad but condition-aware. It helps embedding
    models distinguish chunks by condition, labs, medications, visit type, and
    timeline role without adding undocumented clinical claims.
    """
    topics: list[str] = []

    documented_conditions = tuple(conditions)
    documented_diagnoses = tuple(diagnoses)

    if documented_conditions:
        topics.append(
            "patient-level conditions: "
            + _join_phrases(_condition_phrase(item) for item in documented_conditions)
        )

    if documented_diagnoses:
        topics.append(
            "visit diagnoses: "
            + _join_phrases(_condition_phrase(item) for item in documented_diagnoses)
        )

    if lab_types:
        topics.append("laboratory entries: " + _join_phrases(sorted(lab_types)))

    if medication_names:
        topics.append(
            "medication entries: "
            + _join_phrases(_display_medication_names(medication_names))
        )

    if visit_type:
        topics.append(f"visit type: {visit_type}")

    if prior_visit_id:
        topics.append("timeline link: prior visit documented")
    else:
        topics.append("timeline link: first documented visit")

    if not topics:
        return (
            "This SOAP note supports retrieval over documented encounter "
            "details without adding unstated clinical facts."
        )

    return (
        "Retrieval focus includes "
        + "; ".join(topics)
        + "."
    )


def _condition_phrase(condition: str) -> str:
    """
    Return a display phrase for a documented condition or diagnosis value.
    """
    return CONDITION_LABELS.get(condition, condition)


def _monitoring_phrase(condition: str) -> str:
    """
    Return condition-aware monitoring wording only for documented lab context.
    """
    label = _condition_phrase(condition)

    if condition == "T2DM":
        return f"{label} laboratory follow-up"
    if condition in {"HTN", "CKD"}:
        return f"{label} kidney-related laboratory documentation"
    if condition == "IDA":
        return f"{label} blood and iron-related laboratory documentation"

    return f"{label} laboratory documentation"


def _medication_phrase(condition: str) -> str:
    """
    Return condition-aware medication wording only for documented medications.
    """
    label = _condition_phrase(condition)

    return f"{label} medication documentation"


def _clean_values(values: Iterable[Any]) -> tuple[str, ...]:
    """
    Convert iterable values into non-empty stripped strings.
    """
    return tuple(
        cleaned
        for value in values
        for cleaned in (str(value).strip(),)
        if cleaned
    )


def _lab_type_set(labs: Iterable[Mapping[str, Any]]) -> set[str]:
    """
    Return normalized lab_type values from visit lab dictionaries.
    """
    lab_types: set[str] = set()

    for lab in labs:
        lab_type = str(lab.get("lab_type", "")).strip().lower()

        if lab_type:
            lab_types.add(lab_type)

    return lab_types


def _medication_name_set(medications: Iterable[Mapping[str, Any]]) -> set[str]:
    """
    Return normalized medication_name values from visit medication dictionaries.
    """
    medication_names: set[str] = set()

    for medication in medications:
        medication_name = str(medication.get("medication_name", "")).strip().lower()

        if medication_name:
            medication_names.add(medication_name)

    return medication_names


def _contains_keyword(values: set[str], keyword: str) -> bool:
    """
    Return True if any normalized value contains the normalized keyword.
    """
    normalized_keyword = keyword.lower()

    return any(normalized_keyword in value for value in values)


def _display_medication_names(medication_names: set[str]) -> tuple[str, ...]:
    """
    Return deterministic display names for normalized medication names.
    """
    return tuple(sorted(medication_names))


def _join_phrases(values: Iterable[str]) -> str:
    """
    Join phrases in a readable deterministic way.
    """
    phrases = [phrase for phrase in values if phrase]

    if not phrases:
        return "none"

    if len(phrases) == 1:
        return phrases[0]

    if len(phrases) == 2:
        return f"{phrases[0]} and {phrases[1]}"

    return ", ".join(phrases[:-1]) + f", and {phrases[-1]}"


__all__ = (
    "SoapSemanticContext",
    "CONDITION_LABELS",
    "CONDITION_LAB_KEYWORDS",
    "CONDITION_MEDICATION_KEYWORDS",
    "VISIT_TYPE_TEXT",
    "build_soap_semantic_context",
    "build_condition_focus_text",
    "build_diagnosis_focus_text",
    "build_monitoring_focus_text",
    "build_medication_focus_text",
    "build_visit_context_text",
    "build_timeline_context_text",
    "build_retrieval_focus_text",
)
