"""
generators/allergy_generator.py

Deterministic allergy registry generation for the v1.7 Lite dataset.

RESPONSIBILITY
--------------
This module populates patient["allergy_registry"] in-place.

It does NOT generate:
    - medications          (→ generators/medication_generator.py)
    - lab records          (→ generators/lab_generator.py)
    - SOAP prose           (→ soap/soap_generator.py)
    - allergy chunks       (→ ingestion/chunker.py)
    - ChromaDB metadata    (→ ingestion/metadata_builder.py)

BLUEPRINT CONTRACT
------------------
blueprint.allergen:
    None          → patient["allergy_registry"] = []
    str allergen  → one allergy record generated from ALLERGY_REACTION_MAP /
                    ALLERGY_SEVERITY_MAP and linked to patient["visits"][0].

ALLERGEN UNIQUENESS
-------------------
Allergens are NOT required to be globally unique across all 15 patients.
Two patients may share the same allergen (e.g. Penicillin in PAT-MOD-001
and PAT-CHR-002).  Patient-scoped retrieval is the safety mechanism.

MEDICATION CONFLICT RULE
------------------------
The allergen must not equal any medication name assigned to this patient.
The check uses exact normalized matching to avoid false positives such as
'Sulfa' conflicting with 'Ferrous sulfate'.

DETERMINISM
-----------
All outputs are deterministic.
No random module is used anywhere in this file.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from config.constants import (
    ALLERGY_REACTION_MAP,
    ALLERGY_SEVERITY_MAP,
    DATE_REGEX,
    MEDICATION_NAMES,
    REQUIRED_ALLERGY_FIELDS,
    SAFE_ALLERGEN_POOL,
    SEVERITIES,
)
from config.patient_blueprints import BLUEPRINT_BY_ID, PatientBlueprint


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

AllergyRecord = dict[str, str]
MedicationLike = dict[str, Any] | str


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------

class AllergyGenerationError(ValueError):
    """Raised when allergy generation cannot proceed safely."""


# ---------------------------------------------------------------------------
# Primary public API
# ---------------------------------------------------------------------------

def generate_allergy_registry_for_patient(
    patient: dict,
    blueprint: PatientBlueprint | None = None,
) -> dict:
    """Populate patient['allergy_registry'] in-place and return patient.

    This is the standard integration point:

        generate_visits_for_patient(patient, blueprint)
        generate_medications_for_patient(patient, blueprint)
        generate_labs_for_patient(patient, blueprint)
        generate_allergy_registry_for_patient(patient, blueprint)

    Args:
        patient:   Patient dict with visits already populated.
        blueprint: PatientBlueprint.  If None, looked up by patient_id.

    Returns:
        The same patient dict with allergy_registry populated.
    """
    if blueprint is None:
        pid = patient.get("patient_id", "")
        if pid not in BLUEPRINT_BY_ID:
            raise AllergyGenerationError(
                f"No blueprint found for patient_id='{pid}'."
            )
        blueprint = BLUEPRINT_BY_ID[pid]

    _validate_preconditions(patient, blueprint)

    if blueprint.allergen is None:
        patient["allergy_registry"] = []
        return patient

    patient["allergy_registry"] = _build_allergy_registry(patient, blueprint)
    return patient


def _build_allergy_registry(
    patient: dict,
    blueprint: PatientBlueprint,
) -> list[AllergyRecord]:
    """Build the allergy registry for a patient with blueprint.allergen set."""
    allergen  = blueprint.allergen
    reaction  = ALLERGY_REACTION_MAP[allergen]
    severity  = ALLERGY_SEVERITY_MAP[allergen]
    pid       = blueprint.patient_id

    _validate_allergy_values(pid, allergen, reaction, severity)

    # Collect all medication names assigned to this patient.
    all_medication_names = _collect_all_medication_names(patient, blueprint)

    contradiction = find_allergen_medication_contradiction(allergen, all_medication_names)
    if contradiction:
        raise AllergyGenerationError(
            f"{pid}: allergen '{allergen}' conflicts with "
            f"medication '{contradiction}'."
        )

    # Source visit: use the first generated visit.
    source_visit = patient["visits"][0]
    record: AllergyRecord = {
        "allergen":        allergen,
        "reaction":        reaction,
        "severity":        severity,
        "recorded_date":   str(source_visit["visit_date"]),
        "source_visit_id": str(source_visit["visit_id"]),
    }

    _validate_allergy_record(record, pid)
    return [record]


# ---------------------------------------------------------------------------
# Backward-compatible aliases
# ---------------------------------------------------------------------------

def generate_allergy_registry(
    patient: dict,
    blueprint: PatientBlueprint | None = None,
) -> dict:
    """Backward-compatible alias for generate_allergy_registry_for_patient."""
    return generate_allergy_registry_for_patient(patient, blueprint)


def build_allergy_registry(
    patient: dict,
    blueprint: PatientBlueprint | None = None,
) -> dict:
    """Backward-compatible alias."""
    return generate_allergy_registry_for_patient(patient, blueprint)


def generate_allergies_for_patient(
    patient: dict,
    blueprint: PatientBlueprint | None = None,
) -> dict:
    """Backward-compatible alias."""
    return generate_allergy_registry_for_patient(patient, blueprint)


def generate_allergies(
    patient: dict,
    blueprint: PatientBlueprint | None = None,
) -> dict:
    """Short backward-compatible alias."""
    return generate_allergy_registry_for_patient(patient, blueprint)


# ---------------------------------------------------------------------------
# Public validation helpers (used by tests and validators)
# ---------------------------------------------------------------------------

def find_allergen_medication_contradiction(
    allergen: str,
    medications: Iterable[MedicationLike],
) -> str | None:
    """Return the conflicting medication name if allergen matches one.

    Uses exact normalized matching to avoid false positives such as
    'Sulfa' matching 'Ferrous sulfate'.

    Returns:
        The conflicting medication name, or None if no conflict.
    """
    clean_allergen = _normalize(allergen)
    if not clean_allergen:
        return None

    for medication in medications:
        if isinstance(medication, str):
            med_name = medication
        elif isinstance(medication, dict):
            med_name = str(medication.get("medication_name", ""))
        else:
            continue

        if not med_name:
            continue

        # Only an exact normalized match counts as a conflict.
        if clean_allergen == _normalize(med_name):
            return med_name

    return None


def allergy_has_contradiction(
    allergen: str,
    medications: Iterable[MedicationLike],
) -> bool:
    """Boolean helper for validators and tests."""
    return find_allergen_medication_contradiction(allergen, medications) is not None


def build_allergy_retrieval_phrase(
    patient_id: str,
    allergy_record: dict[str, Any],
) -> str:
    """Build a retrieval-friendly phrase for chunking tests without creating a chunk.

    The chunker is responsible for actual allergy chunks.
    This helper is a safe wording utility only.
    """
    allergen        = str(allergy_record.get("allergen", "")).strip()
    reaction        = str(allergy_record.get("reaction", "")).strip()
    severity        = str(allergy_record.get("severity", "")).strip()
    source_visit_id = str(allergy_record.get("source_visit_id", "")).strip()

    if not patient_id or not allergen or not reaction:
        raise AllergyGenerationError(
            "Cannot build allergy retrieval phrase without patient_id, allergen, and reaction."
        )

    severity_phrase = f" {severity}" if severity else ""
    source_phrase   = f" documented at {source_visit_id}" if source_visit_id else ""
    return (
        f"Allergy record for {patient_id}: {allergen} allergy "
        f"with{severity_phrase} {reaction} reaction{source_phrase}."
    )


def extract_medication_names_from_visits(visits: list[dict]) -> tuple[str, ...]:
    """Return unique medication names from all generated visits."""
    names: list[str] = []
    for visit in visits:
        for med in visit.get("medications", []):
            if isinstance(med, dict):
                name = str(med.get("medication_name", "")).strip()
            elif isinstance(med, str):
                name = med.strip()
            else:
                continue
            if name:
                names.append(name)
    return tuple(dict.fromkeys(names))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _collect_all_medication_names(
    patient: dict,
    blueprint: PatientBlueprint,
) -> list[str]:
    """Union of medication names from generated visits and blueprint fields."""
    names: list[str] = []

    # From visits (populated by medication_generator).
    names.extend(extract_medication_names_from_visits(patient.get("visits", [])))

    # From blueprint structured fields (guards against future blueprint changes
    # where visit medications may not yet be populated).
    for med_tuple in (
        blueprint.initial_medications,
        blueprint.added_medications,
        blueprint.completed_medications,
        blueprint.stopped_medications,
    ):
        names.extend(med_tuple)

    return list(dict.fromkeys(names))


def _validate_preconditions(patient: dict, blueprint: PatientBlueprint) -> None:
    pid = patient.get("patient_id", "")
    if pid != blueprint.patient_id:
        raise AllergyGenerationError(
            f"patient_id mismatch: patient='{pid}', blueprint='{blueprint.patient_id}'."
        )
    if not patient.get("visits"):
        raise AllergyGenerationError(
            f"{blueprint.patient_id}: patient has no visits. "
            "Run generate_visits_for_patient first."
        )


def _validate_allergy_values(
    patient_id: str,
    allergen: str,
    reaction: str,
    severity: str,
) -> None:
    """Check allergen, reaction, and severity values are valid."""
    if not allergen:
        raise AllergyGenerationError(f"{patient_id}: allergen is required.")
    if not reaction:
        raise AllergyGenerationError(f"{patient_id}: allergy reaction is required.")
    if not severity:
        raise AllergyGenerationError(f"{patient_id}: allergy severity is required.")

    if allergen not in SAFE_ALLERGEN_POOL:
        raise AllergyGenerationError(
            f"{patient_id}: allergen '{allergen}' is not in SAFE_ALLERGEN_POOL."
        )
    if severity not in SEVERITIES:
        raise AllergyGenerationError(
            f"{patient_id}: severity '{severity}' not in SEVERITIES."
        )
    expected_reaction = ALLERGY_REACTION_MAP.get(allergen)
    if expected_reaction and reaction != expected_reaction:
        raise AllergyGenerationError(
            f"{patient_id}: reaction for '{allergen}' must be "
            f"'{expected_reaction}', got '{reaction}'."
        )
    expected_severity = ALLERGY_SEVERITY_MAP.get(allergen)
    if expected_severity and severity != expected_severity:
        raise AllergyGenerationError(
            f"{patient_id}: severity for '{allergen}' must be "
            f"'{expected_severity}', got '{severity}'."
        )


def _validate_allergy_record(record: AllergyRecord, patient_id: str) -> None:
    """Check the generated record against REQUIRED_ALLERGY_FIELDS."""
    missing = [f for f in REQUIRED_ALLERGY_FIELDS if not record.get(f)]
    if missing:
        raise AllergyGenerationError(
            f"{patient_id}: allergy record missing required fields: {missing}."
        )
    # recorded_date format
    if not re.fullmatch(DATE_REGEX, record.get("recorded_date", "")):
        raise AllergyGenerationError(
            f"{patient_id}: recorded_date '{record.get('recorded_date')}' "
            f"does not match DATE_REGEX."
        )
    # source_visit_id non-empty
    if not record.get("source_visit_id"):
        raise AllergyGenerationError(
            f"{patient_id}: source_visit_id must be non-empty."
        )


def _normalize(value: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for exact matching."""
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()
