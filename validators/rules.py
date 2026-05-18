"""
validators/rules.py

Authoritative validation rules V1-V11 for synthetic patient JSON files.

Design goals:
- Keep validation deterministic and side-effect free.
- Return ValidationIssue objects instead of raising exceptions.
- Keep constants/enums imported from config.constants only.
- Keep BP as a vital sign only; never allow BP in labs.
- Preserve the v1.5 validation contract while making the implementation
  easier to read, test, and maintain.

Validation rules:
- V1: Chronological visit order
- V2: Medication/allergy conflict prevention
- V3: Impossible vitals and age bounds
- V4: Required fields, basic schema shape, and forbidden demographics.age
- V5: prior_visit_id and allergy source_visit_id reference integrity
- V6: Duplicate visit_id prevention
- V7: Enum validation, ID pattern consistency, and CKD constraints
- V8: Date format validation
- V9: BP forbidden inside labs
- V10: timeline_events forbidden
- V11: Medication whitelist + frequency + route validation
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from config.constants import (
    AGE_LIMITS,
    BP_FORBIDDEN_LAB_TERMS,
    CONDITIONS,
    DATE_FORMAT,
    DATE_REGEX,
    DOCUMENT_ID_REGEX,
    FLAGS,
    FREQUENCIES,
    ID_PREFIX_TO_TIER,
    LAB_TYPES,
    MEDICATION_WHITELIST,
    PATIENT_ID_REGEX,
    REQUIRED_ALLERGY_FIELDS,
    REQUIRED_DEMOGRAPHICS_FIELDS,
    REQUIRED_LAB_FIELDS,
    REQUIRED_MEDICATION_FIELDS,
    REQUIRED_TOP_LEVEL_FIELDS,
    REQUIRED_VISIT_FIELDS,
    REQUIRED_VITAL_FIELDS,
    ROUTES,
    SCHEMA_VERSION,
    SEVERITIES,
    SEX_VALUES,
    SOAP_SECTIONS,
    TIER_TO_ID_PREFIX,
    TIERS,
    VITAL_LIMITS,
    VISIT_ID_REGEX,
    VISIT_TYPES,
)

Severity = Literal["FAIL", "WARN"]

_PATIENT_ID_RE = re.compile(r"^PAT-(NRM|MOD|CHR)-(\d{3})$")
_VISIT_ID_RE = re.compile(r"^VST-(NRM|MOD|CHR)-(\d{3})-(\d{3})$")
_DOCUMENT_ID_RE = re.compile(r"^DOC-(NRM|MOD|CHR)-(\d{3})-(\d{3})$")


@dataclass(frozen=True)
class ValidationIssue:
    """Validation issue produced by one V-rule."""

    rule_id: str
    severity: Severity
    patient_id: str
    message: str
    location: str = ""


def validate_patient(patient: dict[str, Any]) -> list[ValidationIssue]:
    """Run V1-V11 against a single patient JSON object."""
    issues: list[ValidationIssue] = []

    for rule in (
        validate_v1_chronological_visits,
        validate_v2_allergy_medication_conflicts,
        validate_v3_impossible_vitals,
        validate_v4_required_fields,
        validate_v5_reference_integrity,
        validate_v6_duplicate_visit_ids,
        validate_v7_enums_patterns_and_ckd,
        validate_v8_date_formats,
        validate_v9_bp_forbidden_in_labs,
        validate_v10_timeline_events_forbidden,
        validate_v11_medication_whitelist_frequency_route,
    ):
        try:
            issues.extend(rule(patient))
        except Exception as exc:  # pragma: no cover - defensive validation guard
            issues.append(
                ValidationIssue(
                    rule_id="VALIDATOR",
                    severity="FAIL",
                    patient_id=patient_id_of(patient),
                    location=rule.__name__,
                    message=f"Validator rule crashed unexpectedly: {exc}",
                )
            )

    return issues


def patient_id_of(patient: dict[str, Any]) -> str:
    """Return patient_id safely for validation messages."""
    return str(patient.get("patient_id", "<missing-patient-id>"))


# ---------------------------------------------------------------------
# V1
# ---------------------------------------------------------------------


def validate_v1_chronological_visits(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V1: Visit dates must be chronological in the visits array."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)
    previous_date = None

    for visit in _safe_list(patient.get("visits")):
        if not isinstance(visit, dict):
            continue

        visit_id = visit.get("visit_id", "<missing-visit-id>")
        visit_date_raw = visit.get("visit_date")

        try:
            visit_date = datetime.strptime(str(visit_date_raw), DATE_FORMAT).date()
        except (TypeError, ValueError):
            # V8 reports invalid date formats.
            continue

        if previous_date is not None and visit_date < previous_date:
            issues.append(
                _issue(
                    "V1",
                    "FAIL",
                    pid,
                    f"visits.{visit_id}.visit_date",
                    (
                        f"Visit date {visit_date_raw} is earlier than the previous "
                        "visit date."
                    ),
                )
            )

        previous_date = visit_date

    return issues


# ---------------------------------------------------------------------
# V2
# ---------------------------------------------------------------------


def validate_v2_allergy_medication_conflicts(
    patient: dict[str, Any],
) -> list[ValidationIssue]:
    """V2: Medication names must not match allergy_registry allergens."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    allergens = {
        _normalized(allergy.get("allergen"))
        for allergy in _safe_list(patient.get("allergy_registry"))
        if isinstance(allergy, dict) and _normalized(allergy.get("allergen"))
    }

    for visit in _safe_list(patient.get("visits")):
        if not isinstance(visit, dict):
            continue

        visit_id = visit.get("visit_id", "<missing-visit-id>")

        for med_index, medication in enumerate(_safe_list(visit.get("medications"))):
            if not isinstance(medication, dict):
                continue

            med_name = _normalized(medication.get("medication_name"))
            if med_name and med_name in allergens:
                issues.append(
                    _issue(
                        "V2",
                        "FAIL",
                        pid,
                        f"visits.{visit_id}.medications[{med_index}].medication_name",
                        (
                            f"Medication '{medication.get('medication_name')}' "
                            "conflicts with allergy_registry."
                        ),
                    )
                )

    return issues


# ---------------------------------------------------------------------
# V3
# ---------------------------------------------------------------------


def validate_v3_impossible_vitals(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V3: Vitals must be physically plausible; age must remain 18-80."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)
    demographics = _safe_dict(patient.get("demographics"))

    for visit in _safe_list(patient.get("visits")):
        if not isinstance(visit, dict):
            continue

        visit_id = visit.get("visit_id", "<missing-visit-id>")
        vitals = visit.get("vitals")

        if not isinstance(vitals, dict):
            issues.append(
                _issue(
                    "V3",
                    "FAIL",
                    pid,
                    f"visits.{visit_id}.vitals",
                    "vitals must be an object.",
                )
            )
            continue

        for vital_name, (minimum, maximum) in VITAL_LIMITS.items():
            if vital_name not in vitals:
                continue

            issues.extend(
                _validate_numeric_range(
                    rule_id="V3",
                    patient_id=pid,
                    location=f"visits.{visit_id}.vitals.{vital_name}",
                    label=f"Vital '{vital_name}'",
                    value=vitals.get(vital_name),
                    minimum=minimum,
                    maximum=maximum,
                    inclusive_minimum=True,
                    inclusive_maximum=True,
                )
            )

        if "weight_kg" in vitals:
            issues.extend(
                _validate_numeric_range(
                    rule_id="V3",
                    patient_id=pid,
                    location=f"visits.{visit_id}.vitals.weight_kg",
                    label="Vital 'weight_kg'",
                    value=vitals.get("weight_kg"),
                    minimum=25,
                    maximum=250,
                    inclusive_minimum=False,
                    inclusive_maximum=True,
                )
            )

        age = _age_at_visit(
            demographics.get("date_of_birth"),
            visit.get("visit_date"),
        )
        if age is None:
            continue

        min_age, max_age = AGE_LIMITS
        if not min_age <= age <= max_age:
            issues.append(
                _issue(
                    "V3",
                    "FAIL",
                    pid,
                    f"visits.{visit_id}",
                    f"Age at visit is {age}, outside allowed range {min_age}-{max_age}.",
                )
            )

    return issues


# ---------------------------------------------------------------------
# V4
# ---------------------------------------------------------------------


def validate_v4_required_fields(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V4: Required fields, basic schema shape, and forbidden demographics.age."""
    pid = patient_id_of(patient)
    issues: list[ValidationIssue] = []

    issues.extend(_validate_top_level_fields(patient, pid))
    issues.extend(_validate_demographics_shape(patient, pid))
    issues.extend(_validate_metadata_shape(patient, pid))
    issues.extend(_validate_conditions_shape(patient, pid))
    issues.extend(_validate_visits_shape(patient, pid))
    issues.extend(_validate_allergy_registry_shape(patient, pid))

    return issues


# ---------------------------------------------------------------------
# V5
# ---------------------------------------------------------------------


def validate_v5_reference_integrity(patient: dict[str, Any]) -> list[ValidationIssue]:
    """
    V5: prior_visit_id and allergy source_visit_id must reference existing visits.

    Severity remains WARN because these are fix-before-demo integrity issues.
    """
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    visit_ids = {
        str(visit.get("visit_id"))
        for visit in _safe_list(patient.get("visits"))
        if isinstance(visit, dict) and visit.get("visit_id")
    }

    for visit in _safe_list(patient.get("visits")):
        if not isinstance(visit, dict):
            continue

        visit_id = visit.get("visit_id", "<missing-visit-id>")
        prior_visit_id = visit.get("prior_visit_id")

        if prior_visit_id is not None and str(prior_visit_id) not in visit_ids:
            issues.append(
                _issue(
                    "V5",
                    "WARN",
                    pid,
                    f"visits.{visit_id}.prior_visit_id",
                    (
                        f"prior_visit_id '{prior_visit_id}' does not reference "
                        "an existing visit."
                    ),
                )
            )

    for allergy_index, allergy in enumerate(_safe_list(patient.get("allergy_registry"))):
        if not isinstance(allergy, dict):
            continue

        source_visit_id = allergy.get("source_visit_id")
        if source_visit_id is not None and str(source_visit_id) not in visit_ids:
            issues.append(
                _issue(
                    "V5",
                    "WARN",
                    pid,
                    f"allergy_registry[{allergy_index}].source_visit_id",
                    (
                        f"source_visit_id '{source_visit_id}' does not reference "
                        "an existing visit."
                    ),
                )
            )

    return issues


# ---------------------------------------------------------------------
# V6
# ---------------------------------------------------------------------


def validate_v6_duplicate_visit_ids(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V6: visit_id values must be unique inside each patient file."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    seen: set[str] = set()
    duplicates: set[str] = set()

    for visit in _safe_list(patient.get("visits")):
        if not isinstance(visit, dict):
            continue

        visit_id = visit.get("visit_id")
        if not visit_id:
            continue

        visit_id_text = str(visit_id)
        if visit_id_text in seen:
            duplicates.add(visit_id_text)
        seen.add(visit_id_text)

    for duplicate in sorted(duplicates):
        issues.append(
            _issue(
                "V6",
                "FAIL",
                pid,
                "visits.visit_id",
                f"Duplicate visit_id found: {duplicate}.",
            )
        )

    return issues


# ---------------------------------------------------------------------
# V7
# ---------------------------------------------------------------------


def validate_v7_enums_patterns_and_ckd(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V7: Enum values, ID contracts, and CKD co-occurrence constraints."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    issues.extend(_validate_id_patterns_and_consistency(patient))
    issues.extend(_validate_patient_level_enums(patient, pid))
    issues.extend(_validate_ckd_constraints(patient, pid))
    issues.extend(_validate_allergy_enums(patient, pid))
    issues.extend(_validate_visit_level_enums(patient, pid))

    return issues


# ---------------------------------------------------------------------
# V8
# ---------------------------------------------------------------------


def validate_v8_date_formats(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V8: Date fields must use YYYY-MM-DD and represent valid calendar dates."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    for location, value in _collect_date_fields(patient):
        if value is None:
            continue

        if not isinstance(value, str) or not re.match(DATE_REGEX, value):
            issues.append(
                _issue(
                    "V8",
                    "FAIL",
                    pid,
                    location,
                    f"Invalid date format '{value}'. Expected YYYY-MM-DD.",
                )
            )
            continue

        try:
            datetime.strptime(value, DATE_FORMAT)
        except ValueError:
            issues.append(
                _issue(
                    "V8",
                    "FAIL",
                    pid,
                    location,
                    f"Invalid calendar date '{value}'.",
                )
            )

    return issues


# ---------------------------------------------------------------------
# V9
# ---------------------------------------------------------------------


def validate_v9_bp_forbidden_in_labs(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V9: Blood pressure must never appear inside visit.labs[]."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)
    forbidden_terms = {_normalized(term) for term in BP_FORBIDDEN_LAB_TERMS}

    for visit in _safe_list(patient.get("visits")):
        if not isinstance(visit, dict):
            continue

        visit_id = visit.get("visit_id", "<missing-visit-id>")

        for lab_index, lab in enumerate(_safe_list(visit.get("labs"))):
            if not isinstance(lab, dict):
                continue

            lab_type = _normalized(lab.get("lab_type"))
            if _contains_forbidden_bp_term(lab_type, forbidden_terms):
                issues.append(
                    _issue(
                        "V9",
                        "FAIL",
                        pid,
                        f"visits.{visit_id}.labs[{lab_index}].lab_type",
                        f"BP value found in labs array at {visit_id}.",
                    )
                )

            for key in lab.keys():
                key_normalized = _normalized(key)
                if _contains_forbidden_bp_term(key_normalized, forbidden_terms):
                    issues.append(
                        _issue(
                            "V9",
                            "FAIL",
                            pid,
                            f"visits.{visit_id}.labs[{lab_index}].{key}",
                            f"BP-like field '{key}' found inside lab object.",
                        )
                    )

    return issues


# ---------------------------------------------------------------------
# V10
# ---------------------------------------------------------------------


def validate_v10_timeline_events_forbidden(
    patient: dict[str, Any],
) -> list[ValidationIssue]:
    """V10: timeline_events is forbidden anywhere in patient JSON."""
    pid = patient_id_of(patient)

    return [
        _issue(
            "V10",
            "FAIL",
            pid,
            location,
            "timeline_events field is forbidden. Generate timeline from visits.",
        )
        for location in _find_key_locations(patient, forbidden_key="timeline_events")
    ]


# ---------------------------------------------------------------------
# V11
# ---------------------------------------------------------------------


def validate_v11_medication_whitelist_frequency_route(
    patient: dict[str, Any],
) -> list[ValidationIssue]:
    """V11: Medications must use the whitelist, expected frequency, and expected route."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    for visit in _safe_list(patient.get("visits")):
        if not isinstance(visit, dict):
            continue

        visit_id = visit.get("visit_id", "<missing-visit-id>")

        for med_index, med in enumerate(_safe_list(visit.get("medications"))):
            if not isinstance(med, dict):
                continue

            med_name = med.get("medication_name")
            location = f"visits.{visit_id}.medications[{med_index}]"

            if med_name not in MEDICATION_WHITELIST:
                issues.append(
                    _issue(
                        "V11",
                        "FAIL",
                        pid,
                        f"{location}.medication_name",
                        f"Medication '{med_name}' is not in whitelist.",
                    )
                )
                continue

            expected = MEDICATION_WHITELIST[med_name]
            frequency = med.get("frequency")
            route = med.get("route")

            if frequency not in FREQUENCIES:
                issues.append(
                    _issue(
                        "V11",
                        "FAIL",
                        pid,
                        f"{location}.frequency",
                        f"Invalid frequency '{frequency}'.",
                    )
                )
            elif frequency != expected["frequency"]:
                issues.append(
                    _issue(
                        "V11",
                        "FAIL",
                        pid,
                        f"{location}.frequency",
                        (
                            f"Medication '{med_name}' frequency must be "
                            f"'{expected['frequency']}', got '{frequency}'."
                        ),
                    )
                )

            if route not in ROUTES:
                issues.append(
                    _issue(
                        "V11",
                        "FAIL",
                        pid,
                        f"{location}.route",
                        f"Invalid route '{route}'.",
                    )
                )
            elif route != expected["route"]:
                issues.append(
                    _issue(
                        "V11",
                        "FAIL",
                        pid,
                        f"{location}.route",
                        (
                            f"Medication '{med_name}' route must be "
                            f"'{expected['route']}', got '{route}'."
                        ),
                    )
                )

    return issues


# ---------------------------------------------------------------------
# V4 helper functions
# ---------------------------------------------------------------------


def _validate_top_level_fields(
    patient: dict[str, Any],
    patient_id: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in patient:
            issues.append(
                _issue(
                    "V4",
                    "FAIL",
                    patient_id,
                    field,
                    f"Missing top-level field '{field}'.",
                )
            )

    if patient.get("schema_version") != SCHEMA_VERSION:
        issues.append(
            _issue(
                "V4",
                "FAIL",
                patient_id,
                "schema_version",
                f"schema_version must be '{SCHEMA_VERSION}'.",
            )
        )

    return issues


def _validate_demographics_shape(
    patient: dict[str, Any],
    patient_id: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    demographics = patient.get("demographics")

    if not isinstance(demographics, dict):
        return [
            _issue(
                "V4",
                "FAIL",
                patient_id,
                "demographics",
                "demographics must be an object.",
            )
        ]

    for field in REQUIRED_DEMOGRAPHICS_FIELDS:
        if field not in demographics:
            issues.append(
                _issue(
                    "V4",
                    "FAIL",
                    patient_id,
                    f"demographics.{field}",
                    f"Missing demographics field '{field}'.",
                )
            )

    if "age" in demographics:
        issues.append(
            _issue(
                "V4",
                "FAIL",
                patient_id,
                "demographics.age",
                "demographics.age is forbidden. Use date_of_birth only.",
            )
        )

    return issues


def _validate_metadata_shape(
    patient: dict[str, Any],
    patient_id: str,
) -> list[ValidationIssue]:
    metadata = patient.get("metadata")

    if not isinstance(metadata, dict):
        return [
            _issue(
                "V4",
                "FAIL",
                patient_id,
                "metadata",
                "metadata must be an object.",
            )
        ]

    if "tier" not in metadata:
        return [
            _issue(
                "V4",
                "FAIL",
                patient_id,
                "metadata.tier",
                "Missing metadata field 'tier'.",
            )
        ]

    return []


def _validate_conditions_shape(
    patient: dict[str, Any],
    patient_id: str,
) -> list[ValidationIssue]:
    if not isinstance(patient.get("conditions"), list):
        return [
            _issue(
                "V4",
                "FAIL",
                patient_id,
                "conditions",
                "conditions must be an array.",
            )
        ]

    return []


def _validate_visits_shape(
    patient: dict[str, Any],
    patient_id: str,
) -> list[ValidationIssue]:
    visits = patient.get("visits")
    if not isinstance(visits, list):
        return [
            _issue(
                "V4",
                "FAIL",
                patient_id,
                "visits",
                "visits must be an array.",
            )
        ]

    issues: list[ValidationIssue] = []
    for visit_index, visit in enumerate(visits):
        if not isinstance(visit, dict):
            issues.append(
                _issue(
                    "V4",
                    "FAIL",
                    patient_id,
                    f"visits[{visit_index}]",
                    "visit must be an object.",
                )
            )
            continue

        issues.extend(_validate_single_visit_shape(patient_id, visit, visit_index))

    return issues


def _validate_single_visit_shape(
    patient_id: str,
    visit: dict[str, Any],
    visit_index: int,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    visit_id = str(visit.get("visit_id", f"<visit-index-{visit_index}>"))

    for field in REQUIRED_VISIT_FIELDS:
        if field not in visit:
            issues.append(
                _issue(
                    "V4",
                    "WARN",
                    patient_id,
                    f"visits.{visit_id}.{field}",
                    f"Missing visit field '{field}'.",
                )
            )

    issues.extend(_validate_visit_list_field(patient_id, visit, visit_id, "diagnoses"))
    issues.extend(_validate_visit_list_field(patient_id, visit, visit_id, "linked_documents"))
    issues.extend(_validate_vitals_shape(patient_id, visit, visit_id))
    issues.extend(_validate_labs_shape(patient_id, visit, visit_id))
    issues.extend(_validate_medications_shape(patient_id, visit, visit_id))
    issues.extend(_validate_soap_shape(patient_id, visit, visit_id))

    return issues


def _validate_visit_list_field(
    patient_id: str,
    visit: dict[str, Any],
    visit_id: str,
    field_name: str,
) -> list[ValidationIssue]:
    if field_name in visit and not isinstance(visit.get(field_name), list):
        return [
            _issue(
                "V4",
                "FAIL",
                patient_id,
                f"visits.{visit_id}.{field_name}",
                f"{field_name} must be an array.",
            )
        ]

    return []


def _validate_vitals_shape(
    patient_id: str,
    visit: dict[str, Any],
    visit_id: str,
) -> list[ValidationIssue]:
    vitals = visit.get("vitals")
    if not isinstance(vitals, dict):
        return [
            _issue(
                "V4",
                "FAIL",
                patient_id,
                f"visits.{visit_id}.vitals",
                "vitals must be an object.",
            )
        ]

    return [
        _issue(
            "V4",
            "FAIL",
            patient_id,
            f"visits.{visit_id}.vitals.{field}",
            f"Missing vital field '{field}'.",
        )
        for field in REQUIRED_VITAL_FIELDS
        if field not in vitals
    ]


def _validate_labs_shape(
    patient_id: str,
    visit: dict[str, Any],
    visit_id: str,
) -> list[ValidationIssue]:
    labs = visit.get("labs", [])
    if not isinstance(labs, list):
        return [
            _issue(
                "V4",
                "FAIL",
                patient_id,
                f"visits.{visit_id}.labs",
                "labs must be an array.",
            )
        ]

    issues: list[ValidationIssue] = []
    for lab_index, lab in enumerate(labs):
        if not isinstance(lab, dict):
            issues.append(
                _issue(
                    "V4",
                    "FAIL",
                    patient_id,
                    f"visits.{visit_id}.labs[{lab_index}]",
                    "lab must be an object.",
                )
            )
            continue

        for field in REQUIRED_LAB_FIELDS:
            if field not in lab:
                issues.append(
                    _issue(
                        "V4",
                        "FAIL",
                        patient_id,
                        f"visits.{visit_id}.labs[{lab_index}].{field}",
                        f"Missing lab field '{field}'.",
                    )
                )

    return issues


def _validate_medications_shape(
    patient_id: str,
    visit: dict[str, Any],
    visit_id: str,
) -> list[ValidationIssue]:
    medications = visit.get("medications", [])
    if not isinstance(medications, list):
        return [
            _issue(
                "V4",
                "FAIL",
                patient_id,
                f"visits.{visit_id}.medications",
                "medications must be an array.",
            )
        ]

    issues: list[ValidationIssue] = []
    for med_index, med in enumerate(medications):
        if not isinstance(med, dict):
            issues.append(
                _issue(
                    "V4",
                    "FAIL",
                    patient_id,
                    f"visits.{visit_id}.medications[{med_index}]",
                    "medication must be an object.",
                )
            )
            continue

        for field in REQUIRED_MEDICATION_FIELDS:
            if field not in med:
                issues.append(
                    _issue(
                        "V4",
                        "FAIL",
                        patient_id,
                        f"visits.{visit_id}.medications[{med_index}].{field}",
                        f"Missing medication field '{field}'.",
                    )
                )

    return issues


def _validate_soap_shape(
    patient_id: str,
    visit: dict[str, Any],
    visit_id: str,
) -> list[ValidationIssue]:
    soap_note = visit.get("soap_note")
    if not isinstance(soap_note, dict):
        return [
            _issue(
                "V4",
                "FAIL",
                patient_id,
                f"visits.{visit_id}.soap_note",
                "soap_note must be an object.",
            )
        ]

    return [
        _issue(
            "V4",
            "FAIL",
            patient_id,
            f"visits.{visit_id}.soap_note.{section}",
            f"Missing SOAP section '{section}'.",
        )
        for section in SOAP_SECTIONS
        if section not in soap_note
    ]


def _validate_allergy_registry_shape(
    patient: dict[str, Any],
    patient_id: str,
) -> list[ValidationIssue]:
    allergy_registry = patient.get("allergy_registry")
    if not isinstance(allergy_registry, list):
        return [
            _issue(
                "V4",
                "FAIL",
                patient_id,
                "allergy_registry",
                "allergy_registry must be an array.",
            )
        ]

    issues: list[ValidationIssue] = []
    for allergy_index, allergy in enumerate(allergy_registry):
        if not isinstance(allergy, dict):
            issues.append(
                _issue(
                    "V4",
                    "FAIL",
                    patient_id,
                    f"allergy_registry[{allergy_index}]",
                    "allergy record must be an object.",
                )
            )
            continue

        for field in REQUIRED_ALLERGY_FIELDS:
            if field not in allergy:
                issues.append(
                    _issue(
                        "V4",
                        "FAIL",
                        patient_id,
                        f"allergy_registry[{allergy_index}].{field}",
                        f"Missing allergy field '{field}'.",
                    )
                )

    return issues


# ---------------------------------------------------------------------
# V7 helper functions
# ---------------------------------------------------------------------


def _validate_id_patterns_and_consistency(
    patient: dict[str, Any],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    patient_id = patient.get("patient_id")
    patient_identity = _parse_patient_id(patient_id)

    if patient_identity is None:
        issues.append(
            _issue(
                "V7",
                "FAIL",
                pid,
                "patient_id",
                f"Invalid patient_id format '{patient_id}'.",
            )
        )
    else:
        issues.extend(_validate_patient_id_matches_tier(patient, pid, patient_identity))

    for visit_index, visit in enumerate(_safe_list(patient.get("visits"))):
        if not isinstance(visit, dict):
            continue

        visit_id = visit.get("visit_id")
        visit_identity = _parse_visit_id(visit_id)
        location_prefix = f"visits[{visit_index}]"

        if visit_identity is None:
            issues.append(
                _issue(
                    "V7",
                    "FAIL",
                    pid,
                    f"{location_prefix}.visit_id",
                    f"Invalid visit_id format '{visit_id}'.",
                )
            )
        elif patient_identity is not None:
            issues.extend(
                _validate_child_id_matches_patient(
                    rule_id="V7",
                    patient_id=pid,
                    location=f"{location_prefix}.visit_id",
                    child_label="visit_id",
                    child_value=str(visit_id),
                    child_prefix=visit_identity[0],
                    child_patient_number=visit_identity[1],
                    patient_prefix=patient_identity[0],
                    patient_number=patient_identity[1],
                )
            )

        prior_visit_id = visit.get("prior_visit_id")
        if prior_visit_id is not None:
            prior_identity = _parse_visit_id(prior_visit_id)
            if prior_identity is None:
                issues.append(
                    _issue(
                        "V7",
                        "FAIL",
                        pid,
                        f"{location_prefix}.prior_visit_id",
                        f"Invalid prior_visit_id format '{prior_visit_id}'.",
                    )
                )
            elif patient_identity is not None:
                issues.extend(
                    _validate_child_id_matches_patient(
                        rule_id="V7",
                        patient_id=pid,
                        location=f"{location_prefix}.prior_visit_id",
                        child_label="prior_visit_id",
                        child_value=str(prior_visit_id),
                        child_prefix=prior_identity[0],
                        child_patient_number=prior_identity[1],
                        patient_prefix=patient_identity[0],
                        patient_number=patient_identity[1],
                    )
                )

        linked_documents = visit.get("linked_documents", [])
        if isinstance(linked_documents, list):
            for doc_index, document_id in enumerate(linked_documents):
                document_identity = _parse_document_id(document_id)
                document_location = f"{location_prefix}.linked_documents[{doc_index}]"

                if document_identity is None:
                    issues.append(
                        _issue(
                            "V7",
                            "FAIL",
                            pid,
                            document_location,
                            f"Invalid document_id format '{document_id}'.",
                        )
                    )
                elif patient_identity is not None:
                    issues.extend(
                        _validate_child_id_matches_patient(
                            rule_id="V7",
                            patient_id=pid,
                            location=document_location,
                            child_label="document_id",
                            child_value=str(document_id),
                            child_prefix=document_identity[0],
                            child_patient_number=document_identity[1],
                            patient_prefix=patient_identity[0],
                            patient_number=patient_identity[1],
                        )
                    )

    for allergy_index, allergy in enumerate(_safe_list(patient.get("allergy_registry"))):
        if not isinstance(allergy, dict):
            continue

        source_visit_id = allergy.get("source_visit_id")
        source_identity = _parse_visit_id(source_visit_id)
        location = f"allergy_registry[{allergy_index}].source_visit_id"

        if source_identity is None:
            issues.append(
                _issue(
                    "V7",
                    "FAIL",
                    pid,
                    location,
                    f"Invalid source_visit_id format '{source_visit_id}'.",
                )
            )
        elif patient_identity is not None:
            issues.extend(
                _validate_child_id_matches_patient(
                    rule_id="V7",
                    patient_id=pid,
                    location=location,
                    child_label="source_visit_id",
                    child_value=str(source_visit_id),
                    child_prefix=source_identity[0],
                    child_patient_number=source_identity[1],
                    patient_prefix=patient_identity[0],
                    patient_number=patient_identity[1],
                )
            )

    return issues


def _validate_patient_id_matches_tier(
    patient: dict[str, Any],
    patient_id: str,
    patient_identity: tuple[str, str],
) -> list[ValidationIssue]:
    metadata = _safe_dict(patient.get("metadata"))
    tier = metadata.get("tier")

    if tier not in TIERS:
        return []

    expected_prefix = TIER_TO_ID_PREFIX[tier]
    actual_prefix = patient_identity[0]

    if actual_prefix != expected_prefix:
        return [
            _issue(
                "V7",
                "FAIL",
                patient_id,
                "patient_id",
                (
                    f"patient_id prefix '{actual_prefix}' does not match "
                    f"metadata.tier='{tier}' expected prefix '{expected_prefix}'."
                ),
            )
        ]

    return []


def _validate_child_id_matches_patient(
    *,
    rule_id: str,
    patient_id: str,
    location: str,
    child_label: str,
    child_value: str,
    child_prefix: str,
    child_patient_number: str,
    patient_prefix: str,
    patient_number: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if child_prefix != patient_prefix:
        issues.append(
            _issue(
                rule_id,
                "FAIL",
                patient_id,
                location,
                (
                    f"{child_label} '{child_value}' prefix '{child_prefix}' does not "
                    f"match patient prefix '{patient_prefix}'."
                ),
            )
        )

    if child_patient_number != patient_number:
        issues.append(
            _issue(
                rule_id,
                "FAIL",
                patient_id,
                location,
                (
                    f"{child_label} '{child_value}' patient number "
                    f"'{child_patient_number}' does not match patient number "
                    f"'{patient_number}'."
                ),
            )
        )

    return issues


def _validate_patient_level_enums(
    patient: dict[str, Any],
    patient_id: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    metadata = _safe_dict(patient.get("metadata"))
    tier = metadata.get("tier")
    if tier not in TIERS:
        issues.append(
            _issue("V7", "FAIL", patient_id, "metadata.tier", f"Invalid tier '{tier}'.")
        )

    demographics = _safe_dict(patient.get("demographics"))
    sex = demographics.get("sex")
    if sex not in SEX_VALUES:
        issues.append(
            _issue("V7", "FAIL", patient_id, "demographics.sex", f"Invalid sex '{sex}'.")
        )

    if isinstance(patient.get("conditions"), list):
        for condition_index, condition in enumerate(patient["conditions"]):
            if condition not in CONDITIONS:
                issues.append(
                    _issue(
                        "V7",
                        "FAIL",
                        patient_id,
                        f"conditions[{condition_index}]",
                        f"Invalid condition enum '{condition}'.",
                    )
                )

    return issues


def _validate_ckd_constraints(
    patient: dict[str, Any],
    patient_id: str,
) -> list[ValidationIssue]:
    if not isinstance(patient.get("conditions"), list):
        return []

    issues: list[ValidationIssue] = []
    conditions = set(patient["conditions"])
    tier = _safe_dict(patient.get("metadata")).get("tier")

    if "CKD" not in conditions:
        return issues

    if tier != "chronic":
        issues.append(
            _issue(
                "V7",
                "FAIL",
                patient_id,
                "conditions",
                "CKD requires metadata.tier='chronic'.",
            )
        )

    for required_condition in ("T2DM", "HTN"):
        if required_condition not in conditions:
            issues.append(
                _issue(
                    "V7",
                    "FAIL",
                    patient_id,
                    "conditions",
                    f"CKD requires co-occurring condition '{required_condition}'.",
                )
            )

    return issues


def _validate_allergy_enums(
    patient: dict[str, Any],
    patient_id: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for allergy_index, allergy in enumerate(_safe_list(patient.get("allergy_registry"))):
        if not isinstance(allergy, dict):
            continue

        severity = allergy.get("severity")
        if severity not in SEVERITIES:
            issues.append(
                _issue(
                    "V7",
                    "FAIL",
                    patient_id,
                    f"allergy_registry[{allergy_index}].severity",
                    f"Invalid allergy severity '{severity}'.",
                )
            )

    return issues


def _validate_visit_level_enums(
    patient: dict[str, Any],
    patient_id: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for visit in _safe_list(patient.get("visits")):
        if not isinstance(visit, dict):
            continue

        visit_id = visit.get("visit_id", "<missing-visit-id>")

        visit_type = visit.get("visit_type")
        if visit_type not in VISIT_TYPES:
            issues.append(
                _issue(
                    "V7",
                    "FAIL",
                    patient_id,
                    f"visits.{visit_id}.visit_type",
                    f"Invalid visit_type '{visit_type}'.",
                )
            )

        if isinstance(visit.get("diagnoses"), list):
            for diagnosis_index, diagnosis in enumerate(visit["diagnoses"]):
                if diagnosis not in CONDITIONS:
                    issues.append(
                        _issue(
                            "V7",
                            "FAIL",
                            patient_id,
                            f"visits.{visit_id}.diagnoses[{diagnosis_index}]",
                            f"Invalid diagnosis enum '{diagnosis}'.",
                        )
                    )

        if isinstance(visit.get("labs"), list):
            issues.extend(_validate_lab_enums(patient_id, visit_id, visit["labs"]))

        if isinstance(visit.get("medications"), list):
            issues.extend(_validate_medication_enums(patient_id, visit_id, visit["medications"]))

    return issues


def _validate_lab_enums(
    patient_id: str,
    visit_id: Any,
    labs: list[Any],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for lab_index, lab in enumerate(labs):
        if not isinstance(lab, dict):
            continue

        lab_type = lab.get("lab_type")
        if lab_type not in LAB_TYPES:
            issues.append(
                _issue(
                    "V7",
                    "FAIL",
                    patient_id,
                    f"visits.{visit_id}.labs[{lab_index}].lab_type",
                    f"Invalid lab_type '{lab_type}'.",
                )
            )

        flag = lab.get("flag")
        if flag not in FLAGS:
            issues.append(
                _issue(
                    "V7",
                    "FAIL",
                    patient_id,
                    f"visits.{visit_id}.labs[{lab_index}].flag",
                    f"Invalid lab flag '{flag}'.",
                )
            )

    return issues


def _validate_medication_enums(
    patient_id: str,
    visit_id: Any,
    medications: list[Any],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for med_index, med in enumerate(medications):
        if not isinstance(med, dict):
            continue

        frequency = med.get("frequency")
        if frequency not in FREQUENCIES:
            issues.append(
                _issue(
                    "V7",
                    "FAIL",
                    patient_id,
                    f"visits.{visit_id}.medications[{med_index}].frequency",
                    f"Invalid frequency '{frequency}'.",
                )
            )

        route = med.get("route")
        if route not in ROUTES:
            issues.append(
                _issue(
                    "V7",
                    "FAIL",
                    patient_id,
                    f"visits.{visit_id}.medications[{med_index}].route",
                    f"Invalid route '{route}'.",
                )
            )

    return issues


# ---------------------------------------------------------------------
# Generic helper functions
# ---------------------------------------------------------------------


def _issue(
    rule_id: str,
    severity: Severity,
    patient_id: str,
    location: str,
    message: str,
) -> ValidationIssue:
    return ValidationIssue(
        rule_id=rule_id,
        severity=severity,
        patient_id=patient_id,
        location=location,
        message=message,
    )


def _safe_list(value: Any) -> list[Any]:
    """Return value if it is a list, otherwise an empty list."""
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict[str, Any]:
    """Return value if it is a dict, otherwise an empty dict."""
    return value if isinstance(value, dict) else {}


def _normalized(value: Any) -> str:
    """Normalize values for case-insensitive comparison."""
    return str(value).strip().lower()


def _parse_patient_id(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, str) or not re.match(PATIENT_ID_REGEX, value):
        return None

    match = _PATIENT_ID_RE.match(value)
    if not match:
        return None

    return match.group(1), match.group(2)


def _parse_visit_id(value: Any) -> tuple[str, str, str] | None:
    if not isinstance(value, str) or not re.match(VISIT_ID_REGEX, value):
        return None

    match = _VISIT_ID_RE.match(value)
    if not match:
        return None

    return match.group(1), match.group(2), match.group(3)


def _parse_document_id(value: Any) -> tuple[str, str, str] | None:
    if not isinstance(value, str) or not re.match(DOCUMENT_ID_REGEX, value):
        return None

    match = _DOCUMENT_ID_RE.match(value)
    if not match:
        return None

    return match.group(1), match.group(2), match.group(3)


def _validate_numeric_range(
    *,
    rule_id: str,
    patient_id: str,
    location: str,
    label: str,
    value: Any,
    minimum: float,
    maximum: float,
    inclusive_minimum: bool,
    inclusive_maximum: bool,
) -> list[ValidationIssue]:
    """Validate a numeric value against a bounded range."""
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return [
            _issue(
                rule_id,
                "FAIL",
                patient_id,
                location,
                f"{label} must be numeric.",
            )
        ]

    min_ok = numeric_value >= minimum if inclusive_minimum else numeric_value > minimum
    max_ok = numeric_value <= maximum if inclusive_maximum else numeric_value < maximum

    if min_ok and max_ok:
        return []

    min_operator = ">=" if inclusive_minimum else ">"
    max_operator = "<=" if inclusive_maximum else "<"

    return [
        _issue(
            rule_id,
            "FAIL",
            patient_id,
            location,
            (
                f"{label}={numeric_value} outside allowed range "
                f"{min_operator}{minimum} and {max_operator}{maximum}."
            ),
        )
    ]


def _age_at_visit(date_of_birth: Any, visit_date: Any) -> int | None:
    """Calculate age at visit. Return None when either date is invalid."""
    try:
        dob = datetime.strptime(str(date_of_birth), DATE_FORMAT).date()
        visit = datetime.strptime(str(visit_date), DATE_FORMAT).date()
    except (TypeError, ValueError):
        return None

    years = visit.year - dob.year
    before_birthday = (visit.month, visit.day) < (dob.month, dob.day)
    return years - int(before_birthday)


def _collect_date_fields(obj: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """
    Recursively collect date-like fields for V8.

    event_date remains included for backward validation coverage even though the
    locked patient schema should not require it.
    """
    date_keys = {
        "visit_date",
        "recorded_date",
        "start_date",
        "stop_date",
        "date_of_birth",
        "event_date",
    }
    found: list[tuple[str, Any]] = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            location = f"{prefix}.{key}" if prefix else key

            if key in date_keys:
                found.append((location, value))

            found.extend(_collect_date_fields(value, location))

    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            location = f"{prefix}[{index}]" if prefix else f"[{index}]"
            found.extend(_collect_date_fields(item, location))

    return found


def _contains_forbidden_bp_term(
    value: str,
    forbidden_terms: set[str],
) -> bool:
    """Return True if a normalized lab label contains a BP-forbidden term."""
    if not value:
        return False

    return any(term == value or term in value for term in forbidden_terms)


def _find_key_locations(
    obj: Any,
    forbidden_key: str,
    prefix: str = "",
) -> list[str]:
    """Recursively find locations of a forbidden key."""
    locations: list[str] = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            location = f"{prefix}.{key}" if prefix else key

            if key == forbidden_key:
                locations.append(location)

            locations.extend(_find_key_locations(value, forbidden_key, location))

    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            location = f"{prefix}[{index}]" if prefix else f"[{index}]"
            locations.extend(_find_key_locations(item, forbidden_key, location))

    return locations
