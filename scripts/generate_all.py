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
6. SOAP notes
7. SOAP audit
8. validation
9. export valid files to data/patients/
10. export invalid files to data/quarantine/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

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
from soap.soap_auditor import audit_patient_soap  # noqa: E402
from soap.soap_generator import add_soap_notes_to_patient  # noqa: E402
from validators.rules import validate_patient  # noqa: E402


def generate_all_patients(
    mode: str = DEFAULT_DATASET_MODE,
) -> list[dict[str, Any]]:
    """
    Generate the selected dataset in dependency order.

    Args:
        mode:
            - "pilot": generate 5 pilot patients
            - "full": generate 30 full-dataset patients
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
        patient = add_soap_notes_to_patient(patient)

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
    Validate and export patients.

    Valid patients go to data/patients.
    Invalid patients go to data/quarantine with issue reports.
    """
    valid_count = 0
    invalid_count = 0

    for patient in patients:
        patient_id = patient["patient_id"]
        soap_issues = audit_patient_soap(patient)
        validation_issues = validate_patient(patient)

        fail_soap = [issue for issue in soap_issues if issue.severity == "FAIL"]
        fail_validation = [
            issue
            for issue in validation_issues
            if issue.severity == "FAIL"
        ]

        is_valid = not fail_soap and not fail_validation

        if is_valid:
            _write_patient_json(patient_file_path(patient_id), patient)
            valid_count += 1
        else:
            _write_patient_json(quarantine_file_path(patient_id), patient)
            _write_issue_report(patient_id, soap_issues, validation_issues)
            invalid_count += 1

    return valid_count, invalid_count


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
    soap_issues,
    validation_issues,
) -> None:
    payload = {
        "patient_id": patient_id,
        "soap_issues": [
            {
                "severity": issue.severity,
                "patient_id": issue.patient_id,
                "visit_id": issue.visit_id,
                "message": issue.message,
            }
            for issue in soap_issues
        ],
        "validation_issues": [
            {
                "rule_id": issue.rule_id,
                "severity": issue.severity,
                "patient_id": issue.patient_id,
                "message": issue.message,
                "location": issue.location,
            }
            for issue in validation_issues
        ],
    }

    report_path = QUARANTINE_DIR / f"{patient_id}.validation_issues.json"
    report_path.write_text(
        json.dumps(payload, indent=JSON_INDENT, ensure_ascii=False),
        encoding=JSON_ENCODING,
    )


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
