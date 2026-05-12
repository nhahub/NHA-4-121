"""
validators/rules.py

Authoritative validation rules V1-V11.

Each rule returns ValidationIssue objects instead of raising exceptions.
This keeps validation report generation simple and student-friendly.
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
    FLAGS,
    FREQUENCIES,
    LAB_TYPES,
    MEDICATION_WHITELIST,
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
    TIERS,
    VITAL_LIMITS,
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
        validate_v5_prior_visit_integrity,
        validate_v6_duplicate_visit_ids,
        validate_v7_enums_and_ckd,
        validate_v8_date_formats,
        validate_v9_bp_forbidden_in_labs,
        validate_v10_timeline_events_forbidden,
        validate_v11_medication_whitelist_frequency_route,
    ):
        issues.extend(rule(patient))

    return issues


def patient_id_of(patient: dict[str, Any]) -> str:
    return str(patient.get("patient_id", "<missing-patient-id>"))


def validate_v1_chronological_visits(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V1: Chronological visit order."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)
    previous_date = None

    for visit in patient.get("visits", []):
        visit_date_raw = visit.get("visit_date")
        visit_id = visit.get("visit_id", "<missing-visit-id>")

        try:
            visit_date = datetime.strptime(str(visit_date_raw), DATE_FORMAT).date()
        except ValueError:
            continue

        if previous_date and visit_date < previous_date:
            issues.append(
                ValidationIssue(
                    rule_id="V1",
                    severity="FAIL",
                    patient_id=pid,
                    location=f"visits.{visit_id}.visit_date",
                    message=f"Visit date {visit_date_raw} is earlier than previous visit.",
                )
            )

        previous_date = visit_date

    return issues


def validate_v2_allergy_medication_conflicts(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V2: Medication must not conflict with allergy_registry."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    allergens = {
        str(allergy.get("allergen", "")).strip().lower()
        for allergy in patient.get("allergy_registry", [])
    }

    for visit in patient.get("visits", []):
        visit_id = visit.get("visit_id", "<missing-visit-id>")

        for medication in visit.get("medications", []):
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
                            f"conflicts with allergy_registry."
                        ),
                    )
                )

    return issues


def validate_v3_impossible_vitals(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V3: Impossible vitals prevention and age bounds."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    for visit in patient.get("visits", []):
        visit_id = visit.get("visit_id", "<missing-visit-id>")
        vitals = visit.get("vitals", {})

        for vital_name, (minimum, maximum) in VITAL_LIMITS.items():
            value = vitals.get(vital_name)

            if value is None:
                continue

            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                issues.append(
                    ValidationIssue(
                        rule_id="V3",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"visits.{visit_id}.vitals.{vital_name}",
                        message=f"Vital '{vital_name}' must be numeric.",
                    )
                )
                continue

            if not minimum <= numeric_value <= maximum:
                issues.append(
                    ValidationIssue(
                        rule_id="V3",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"visits.{visit_id}.vitals.{vital_name}",
                        message=(
                            f"Vital '{vital_name}'={numeric_value} outside "
                            f"allowed range {minimum}-{maximum}."
                        ),
                    )
                )

        age = _age_at_visit(
            patient.get("demographics", {}).get("date_of_birth"),
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
                        message=f"Age at visit is {age}, outside allowed range {min_age}-{max_age}.",
                    )
                )

    return issues


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

    for index, visit in enumerate(patient.get("visits", [])):
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

        for lab_index, lab in enumerate(visit.get("labs", [])):
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

        for med_index, med in enumerate(visit.get("medications", [])):
            for field in REQUIRED_MEDICATION_FIELDS:
                if field not in med:
                    issues.append(
                        ValidationIssue(
                            rule_id="V4",
                            severity="FAIL",
                            patient_id=pid,
                            location=f"visits.{visit_id}.medications[{med_index}].{field}",
                            message=f"Missing medication field '{field}'.",
                        )
                    )

    for allergy_index, allergy in enumerate(patient.get("allergy_registry", [])):
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


def validate_v5_prior_visit_integrity(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V5: prior_visit_id integrity."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    visit_ids = {
        visit.get("visit_id")
        for visit in patient.get("visits", [])
        if visit.get("visit_id")
    }

    for visit in patient.get("visits", []):
        visit_id = visit.get("visit_id", "<missing-visit-id>")
        prior_visit_id = visit.get("prior_visit_id")

        if prior_visit_id is not None and prior_visit_id not in visit_ids:
            issues.append(
                ValidationIssue(
                    rule_id="V5",
                    severity="WARN",
                    patient_id=pid,
                    location=f"visits.{visit_id}.prior_visit_id",
                    message=f"prior_visit_id '{prior_visit_id}' does not reference an existing visit.",
                )
            )

    return issues


def validate_v6_duplicate_visit_ids(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V6: Duplicate visit_id prevention."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    seen: set[str] = set()
    duplicates: set[str] = set()

    for visit in patient.get("visits", []):
        visit_id = visit.get("visit_id")

        if not visit_id:
            continue

        if visit_id in seen:
            duplicates.add(visit_id)

        seen.add(visit_id)

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


def validate_v7_enums_and_ckd(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V7: Enum validation and CKD co-occurrence constraints."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    tier = patient.get("metadata", {}).get("tier")

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

    sex = patient.get("demographics", {}).get("sex")
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

    for condition in patient.get("conditions", []):
        if condition not in CONDITIONS:
            issues.append(
                ValidationIssue(
                    rule_id="V7",
                    severity="FAIL",
                    patient_id=pid,
                    location="conditions",
                    message=f"Invalid condition enum '{condition}'.",
                )
            )

    patient_conditions = set(patient.get("conditions", []))
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

    for allergy_index, allergy in enumerate(patient.get("allergy_registry", [])):
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

    for visit in patient.get("visits", []):
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

        for diagnosis in visit.get("diagnoses", []):
            if diagnosis not in CONDITIONS:
                issues.append(
                    ValidationIssue(
                        rule_id="V7",
                        severity="FAIL",
                        patient_id=pid,
                        location=f"visits.{visit_id}.diagnoses",
                        message=f"Invalid diagnosis enum '{diagnosis}'.",
                    )
                )

        for lab_index, lab in enumerate(visit.get("labs", [])):
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

        for med_index, med in enumerate(visit.get("medications", [])):
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


def validate_v8_date_formats(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V8: Date format validation."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    date_locations = _collect_date_fields(patient)

    for location, value in date_locations:
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


def validate_v9_bp_forbidden_in_labs(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V9: BP forbidden inside labs."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)
    forbidden_terms = {term.lower() for term in BP_FORBIDDEN_LAB_TERMS}

    for visit in patient.get("visits", []):
        visit_id = visit.get("visit_id", "<missing-visit-id>")

        for lab_index, lab in enumerate(visit.get("labs", [])):
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
                if str(key).strip().lower() in forbidden_terms:
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


def validate_v10_timeline_events_forbidden(patient: dict[str, Any]) -> list[ValidationIssue]:
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


def validate_v11_medication_whitelist_frequency_route(patient: dict[str, Any]) -> list[ValidationIssue]:
    """V11: Medication whitelist + frequency + route validation."""
    issues: list[ValidationIssue] = []
    pid = patient_id_of(patient)

    for visit in patient.get("visits", []):
        visit_id = visit.get("visit_id", "<missing-visit-id>")

        for med_index, med in enumerate(visit.get("medications", [])):
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


def _age_at_visit(date_of_birth: Any, visit_date: Any) -> int | None:
    try:
        dob = datetime.strptime(str(date_of_birth), DATE_FORMAT).date()
        visit = datetime.strptime(str(visit_date), DATE_FORMAT).date()
    except ValueError:
        return None

    years = visit.year - dob.year
    before_birthday = (visit.month, visit.day) < (dob.month, dob.day)
    return years - int(before_birthday)


def _collect_date_fields(obj: Any, prefix: str = "") -> list[tuple[str, Any]]:
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


def _find_key_locations(obj: Any, forbidden_key: str, prefix: str = "") -> list[str]:
    locations: list[str] = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            location = f"{prefix}.{key}" if prefix else key

            if key == forbidden_key:
                locations.append(location)

            locations.extend(_find_key_locations(value, forbidden_key, location))

    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            locations.extend(_find_key_locations(item, forbidden_key, f"{prefix}[{index}]"))

    return locations