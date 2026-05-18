"""
scripts/generate_all.py

Generate deterministic synthetic patient JSON files.

Run from project root:

    python scripts/generate_all.py --clean
    python scripts/generate_all.py --mode pilot --clean
    python scripts/generate_all.py --mode full --clean

Pipeline:
1. patient shells
2. visits
3. medications
4. labs
5. allergies
6. structured validation hard gate
7. SOAP notes for structurally valid patients only
8. SOAP audit
9. final validation
10. export valid files to data/patients/
11. export invalid files to data/quarantine/

Safety rule:
    SOAP generation must never run for a patient that already has FAIL-level
    structured validation issues. Validation is the hard gate before SOAP.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.constants import (  # noqa: E402
    DATASET_MODE_FULL,
    DATASET_MODE_PILOT,
    DEFAULT_DATASET_MODE,
    EXPECTED_FULL_PATIENT_COUNT,
    EXPECTED_PILOT_PATIENT_COUNT,
    FINAL_PATIENT_DISTRIBUTION,
    JSON_ENCODING,
    JSON_INDENT,
    PILOT_PATIENT_DISTRIBUTION,
)
from config.paths import (  # noqa: E402
    PATIENTS_DIR,
    QUARANTINE_DIR,
    ensure_project_directories,
    patient_file_path,
    quarantine_file_path,
)
from generators.allergy_generator import add_allergies_to_patient  # noqa: E402
from generators.lab_generator import add_labs_to_patient  # noqa: E402
from generators.medication_generator import add_medications_to_patient  # noqa: E402
from generators.patient_generator import (  # noqa: E402
    blueprint_by_patient_id,
    generate_patient_shells,
)
from generators.visit_generator import add_visits_to_patient  # noqa: E402
from soap.soap_auditor import (  # noqa: E402
    SoapAuditIssue,
    SoapAuditSeverity,
    audit_patient_soap,
    flatten_issues,
)
from soap.soap_generator import add_soap_notes_to_patient  # noqa: E402
from validators.rules import ValidationIssue, validate_patient  # noqa: E402


def generate_all_patients(
    mode: str = DEFAULT_DATASET_MODE,
) -> list[dict[str, Any]]:
    """
    Generate the selected dataset in dependency order.

    The function first generates structured patient records, validates them,
    and only then generates SOAP notes for records with zero FAIL-level
    validation issues.

    Args:
        mode:
            - "pilot": generate 5 pilot patients
            - "full": generate 30 full-dataset patients

    Returns:
        Generated patient dictionaries. Patients with structured validation
        failures are returned without regenerated SOAP notes so they can be
        exported to quarantine with clean validation reports.
    """
    structured_patients = generate_structured_patients(mode=mode)
    generated: list[dict[str, Any]] = []

    for patient in structured_patients:
        structured_issues = validate_patient(patient)

        if _has_fail_validation_issues(structured_issues):
            generated.append(patient)
            continue

        generated.append(add_soap_notes_to_patient(patient))

    return generated


def generate_structured_patients(
    mode: str = DEFAULT_DATASET_MODE,
) -> list[dict[str, Any]]:
    """
    Generate structured patient records before SOAP generation.

    This stage is deterministic and does not call the SOAP layer. It is the
    validation input for the hard gate before SOAP notes are created.
    """
    expected_count = _expected_patient_count_for_mode(mode)

    blueprints = blueprint_by_patient_id(mode=mode)
    patients = generate_patient_shells(mode=mode)

    generated: list[dict[str, Any]] = []

    for patient in patients:
        patient_id = patient["patient_id"]
        blueprint = blueprints[patient_id]

        patient = add_visits_to_patient(patient, blueprint)
        patient = add_medications_to_patient(patient)
        patient = add_labs_to_patient(patient)
        patient = add_allergies_to_patient(patient)

        generated.append(patient)

    if len(generated) != expected_count:
        raise RuntimeError(
            f"Expected {expected_count} patients for mode='{mode}', "
            f"generated {len(generated)}."
        )

    _assert_generated_distribution(generated, mode=mode)
    _assert_unique_generated_patient_ids(generated)

    return generated


def export_patients(
    patients: list[dict[str, Any]],
) -> tuple[int, int]:
    """
    Validate, audit, and export patients.

    Valid patients go to data/patients.
    Invalid patients go to data/quarantine with issue reports.

    Important:
        SOAP audit is skipped when final validation already has FAIL issues.
        This avoids noisy SOAP failures for structurally invalid records and
        preserves validation as the hard gate.
    """
    valid_count = 0
    invalid_count = 0

    for patient in patients:
        patient_id = str(patient.get("patient_id", "UNKNOWN_PATIENT"))
        validation_issues = validate_patient(patient)
        fail_validation = _fail_validation_issues(validation_issues)

        soap_issues: list[SoapAuditIssue] = []
        fail_soap: list[SoapAuditIssue] = []

        if not fail_validation:
            soap_results = audit_patient_soap(patient)
            soap_issues = flatten_issues(soap_results)
            fail_soap = _fail_soap_issues(soap_issues)

        is_valid = not fail_validation and not fail_soap

        if is_valid:
            _write_patient_json(patient_file_path(patient_id), patient)
            valid_count += 1
            continue

        _write_patient_json(quarantine_file_path(patient_id), patient)
        _write_issue_report(
            patient_id=patient_id,
            soap_issues=soap_issues,
            validation_issues=validation_issues,
        )
        invalid_count += 1

    return valid_count, invalid_count


def _has_existing_generated_outputs() -> bool:
    """
    Return True if generated patient or issue files already exist.

    This prevents accidental mixed datasets when switching between pilot/full
    modes without --clean.
    """
    patterns = (
        "PAT-*.json",
        "*.validation_issues.json",
        "*.soap_issues.json",
    )

    for directory in (PATIENTS_DIR, QUARANTINE_DIR):
        if not directory.exists():
            continue

        for pattern in patterns:
            if any(directory.glob(pattern)):
                return True

    return False


def clean_output_directories() -> None:
    """Remove previously generated patient/quarantine files."""
    for directory in (PATIENTS_DIR, QUARANTINE_DIR):
        directory.mkdir(parents=True, exist_ok=True)

        for path in directory.glob("PAT-*.json"):
            path.unlink()

        for path in directory.glob("*.validation_issues.json"):
            path.unlink()

        for path in directory.glob("*.soap_issues.json"):
            path.unlink()


def _write_patient_json(path: Path, patient: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(patient, indent=JSON_INDENT, ensure_ascii=False),
        encoding=JSON_ENCODING,
    )


def _write_issue_report(
    patient_id: str,
    soap_issues: Iterable[SoapAuditIssue],
    validation_issues: Iterable[ValidationIssue],
) -> None:
    """Write combined validation/SOAP issue report for quarantined patients."""
    payload = {
        "patient_id": patient_id,
        "soap_issues": [_serialize_soap_issue(issue) for issue in soap_issues],
        "validation_issues": [
            _serialize_validation_issue(issue)
            for issue in validation_issues
        ],
    }

    report_path = QUARANTINE_DIR / f"{patient_id}.validation_issues.json"
    report_path.write_text(
        json.dumps(payload, indent=JSON_INDENT, ensure_ascii=False),
        encoding=JSON_ENCODING,
    )


def _serialize_soap_issue(issue: SoapAuditIssue) -> dict[str, Any]:
    return {
        "rule_id": issue.rule_id,
        "severity": issue.severity.value,
        "patient_id": issue.patient_id,
        "visit_id": issue.visit_id,
        "section": issue.section,
        "message": issue.message,
    }


def _serialize_validation_issue(issue: ValidationIssue) -> dict[str, Any]:
    return {
        "rule_id": issue.rule_id,
        "severity": issue.severity,
        "patient_id": issue.patient_id,
        "message": issue.message,
        "location": issue.location,
    }


def _fail_validation_issues(
    issues: Iterable[ValidationIssue],
) -> list[ValidationIssue]:
    return [issue for issue in issues if issue.severity == "FAIL"]


def _has_fail_validation_issues(issues: Iterable[ValidationIssue]) -> bool:
    return bool(_fail_validation_issues(issues))


def _fail_soap_issues(
    issues: Iterable[SoapAuditIssue],
) -> list[SoapAuditIssue]:
    return [
        issue
        for issue in issues
        if issue.severity == SoapAuditSeverity.FAIL
    ]


def _expected_patient_count_for_mode(mode: str) -> int:
    if mode == DATASET_MODE_PILOT:
        return EXPECTED_PILOT_PATIENT_COUNT

    if mode == DATASET_MODE_FULL:
        return EXPECTED_FULL_PATIENT_COUNT

    raise ValueError(
        f"Unsupported dataset mode '{mode}'. "
        f"Expected '{DATASET_MODE_PILOT}' or '{DATASET_MODE_FULL}'."
    )


def _expected_distribution_for_mode(mode: str) -> dict[str, int]:
    if mode == DATASET_MODE_PILOT:
        return PILOT_PATIENT_DISTRIBUTION

    if mode == DATASET_MODE_FULL:
        return FINAL_PATIENT_DISTRIBUTION

    raise ValueError(
        f"Unsupported dataset mode '{mode}'. "
        f"Expected '{DATASET_MODE_PILOT}' or '{DATASET_MODE_FULL}'."
    )


def _assert_generated_distribution(
    patients: list[dict[str, Any]],
    mode: str,
) -> None:
    expected_distribution = _expected_distribution_for_mode(mode)
    actual_distribution = {tier: 0 for tier in expected_distribution}

    for patient in patients:
        tier = patient.get("metadata", {}).get("tier")
        actual_distribution[tier] = actual_distribution.get(tier, 0) + 1

    if actual_distribution != expected_distribution:
        raise RuntimeError(
            f"Invalid generated tier distribution for mode='{mode}'. "
            f"Expected {expected_distribution}, got {actual_distribution}."
        )


def _assert_unique_generated_patient_ids(patients: list[dict[str, Any]]) -> None:
    patient_ids = [patient["patient_id"] for patient in patients]

    if len(patient_ids) != len(set(patient_ids)):
        raise RuntimeError("Duplicate patient_id detected after generation.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic patient records."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete previous generated patient/quarantine JSON files first.",
    )
    parser.add_argument(
        "--mode",
        choices=(DATASET_MODE_PILOT, DATASET_MODE_FULL),
        default=DEFAULT_DATASET_MODE,
        help="Dataset size to generate. Defaults to the configured default mode.",
    )
    args = parser.parse_args()

    ensure_project_directories()

    if args.clean:
        clean_output_directories()
    elif _has_existing_generated_outputs():
        print(
            "ERROR: Existing generated patient/quarantine files were found. "
            "Re-run with --clean to avoid mixing stale records with a new dataset.",
            file=sys.stderr,
        )
        return 1

    expected_count = _expected_patient_count_for_mode(args.mode)
    patients = generate_all_patients(mode=args.mode)
    valid_count, invalid_count = export_patients(patients)

    print("\n=== DATA GENERATION COMPLETE ===")
    print(f"Mode:               {args.mode}")
    print(f"Expected patients:  {expected_count}")
    print(f"Generated patients: {len(patients)}")
    print(f"Valid exported:     {valid_count}")
    print(f"Quarantined:        {invalid_count}")
    print(f"Approved directory: {PATIENTS_DIR}")
    print(f"Quarantine dir:     {QUARANTINE_DIR}")

    if len(patients) != expected_count:
        return 1

    if valid_count != expected_count:
        return 1

    if invalid_count != 0:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
