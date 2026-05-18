"""
ingestion/retrieval_enricher.py

Deterministic Retrieval Enrichment Layer.

This module builds retrieval-oriented text from documented structured facts.
It is intentionally deterministic and does not call an LLM, mutate patient
records, perform chunking, build metadata, create embeddings, or write to
ChromaDB.

The generated retrieval text is retrieval support only. Structured patient
JSON and generated SOAP notes remain the source of truth.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from config.constants import (
    CONDITIONS,
    LAB_TYPES,
    MEDICATION_NAMES,
    MEDICATION_WHITELIST,
    SOURCE_TYPES,
)


CONDITION_LAB_CONTEXT: dict[str, tuple[str, ...]] = {
    "T2DM": ("HbA1c", "FBG"),
    "HTN": ("Creatinine",),
    "CKD": ("Creatinine",),
    "IDA": ("Hemoglobin", "Ferritin"),
}

CONDITION_LAB_RETRIEVAL_LABELS: dict[str, str] = {
    "T2DM": "diabetes-related",
    "HTN": "hypertension-related",
    "CKD": "CKD-related",
    "IDA": "anemia-related",
}


def build_retrieval_text(
    patient: dict[str, Any],
    visit: dict[str, Any] | None = None,
    source_type: str = "doctor_note",
) -> str:
    """
    Build deterministic retrieval-oriented text for one supported source type.

    Args:
        patient: Full patient JSON dictionary.
        visit: One visit dictionary for visit-level source types.
            Required for doctor_note, lab_result, and prescription.
            Not required for allergy.
        source_type: One value from config.constants.SOURCE_TYPES:
            doctor_note, lab_result, prescription, allergy.

    Returns:
        Retrieval support text derived only from documented structured facts.

    Raises:
        ValueError:
            If source_type is not supported.
            If source_type is not allergy and visit is None.
    """
    if source_type not in SOURCE_TYPES:
        raise ValueError(
            f"Unsupported source_type {source_type!r}. "
            f"Expected one of: {', '.join(SOURCE_TYPES)}"
        )

    if source_type == "allergy":
        return build_allergy_retrieval_text(patient)

    if visit is None:
        raise ValueError(
            f"visit is required when source_type={source_type!r}. "
            "Only source_type='allergy' supports visit=None."
        )

    if source_type == "doctor_note":
        return build_doctor_note_retrieval_text(patient, visit)

    if source_type == "lab_result":
        return build_lab_retrieval_text(patient, visit)

    if source_type == "prescription":
        return build_prescription_retrieval_text(patient, visit)

    raise AssertionError("Unreachable source_type routing branch")


def build_doctor_note_retrieval_text(
    patient: dict[str, Any],
    visit: dict[str, Any],
) -> str:
    """
    Build retrieval text for doctor_note chunks.

    The output includes documented patient, visit, condition, diagnosis,
    vital-sign, lab, medication, and prior-visit context without adding
    medical interpretation.
    """
    patient_id = _safe_text(patient.get("patient_id"))
    visit_id = _safe_text(visit.get("visit_id"))
    visit_date = _safe_text(visit.get("visit_date"))
    visit_type = _safe_text(visit.get("visit_type"))
    tier = _safe_text(_metadata_value(patient, "tier"))

    patient_conditions = _documented_patient_conditions(patient)
    visit_diagnoses = _documented_visit_diagnoses(visit)
    lab_names = _lab_type_names(_dict_list(visit.get("labs")))
    medication_names = _medication_names(_dict_list(visit.get("medications")))
    prior_visit_id = _safe_text(visit.get("prior_visit_id"))

    sentences: list[str] = []

    opening_parts = []
    if visit_type:
        opening_parts.append(f"{visit_type} doctor-note retrieval context")
    else:
        opening_parts.append("Doctor-note retrieval context")

    if patient_id:
        opening_parts.append(f"for patient {patient_id}")
    if visit_id:
        opening_parts.append(f"and visit {visit_id}")
    if visit_date:
        opening_parts.append(f"on {visit_date}")

    sentences.append(_sentence_from_parts(opening_parts))

    if tier:
        sentences.append(f"Documented patient tier is {tier}.")

    if patient_conditions:
        sentences.append(
            "Documented patient conditions include "
            f"{_join_phrases(patient_conditions)}."
        )
    else:
        sentences.append("No patient conditions are documented in the record.")

    if visit_diagnoses:
        sentences.append(
            "Visit diagnoses include "
            f"{_join_phrases(visit_diagnoses)}."
        )
    else:
        sentences.append("No visit diagnoses are documented for this visit.")

    if isinstance(visit.get("vitals"), Mapping) and visit.get("vitals"):
        sentences.append(
            "The visit contains vital-sign documentation for retrieval "
            "matching."
        )
    else:
        sentences.append(
            "The visit contains no documented vital-sign entries."
        )

    if lab_names:
        sentences.append(
            "The visit contains documented laboratory entries for "
            f"{_join_phrases(lab_names)}."
        )
    else:
        sentences.append(
            "The visit contains no documented laboratory entries."
        )

    if medication_names:
        sentences.append(
            "The visit contains documented medication entries for "
            f"{_join_phrases(medication_names)}."
        )
    else:
        sentences.append(
            "The visit contains no documented medication entries."
        )

    if prior_visit_id:
        sentences.append(
            f"The visit links to prior visit {prior_visit_id} for timeline "
            "retrieval context."
        )
    else:
        sentences.append("The visit has no documented prior_visit_id.")

    return " ".join(sentences)


def build_lab_retrieval_text(
    patient: dict[str, Any],
    visit: dict[str, Any],
) -> str:
    """
    Build retrieval text for lab_result chunks.

    Condition-related lab wording is included only when the condition is
    documented in patient conditions or visit diagnoses.
    """
    patient_id = _safe_text(patient.get("patient_id"))
    visit_id = _safe_text(visit.get("visit_id"))
    visit_date = _safe_text(visit.get("visit_date"))
    visit_type = _safe_text(visit.get("visit_type"))

    documented_conditions = _documented_conditions_for_visit(patient, visit)
    labs = _dict_list(visit.get("labs"))
    lab_names = _lab_type_names(labs)
    lab_flag_pairs = _lab_flag_pairs(labs)

    sentences: list[str] = []

    opening_parts = ["Laboratory retrieval context"]
    if patient_id:
        opening_parts.append(f"for patient {patient_id}")
    if visit_id:
        opening_parts.append(f"and visit {visit_id}")
    if visit_date:
        opening_parts.append(f"on {visit_date}")
    if visit_type:
        opening_parts.append(f"during a {visit_type} visit")

    sentences.append(_sentence_from_parts(opening_parts))

    if lab_names:
        sentences.append(
            "Documented lab types in this visit include "
            f"{_join_phrases(lab_names)}."
        )
    else:
        sentences.append(
            "No documented lab types are present in this visit."
        )

    condition_context_sentences = _lab_condition_context_sentences(
        documented_conditions=documented_conditions,
        lab_names=lab_names,
    )

    if condition_context_sentences:
        sentences.extend(condition_context_sentences)
    else:
        sentences.append(
            "No chronic condition-specific lab wording is added because the "
            "documented patient and visit conditions do not match these lab "
            "entries."
        )

    if lab_flag_pairs:
        sentences.append(
            "Lab flags are included exactly as documented: "
            f"{_join_phrases(lab_flag_pairs)}."
        )
    else:
        sentences.append("No lab flags are documented in this visit.")

    return " ".join(sentences)


def build_prescription_retrieval_text(
    patient: dict[str, Any],
    visit: dict[str, Any],
) -> str:
    """
    Build retrieval text for prescription chunks.

    Medication-condition wording is included only when both requirements hold:
    the medication exists in MEDICATION_WHITELIST and the whitelist condition is
    documented in patient conditions or visit diagnoses.
    """
    patient_id = _safe_text(patient.get("patient_id"))
    visit_id = _safe_text(visit.get("visit_id"))
    visit_date = _safe_text(visit.get("visit_date"))
    visit_type = _safe_text(visit.get("visit_type"))

    documented_conditions = _documented_conditions_for_visit(patient, visit)
    medications = _dict_list(visit.get("medications"))
    medication_names = _medication_names(medications)

    sentences: list[str] = []

    opening_parts = ["Prescription retrieval context"]
    if patient_id:
        opening_parts.append(f"for patient {patient_id}")
    if visit_id:
        opening_parts.append(f"and visit {visit_id}")
    if visit_date:
        opening_parts.append(f"on {visit_date}")
    if visit_type:
        opening_parts.append(f"during a {visit_type} visit")

    sentences.append(_sentence_from_parts(opening_parts))

    if medication_names:
        sentences.append(
            "Documented medications in this visit include "
            f"{_join_phrases(medication_names)}."
        )
    else:
        sentences.append(
            "No documented medications are present in this visit."
        )

    detail_sentences = _medication_detail_sentences(medications)
    if detail_sentences:
        sentences.extend(detail_sentences)

    condition_context = _medication_condition_context_phrases(
        medications=medications,
        documented_conditions=documented_conditions,
    )
    if condition_context:
        sentences.append(
            "Medication-condition retrieval context is included only for "
            "documented condition matches: "
            f"{_join_phrases(condition_context)}."
        )
    else:
        sentences.append(
            "No medication-condition retrieval wording is added because no "
            "documented medication has a matching documented condition in "
            "this source context."
        )

    return " ".join(sentences)


def build_allergy_retrieval_text(patient: dict[str, Any]) -> str:
    """
    Build patient-level retrieval text for allergy chunks.

    This function does not require a visit. It uses patient.allergy_registry
    only and does not make risk predictions or allergy inferences.
    """
    patient_id = _safe_text(patient.get("patient_id"))
    allergies = _dict_list(patient.get("allergy_registry"))

    if not allergies:
        if patient_id:
            return (
                f"Allergy retrieval context for patient {patient_id} contains "
                "no documented allergy entries in the allergy_registry."
            )
        return (
            "Allergy retrieval context contains no documented allergy entries "
            "in the allergy_registry."
        )

    sentences: list[str] = []
    if patient_id:
        sentences.append(
            f"Allergy retrieval context for patient {patient_id} includes "
            "documented allergy entries."
        )
    else:
        sentences.append(
            "Allergy retrieval context includes documented allergy entries."
        )

    for allergy in allergies:
        allergy_sentence = _allergy_entry_sentence(allergy)
        if allergy_sentence:
            sentences.append(allergy_sentence)

    return " ".join(sentences)


def _documented_patient_conditions(patient: dict[str, Any]) -> tuple[str, ...]:
    """Return valid documented patient conditions from patient['conditions']."""
    return _ordered_allowed_values(_sequence(patient.get("conditions")), CONDITIONS)


def _documented_visit_diagnoses(visit: dict[str, Any]) -> tuple[str, ...]:
    """Return valid documented visit diagnoses from visit['diagnoses']."""
    return _ordered_allowed_values(_sequence(visit.get("diagnoses")), CONDITIONS)


def _documented_conditions_for_visit(
    patient: dict[str, Any],
    visit: dict[str, Any],
) -> tuple[str, ...]:
    """Return ordered unique patient conditions plus visit diagnoses."""
    return _ordered_unique(
        (
            *_documented_patient_conditions(patient),
            *_documented_visit_diagnoses(visit),
        )
    )


def _lab_type_names(labs: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    """Return documented lab_type names only, preserving deterministic order."""
    values = (_safe_text(lab.get("lab_type")) for lab in labs)
    return _ordered_allowed_values(values, LAB_TYPES)


def _medication_names(
    medications: Iterable[Mapping[str, Any]],
) -> tuple[str, ...]:
    """
    Return documented medication_name values only.

    Medication names are not replaced by whitelist defaults. They are read from
    the structured visit data. Validation remains responsible for rejecting
    non-whitelisted medications before ingestion.
    """
    values = (_safe_text(med.get("medication_name")) for med in medications)
    return _ordered_unique(value for value in values if value)


def _join_phrases(values: Iterable[str]) -> str:
    """Join values deterministically for readable retrieval text."""
    items = _ordered_unique(values)

    if not items:
        return "none"

    if len(items) == 1:
        return items[0]

    if len(items) == 2:
        return f"{items[0]} and {items[1]}"

    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _has_condition_context(
    documented_conditions: Iterable[str],
    condition: str,
) -> bool:
    """Return True only if condition is documented."""
    return condition in set(documented_conditions)


def _lab_condition_context_sentences(
    *,
    documented_conditions: tuple[str, ...],
    lab_names: tuple[str, ...],
) -> tuple[str, ...]:
    """Build safe condition-lab context sentences."""
    sentences: list[str] = []

    for condition, mapped_labs in CONDITION_LAB_CONTEXT.items():
        if not _has_condition_context(documented_conditions, condition):
            continue

        relevant_labs = tuple(lab for lab in mapped_labs if lab in lab_names)
        if not relevant_labs:
            continue

        label = CONDITION_LAB_RETRIEVAL_LABELS[condition]
        sentences.append(
            f"Documented {condition} context allows "
            f"{_join_phrases(relevant_labs)} to be described as {label} "
            "laboratory entries for retrieval matching only."
        )

    return tuple(sentences)


def _lab_flag_pairs(labs: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    """Return deterministic lab_type flag phrases from documented labs."""
    pairs: list[str] = []

    for lab in labs:
        lab_type = _safe_text(lab.get("lab_type"))
        flag = _safe_text(lab.get("flag"))

        if lab_type in LAB_TYPES and flag:
            pairs.append(f"{lab_type} {flag}")

    return _ordered_unique(pairs)


def _medication_detail_sentences(
    medications: Iterable[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Build deterministic medication detail sentences from visit data."""
    sentences: list[str] = []

    for medication in medications:
        name = _safe_text(medication.get("medication_name"))
        if not name:
            continue

        details = []
        medication_class = _safe_text(medication.get("medication_class"))
        dose = _safe_text(medication.get("dose"))
        frequency = _safe_text(medication.get("frequency"))
        route = _safe_text(medication.get("route"))
        start_date = _safe_text(medication.get("start_date"))
        stop_date = _safe_text(medication.get("stop_date"))

        if medication_class:
            details.append(f"class {medication_class}")
        if dose:
            details.append(f"dose {dose}")
        if frequency:
            details.append(f"frequency {frequency}")
        if route:
            details.append(f"route {route}")
        if start_date:
            details.append(f"start date {start_date}")
        if stop_date:
            details.append(f"stop date {stop_date}")

        if details:
            sentences.append(
                f"{name} is documented with {_join_phrases(details)}."
            )
        else:
            sentences.append(
                f"{name} is documented in the prescription entries."
            )

    return tuple(sentences)


def _medication_condition_context_phrases(
    *,
    medications: Iterable[Mapping[str, Any]],
    documented_conditions: tuple[str, ...],
) -> tuple[str, ...]:
    """
    Return medication-condition context phrases only when safe.

    A phrase is safe when:
    1. the medication exists in MEDICATION_WHITELIST, and
    2. the whitelist condition is documented in patient conditions or visit
       diagnoses.
    """
    phrases: list[str] = []

    for medication in medications:
        medication_name = _safe_text(medication.get("medication_name"))
        if medication_name not in MEDICATION_NAMES:
            continue

        whitelist_condition = _safe_text(
            MEDICATION_WHITELIST[medication_name].get("condition")
        )

        if _has_condition_context(documented_conditions, whitelist_condition):
            phrases.append(f"{medication_name} with documented {whitelist_condition}")

    return _ordered_unique(phrases)


def _allergy_entry_sentence(allergy: Mapping[str, Any]) -> str:
    """Build one allergy sentence from documented allergy fields."""
    allergen = _safe_text(allergy.get("allergen"))
    reaction = _safe_text(allergy.get("reaction"))
    severity = _safe_text(allergy.get("severity"))
    recorded_date = _safe_text(allergy.get("recorded_date"))
    source_visit_id = _safe_text(allergy.get("source_visit_id"))

    if not any((allergen, reaction, severity, recorded_date, source_visit_id)):
        return ""

    if allergen:
        sentence = f"Documented allergen {allergen}"
    else:
        sentence = "Documented allergy entry"

    details: list[str] = []
    if reaction:
        details.append(f"reaction {reaction}")
    if severity:
        details.append(f"severity {severity}")
    if recorded_date:
        details.append(f"recorded date {recorded_date}")
    if source_visit_id:
        details.append(f"source visit {source_visit_id}")

    if details:
        sentence += f" has {_join_phrases(details)}."

    else:
        sentence += " is listed in the allergy_registry."

    return sentence


def _metadata_value(patient: Mapping[str, Any], key: str) -> Any:
    """Read one metadata value from patient['metadata'] when available."""
    metadata = patient.get("metadata")
    if not isinstance(metadata, Mapping):
        return ""
    return metadata.get(key, "")


def _sequence(value: Any) -> tuple[Any, ...]:
    """Return a tuple for list or tuple values; otherwise return empty tuple."""
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return ()


def _dict_list(value: Any) -> tuple[Mapping[str, Any], ...]:
    """Return mapping items from a list/tuple; ignore non-dict entries."""
    if not isinstance(value, (list, tuple)):
        return ()

    return tuple(item for item in value if isinstance(item, Mapping))


def _ordered_allowed_values(
    values: Iterable[Any],
    allowed_values: Iterable[str],
) -> tuple[str, ...]:
    """Return ordered unique values that exactly match allowed constants."""
    allowed = set(allowed_values)
    return _ordered_unique(
        text for text in (_safe_text(value) for value in values) if text in allowed
    )


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    """Return values without duplicates while preserving first-seen order."""
    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        text = _safe_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)

    return tuple(output)


def _safe_text(value: Any) -> str:
    """Convert a structured value to a stripped string without inventing data."""
    if value is None:
        return ""
    return str(value).strip()


def _sentence_from_parts(parts: Iterable[str]) -> str:
    """Join sentence parts and ensure final punctuation."""
    text = " ".join(part for part in parts if part).strip()
    if not text:
        return ""
    if text.endswith("."):
        return text
    return f"{text}."


__all__ = [
    "build_retrieval_text",
    "build_doctor_note_retrieval_text",
    "build_lab_retrieval_text",
    "build_prescription_retrieval_text",
    "build_allergy_retrieval_text",
]
