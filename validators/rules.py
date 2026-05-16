"""
validators/rules.py

Authoritative validation rules V1-V11.

Each rule returns ValidationIssue objects instead of raising exceptions.
This keeps validation report generation simple and student-friendly.

Validation rules follow the v1.5 implementation freeze:
- V1: Chronological visit order
- V2: Medication/allergy conflict prevention
- V3: Impossible vitals and age bounds
- V4: Required fields and forbidden demographics.age
- V5: prior_visit_id and allergy source_visit_id integrity
- V6: Duplicate visit_id prevention
- V7: Enum validation, ID pattern validation, and CKD constraints
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
    TIERS,
    VITAL_LIMITS,
    VISIT_ID_REGEX,
    VISIT_TYPES,
)

Severity = Literal["FAIL", "WARN"]


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
        except Exception as exc:
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
    """V1: Chronological visit order."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)
    previous_date = None

    for visit in _safe_list(patient.get("visits", [])):
        if not isinstance(visit, dict):
            continue
        visit_date_raw = visit.get("visit_date")
        visit_id = visit.get("visit_id", "<missing-visit-id>")

        try:
            visit_date = datetime.strptime(str(visit_date_raw), DATE_FORMAT).date()
        except (TypeError, ValueError):
            # V8 handles invalid date formats.
            continue

        if previous_date and visit_date < previous_date:
            issues.append(
                ValidationIssue(
                    rule_id="V1",
                    severity="FAIL",
                    patient_id=pid,
                    location=f"visits.{visit_id}.visit_date",
                    message=(
                        f"Visit date {visit_date_raw} is earlier than "
                        "the previous visit date."
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
    """V2: Medication must not conflict with allergy_registry."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    allergens = {
        str(allergy.get("allergen", "")).strip().lower()
        for allergy in _safe_list(patient.get("allergy_registry", []))
        if isinstance(allergy, dict)
        and str(allergy.get("allergen", "")).strip()
        }

    for visit in _safe_list(patient.get("visits", [])):
        if not isinstance(visit, dict):
            continue
        visit_id = visit.get("visit_id", "<missing-visit-id>")

        for medication in _safe_list(visit.get("medications", [])):
            if not isinstance(medication, dict):
                continue
            med_name = str(medication.get("medication_name", "")).strip().lower()

            if med_name and med_name in allergens:
                issues.append(
                    ValidationIssue(
                        rule_id="V2",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"visits.{visit_id}.medications",
                        message=(
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
    """V3: Impossible vitals prevention and age bounds."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    for visit in _safe_list(patient.get("visits", [])):
        if not isinstance(visit, dict):
            continue

        visit_id = visit.get("visit_id", "<missing-visit-id>")
        vitals = visit.get("vitals", {})

        if not isinstance(vitals, dict):
            issues.append(
                ValidationIssue(
                    rule_id="V3",
                    severity="FAIL",
                    patient_id=pid,
                    location=f"visits.{visit_id}.vitals",
                    message="vitals must be an object.",
                )
            )
            continue

        for vital_name, (minimum, maximum) in VITAL_LIMITS.items():
            value = vitals.get(vital_name)

            if value is None:
                continue

            issues.extend(
                _validate_numeric_range(
                    rule_id="V3",
                    patient_id=pid,
                    location=f"visits.{visit_id}.vitals.{vital_name}",
                    label=f"Vital '{vital_name}'",
                    value=value,
                    minimum=minimum,
                    maximum=maximum,
                    inclusive_minimum=True,
                    inclusive_maximum=True,
                )
            )

        # Explicit weight_kg validation because older constants may not include it.
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

        demographics = _safe_dict(patient.get("demographics", {}))
        age = _age_at_visit(
            demographics.get("date_of_birth"),
            visit.get("visit_date"),
        )

        if age is not None:
            min_age, max_age = AGE_LIMITS

            if not min_age <= age <= max_age:
                issues.append(
                    ValidationIssue(
                        rule_id="V3",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"visits.{visit_id}",
                        message=(
                            f"Age at visit is {age}, outside allowed range "
                            f"{min_age}-{max_age}."
                        ),
                    )
                )

    return issues

# ---------------------------------------------------------------------
# V4
# ---------------------------------------------------------------------


def validate_v4_required_fields(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V4: Required fields validation and forbidden demographics.age."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in patient:
            issues.append(
                ValidationIssue(
                    rule_id="V4",
                    severity="FAIL",
                    patient_id=pid,
                    location=field,
                    message=f"Missing top-level field '{field}'.",
                )
            )

    if patient.get("schema_version") != SCHEMA_VERSION:
        issues.append(
            ValidationIssue(
                rule_id="V4",
                severity="FAIL",
                patient_id=pid,
                location="schema_version",
                message=f"schema_version must be '{SCHEMA_VERSION}'.",
            )
        )

    demographics = patient.get("demographics", {})
    if not isinstance(demographics, dict):
        issues.append(
            ValidationIssue(
                rule_id="V4",
                severity="FAIL",
                patient_id=pid,
                location="demographics",
                message="demographics must be an object.",
            )
        )
        demographics = {}

    for field in REQUIRED_DEMOGRAPHICS_FIELDS:
        if field not in demographics:
            issues.append(
                ValidationIssue(
                    rule_id="V4",
                    severity="FAIL",
                    patient_id=pid,
                    location=f"demographics.{field}",
                    message=f"Missing demographics field '{field}'.",
                )
            )

    if "age" in demographics:
        issues.append(
            ValidationIssue(
                rule_id="V4",
                severity="FAIL",
                patient_id=pid,
                location="demographics.age",
                message="demographics.age is forbidden. Use date_of_birth only.",
            )
        )

    metadata = patient.get("metadata", {})
    if not isinstance(metadata, dict):
        issues.append(
            ValidationIssue(
                rule_id="V4",
                severity="FAIL",
                patient_id=pid,
                location="metadata",
                message="metadata must be an object.",
            )
        )
    elif "tier" not in metadata:
        issues.append(
            ValidationIssue(
                rule_id="V4",
                severity="FAIL",
                patient_id=pid,
                location="metadata.tier",
                message="Missing metadata field 'tier'.",
            )
        )

    visits = patient.get("visits", [])
    if not isinstance(visits, list):
        issues.append(
            ValidationIssue(
                rule_id="V4",
                severity="FAIL",
                patient_id=pid,
                location="visits",
                message="visits must be an array.",
            )
        )
        return issues

    for index, visit in enumerate(visits):
        if not isinstance(visit, dict):
            issues.append(
                ValidationIssue(
                    rule_id="V4",
                    severity="FAIL",
                    patient_id=pid,
                    location=f"visits[{index}]",
                    message="visit must be an object.",
                )
            )
            continue

        visit_id = visit.get("visit_id", f"<visit-index-{index}>")

        for field in REQUIRED_VISIT_FIELDS:
            if field not in visit:
                issues.append(
                    ValidationIssue(
                        rule_id="V4",
                        severity="WARN",
                        patient_id=pid,
                        location=f"visits.{visit_id}.{field}",
                        message=f"Missing visit field '{field}'.",
                    )
                )

        vitals = visit.get("vitals", {})
        if not isinstance(vitals, dict):
            issues.append(
                ValidationIssue(
                    rule_id="V4",
                    severity="FAIL",
                    patient_id=pid,
                    location=f"visits.{visit_id}.vitals",
                    message="vitals must be an object.",
                )
            )
            vitals = {}

        for field in REQUIRED_VITAL_FIELDS:
            if field not in vitals:
                issues.append(
                    ValidationIssue(
                        rule_id="V4",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"visits.{visit_id}.vitals.{field}",
                        message=f"Missing vital field '{field}'.",
                    )
                )

        labs = visit.get("labs", [])
        if not isinstance(labs, list):
            issues.append(
                ValidationIssue(
                    rule_id="V4",
                    severity="FAIL",
                    patient_id=pid,
                    location=f"visits.{visit_id}.labs",
                    message="labs must be an array.",
                )
            )
            labs = []

        for lab_index, lab in enumerate(labs):
            if not isinstance(lab, dict):
                issues.append(
                    ValidationIssue(
                        rule_id="V4",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"visits.{visit_id}.labs[{lab_index}]",
                        message="lab must be an object.",
                    )
                )
                continue

            for field in REQUIRED_LAB_FIELDS:
                if field not in lab:
                    issues.append(
                        ValidationIssue(
                            rule_id="V4",
                            severity="FAIL",
                            patient_id=pid,
                            location=f"visits.{visit_id}.labs[{lab_index}].{field}",
                            message=f"Missing lab field '{field}'.",
                        )
                    )

        medications = visit.get("medications", [])
        if not isinstance(medications, list):
            issues.append(
                ValidationIssue(
                    rule_id="V4",
                    severity="FAIL",
                    patient_id=pid,
                    location=f"visits.{visit_id}.medications",
                    message="medications must be an array.",
                )
            )
            medications = []

        for med_index, med in enumerate(medications):
            if not isinstance(med, dict):
                issues.append(
                    ValidationIssue(
                        rule_id="V4",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"visits.{visit_id}.medications[{med_index}]",
                        message="medication must be an object.",
                    )
                )
                continue

            for field in REQUIRED_MEDICATION_FIELDS:
                if field not in med:
                    issues.append(
                        ValidationIssue(
                            rule_id="V4",
                            severity="FAIL",
                            patient_id=pid,
                            location=(
                                f"visits.{visit_id}.medications[{med_index}].{field}"
                            ),
                            message=f"Missing medication field '{field}'.",
                        )
                    )

        soap_note = visit.get("soap_note", {})
        if not isinstance(soap_note, dict):
            issues.append(
                ValidationIssue(
                    rule_id="V4",
                    severity="FAIL",
                    patient_id=pid,
                    location=f"visits.{visit_id}.soap_note",
                    message="soap_note must be an object.",
                )
            )
            soap_note = {}

        for section in SOAP_SECTIONS:
            if section not in soap_note:
                issues.append(
                    ValidationIssue(
                        rule_id="V4",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"visits.{visit_id}.soap_note.{section}",
                        message=f"Missing SOAP section '{section}'.",
                    )
                )

    allergy_registry = patient.get("allergy_registry", [])
    if not isinstance(allergy_registry, list):
        issues.append(
            ValidationIssue(
                rule_id="V4",
                severity="FAIL",
                patient_id=pid,
                location="allergy_registry",
                message="allergy_registry must be an array.",
            )
        )
        return issues

    for allergy_index, allergy in enumerate(allergy_registry):
        if not isinstance(allergy, dict):
            issues.append(
                ValidationIssue(
                    rule_id="V4",
                    severity="FAIL",
                    patient_id=pid,
                    location=f"allergy_registry[{allergy_index}]",
                    message="allergy record must be an object.",
                )
            )
            continue

        for field in REQUIRED_ALLERGY_FIELDS:
            if field not in allergy:
                issues.append(
                    ValidationIssue(
                        rule_id="V4",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"allergy_registry[{allergy_index}].{field}",
                        message=f"Missing allergy field '{field}'.",
                    )
                )

    return issues


# ---------------------------------------------------------------------
# V5
# ---------------------------------------------------------------------


def validate_v5_reference_integrity(patient: dict[str, Any]) -> list[ValidationIssue]:
    """
    V5: prior_visit_id and allergy source_visit_id reference integrity.

    V5 remains WARN-level because it catches broken references that should be
    reviewed and fixed before demo day.
    """
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    visit_ids = {
    visit.get("visit_id")
    for visit in _safe_list(patient.get("visits", []))
    if isinstance(visit, dict) and visit.get("visit_id")
}

    for visit in _safe_list(patient.get("visits", [])):
        if not isinstance(visit, dict):
            continue

        visit_id = visit.get("visit_id", "<missing-visit-id>")
        prior_visit_id = visit.get("prior_visit_id")

        if prior_visit_id is not None and prior_visit_id not in visit_ids:
            issues.append(
                ValidationIssue(
                    rule_id="V5",
                    severity="WARN",
                    patient_id=pid,
                    location=f"visits.{visit_id}.prior_visit_id",
                    message=(
                        f"prior_visit_id '{prior_visit_id}' does not reference "
                        "an existing visit."
                    ),
                )
            )

    for allergy_index, allergy in enumerate(_safe_list(patient.get("allergy_registry", []))):
        if not isinstance(allergy, dict):
            continue

        source_visit_id = allergy.get("source_visit_id")

        if source_visit_id is not None and source_visit_id not in visit_ids:
            issues.append(
                ValidationIssue(
                    rule_id="V5",
                    severity="WARN",
                    patient_id=pid,
                    location=f"allergy_registry[{allergy_index}].source_visit_id",
                    message=(
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
    """V6: Duplicate visit_id prevention."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    seen: set[str] = set()
    duplicates: set[str] = set()

    for visit in _safe_list(patient.get("visits", [])):
        if not isinstance(visit, dict):
            continue

        visit_id = visit.get("visit_id")

        if not visit_id:
            continue

        if visit_id in seen:
            duplicates.add(str(visit_id))

        seen.add(str(visit_id))

    for duplicate in sorted(duplicates):
        issues.append(
            ValidationIssue(
                rule_id="V6",
                severity="FAIL",
                patient_id=pid,
                location="visits.visit_id",
                message=f"Duplicate visit_id found: {duplicate}.",
            )
        )

    return issues


# ---------------------------------------------------------------------
# V7
# ---------------------------------------------------------------------


def validate_v7_enums_patterns_and_ckd(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V7: Enum validation, ID pattern validation, and CKD co-occurrence constraints."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    issues.extend(_validate_id_patterns(patient))

    metadata = _safe_dict(patient.get("metadata", {}))
    tier = metadata.get("tier")
    if tier not in TIERS:
        issues.append(
            ValidationIssue(
                rule_id="V7",
                severity="FAIL",
                patient_id=pid,
                location="metadata.tier",
                message=f"Invalid tier '{tier}'.",
            )
        )

    demographics = _safe_dict(patient.get("demographics", {}))
    sex = demographics.get("sex")
    if sex not in SEX_VALUES:
        issues.append(
            ValidationIssue(
                rule_id="V7",
                severity="FAIL",
                patient_id=pid,
                location="demographics.sex",
                message=f"Invalid sex '{sex}'.",
            )
        )

    for condition_index, condition in enumerate(_safe_list(patient.get("conditions", []))):
        if condition not in CONDITIONS:
            issues.append(
                ValidationIssue(
                    rule_id="V7",
                    severity="FAIL",
                    patient_id=pid,
                    location=f"conditions[{condition_index}]",
                    message=f"Invalid condition enum '{condition}'.",
                )
            )

    patient_conditions = set(_safe_list(patient.get("conditions", [])))
    if "CKD" in patient_conditions:
        if tier != "chronic":
            issues.append(
                ValidationIssue(
                    rule_id="V7",
                    severity="FAIL",
                    patient_id=pid,
                    location="conditions",
                    message="CKD requires metadata.tier='chronic'.",
                )
            )

        for required in ("T2DM", "HTN"):
            if required not in patient_conditions:
                issues.append(
                    ValidationIssue(
                        rule_id="V7",
                        severity="FAIL",
                        patient_id=pid,
                        location="conditions",
                        message=f"CKD requires co-occurring condition '{required}'.",
                    )
                )

    for allergy_index, allergy in enumerate(_safe_list(patient.get("allergy_registry", []))):
        if not isinstance(allergy, dict):
            continue

        severity = allergy.get("severity")
        if severity not in SEVERITIES:
            issues.append(
                ValidationIssue(
                    rule_id="V7",
                    severity="FAIL",
                    patient_id=pid,
                    location=f"allergy_registry[{allergy_index}].severity",
                    message=f"Invalid allergy severity '{severity}'.",
                )
            )

    for visit in _safe_list(patient.get("visits", [])):
        if not isinstance(visit, dict):
            continue

        visit_id = visit.get("visit_id", "<missing-visit-id>")

        if visit.get("visit_type") not in VISIT_TYPES:
            issues.append(
                ValidationIssue(
                    rule_id="V7",
                    severity="FAIL",
                    patient_id=pid,
                    location=f"visits.{visit_id}.visit_type",
                    message=f"Invalid visit_type '{visit.get('visit_type')}'.",
                )
            )

        for diagnosis_index, diagnosis in enumerate(_safe_list(visit.get("diagnoses", []))):
            if diagnosis not in CONDITIONS:
                issues.append(
                    ValidationIssue(
                        rule_id="V7",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"visits.{visit_id}.diagnoses[{diagnosis_index}]",
                        message=f"Invalid diagnosis enum '{diagnosis}'.",
                    )
                )

        for lab_index, lab in enumerate(_safe_list(visit.get("labs", []))):
            if not isinstance(lab, dict):
                continue

            lab_type = lab.get("lab_type")
            flag = lab.get("flag")

            if lab_type not in LAB_TYPES:
                issues.append(
                    ValidationIssue(
                        rule_id="V7",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"visits.{visit_id}.labs[{lab_index}].lab_type",
                        message=f"Invalid lab_type '{lab_type}'.",
                    )
                )

            if flag not in FLAGS:
                issues.append(
                    ValidationIssue(
                        rule_id="V7",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"visits.{visit_id}.labs[{lab_index}].flag",
                        message=f"Invalid lab flag '{flag}'.",
                    )
                )

        for med_index, med in enumerate(_safe_list(visit.get("medications", []))):
            if not isinstance(med, dict):
                continue

            frequency = med.get("frequency")
            route = med.get("route")

            if frequency not in FREQUENCIES:
                issues.append(
                    ValidationIssue(
                        rule_id="V7",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"visits.{visit_id}.medications[{med_index}].frequency",
                        message=f"Invalid frequency '{frequency}'.",
                    )
                )

            if route not in ROUTES:
                issues.append(
                    ValidationIssue(
                        rule_id="V7",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"visits.{visit_id}.medications[{med_index}].route",
                        message=f"Invalid route '{route}'.",
                    )
                )

    return issues


# ---------------------------------------------------------------------
# V8
# ---------------------------------------------------------------------


def validate_v8_date_formats(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V8: Date format validation."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    for location, value in _collect_date_fields(patient):
        if value is None:
            continue

        if not isinstance(value, str) or not re.match(DATE_REGEX, value):
            issues.append(
                ValidationIssue(
                    rule_id="V8",
                    severity="FAIL",
                    patient_id=pid,
                    location=location,
                    message=f"Invalid date format '{value}'. Expected YYYY-MM-DD.",
                )
            )
            continue

        try:
            datetime.strptime(value, DATE_FORMAT)
        except ValueError:
            issues.append(
                ValidationIssue(
                    rule_id="V8",
                    severity="FAIL",
                    patient_id=pid,
                    location=location,
                    message=f"Invalid calendar date '{value}'.",
                )
            )

    return issues


# ---------------------------------------------------------------------
# V9
# ---------------------------------------------------------------------


def validate_v9_bp_forbidden_in_labs(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V9: BP forbidden inside labs."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)
    forbidden_terms = {term.lower() for term in BP_FORBIDDEN_LAB_TERMS}

    for visit in _safe_list(patient.get("visits", [])):
        if not isinstance(visit, dict):
            continue

        visit_id = visit.get("visit_id", "<missing-visit-id>")

        for lab_index, lab in enumerate(_safe_list(visit.get("labs", []))):
            if not isinstance(lab, dict):
                continue

            lab_type = str(lab.get("lab_type", "")).strip().lower()

            if lab_type in forbidden_terms:
                issues.append(
                    ValidationIssue(
                        rule_id="V9",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"visits.{visit_id}.labs[{lab_index}].lab_type",
                        message=f"BP value found in labs array at {visit_id}.",
                    )
                )

            for key in lab.keys():
                key_normalized = str(key).strip().lower()
                if key_normalized in forbidden_terms:
                    issues.append(
                        ValidationIssue(
                            rule_id="V9",
                            severity="FAIL",
                            patient_id=pid,
                            location=f"visits.{visit_id}.labs[{lab_index}].{key}",
                            message=f"BP-like field '{key}' found inside lab object.",
                        )
                    )

    return issues


# ---------------------------------------------------------------------
# V10
# ---------------------------------------------------------------------


def validate_v10_timeline_events_forbidden(
    patient: dict[str, Any],
) -> list[ValidationIssue]:
    """V10: timeline_events forbidden anywhere in patient JSON."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    for location in _find_key_locations(patient, forbidden_key="timeline_events"):
        issues.append(
            ValidationIssue(
                rule_id="V10",
                severity="FAIL",
                patient_id=pid,
                location=location,
                message="timeline_events field is forbidden. Generate timeline from visits.",
            )
        )

    return issues


# ---------------------------------------------------------------------
# V11
# ---------------------------------------------------------------------


def validate_v11_medication_whitelist_frequency_route(
    patient: dict[str, Any],
) -> list[ValidationIssue]:
    """V11: Medication whitelist + frequency + route validation."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    for visit in _safe_list(patient.get("visits", [])):
        if not isinstance(visit, dict):
            continue

        visit_id = visit.get("visit_id", "<missing-visit-id>")

        for med_index, med in enumerate(_safe_list(visit.get("medications", []))):
            if not isinstance(med, dict):
                continue

            med_name = med.get("medication_name")
            location = f"visits.{visit_id}.medications[{med_index}]"

            if med_name not in MEDICATION_WHITELIST:
                issues.append(
                    ValidationIssue(
                        rule_id="V11",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"{location}.medication_name",
                        message=f"Medication '{med_name}' is not in whitelist.",
                    )
                )
                continue

            expected = MEDICATION_WHITELIST[med_name]

            if med.get("frequency") not in FREQUENCIES:
                issues.append(
                    ValidationIssue(
                        rule_id="V11",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"{location}.frequency",
                        message=f"Invalid frequency '{med.get('frequency')}'.",
                    )
                )

            if med.get("route") not in ROUTES:
                issues.append(
                    ValidationIssue(
                        rule_id="V11",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"{location}.route",
                        message=f"Invalid route '{med.get('route')}'.",
                    )
                )

            if med.get("frequency") != expected["frequency"]:
                issues.append(
                    ValidationIssue(
                        rule_id="V11",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"{location}.frequency",
                        message=(
                            f"Medication '{med_name}' frequency must be "
                            f"'{expected['frequency']}', got '{med.get('frequency')}'."
                        ),
                    )
                )

            if med.get("route") != expected["route"]:
                issues.append(
                    ValidationIssue(
                        rule_id="V11",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"{location}.route",
                        message=(
                            f"Medication '{med_name}' route must be "
                            f"'{expected['route']}', got '{med.get('route')}'."
                        ),
                    )
                )

    return issues


# ---------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------

def _safe_list(value: Any) -> list[Any]:
    """Return value if it is a list, otherwise return an empty list."""
    return value if isinstance(value, list) else []

def _safe_dict(value: Any) -> dict[str, Any]:
    """Return value if it is a dict, otherwise return an empty dict."""
    return value if isinstance(value, dict) else {}

def _validate_id_patterns(patient: dict[str, Any]) -> list[ValidationIssue]:
    """
    Validate patient_id, visit_id, linked document IDs, prior_visit_id format,
    and allergy source_visit_id format.

    These are V7 pattern constraints because IDs are locked schema contracts
    used by retrieval, timeline generation, OCR linkage, and citations.
    """
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    patient_id = patient.get("patient_id")
    if not isinstance(patient_id, str) or not re.match(PATIENT_ID_REGEX, patient_id):
        issues.append(
            ValidationIssue(
                rule_id="V7",
                severity="FAIL",
                patient_id=pid,
                location="patient_id",
                message=f"Invalid patient_id format '{patient_id}'.",
            )
        )

    for visit_index, visit in enumerate(_safe_list(patient.get("visits", []))):
        if not isinstance(visit, dict):
            continue

        visit_id = visit.get("visit_id")
        location_prefix = f"visits[{visit_index}]"

        if not isinstance(visit_id, str) or not re.match(VISIT_ID_REGEX, visit_id):
            issues.append(
                ValidationIssue(
                    rule_id="V7",
                    severity="FAIL",
                    patient_id=pid,
                    location=f"{location_prefix}.visit_id",
                    message=f"Invalid visit_id format '{visit_id}'.",
                )
            )

        prior_visit_id = visit.get("prior_visit_id")
        if prior_visit_id is not None and (
            not isinstance(prior_visit_id, str)
            or not re.match(VISIT_ID_REGEX, prior_visit_id)
        ):
            issues.append(
                ValidationIssue(
                    rule_id="V7",
                    severity="FAIL",
                    patient_id=pid,
                    location=f"{location_prefix}.prior_visit_id",
                    message=f"Invalid prior_visit_id format '{prior_visit_id}'.",
                )
            )

        linked_documents = visit.get("linked_documents", [])
        if isinstance(linked_documents, list):
            for doc_index, document_id in enumerate(linked_documents):
                if not isinstance(document_id, str) or not re.match(
                    DOCUMENT_ID_REGEX,
                    document_id,
                ):
                    issues.append(
                        ValidationIssue(
                            rule_id="V7",
                            severity="FAIL",
                            patient_id=pid,
                            location=f"{location_prefix}.linked_documents[{doc_index}]",
                            message=f"Invalid document_id format '{document_id}'.",
                        )
                    )

    for allergy_index, allergy in enumerate(_safe_list(patient.get("allergy_registry", []))):
        if not isinstance(allergy, dict):
            continue

        source_visit_id = allergy.get("source_visit_id")
        if not isinstance(source_visit_id, str) or not re.match(
            VISIT_ID_REGEX,
            source_visit_id,
        ):
            issues.append(
                ValidationIssue(
                    rule_id="V7",
                    severity="FAIL",
                    patient_id=pid,
                    location=f"allergy_registry[{allergy_index}].source_visit_id",
                    message=f"Invalid source_visit_id format '{source_visit_id}'.",
                )
            )

    return issues


def _validate_numeric_range(
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
    """Validate a numeric field against a range and return issues."""
    issues: list[ValidationIssue] = []

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return [
            ValidationIssue(
                rule_id=rule_id,
                severity="FAIL",
                patient_id=patient_id,
                location=location,
                message=f"{label} must be numeric.",
            )
        ]

    min_ok = numeric_value >= minimum if inclusive_minimum else numeric_value > minimum
    max_ok = numeric_value <= maximum if inclusive_maximum else numeric_value < maximum

    if not (min_ok and max_ok):
        min_operator = ">=" if inclusive_minimum else ">"
        max_operator = "<=" if inclusive_maximum else "<"
        issues.append(
            ValidationIssue(
                rule_id=rule_id,
                severity="FAIL",
                patient_id=patient_id,
                location=location,
                message=(
                    f"{label}={numeric_value} outside allowed range "
                    f"{min_operator}{minimum} and {max_operator}{maximum}."
                ),
            )
        )

    return issues


def _age_at_visit(date_of_birth: Any, visit_date: Any) -> int | None:
    """Calculate age at a visit. Return None if dates are invalid."""
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

    event_date is retained because V8 historically checks it, even though the
    final patient schema does not currently use event_date.
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
            found.extend(_collect_date_fields(item, f"{prefix}[{index}]"))

    return found


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
            locations.extend(
                _find_key_locations(item, forbidden_key, f"{prefix}[{index}]")
            )

    return locations