"""
validators/validate.py

Validation runner for patient JSON files.

Can be imported as a module or executed directly:

    python -m validators.validate
    python -m validators.validate --quarantine
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from config.constants import JSON_ENCODING, JSON_INDENT
from config.paths import (
    PATIENTS_DIR,
    QUARANTINE_DIR,
    ensure_project_directories,
    validation_report_path,
)
from validators.rules import ValidationIssue, validate_patient
from validators.validation_report import (
    ValidationReport,
    build_validation_report,
    issues_for_patient,
    print_validation_report,
    write_validation_report,
)


def load_patient_file(path: Path) -> dict[str, Any]:
    """Load one patient JSON file."""
    with path.open("r", encoding=JSON_ENCODING) as file:
        return json.load(file)


def load_patient_files(directory: Path = PATIENTS_DIR) -> list[tuple[Path, dict[str, Any]]]:
    """Load all patient JSON files in a directory."""
    if not directory.exists():
        return []

    loaded: list[tuple[Path, dict[str, Any]]] = []

    for path in sorted(directory.glob("PAT-*.json")):
        loaded.append((path, load_patient_file(path)))

    return loaded


def validate_patients(patients: list[dict[str, Any]]) -> ValidationReport:
    """Validate in-memory patient dictionaries."""
    all_issues: list[ValidationIssue] = []

    for patient in patients:
        all_issues.extend(validate_patient(patient))

    return build_validation_report(
        patients_checked=len(patients),
        issues=all_issues,
    )


def validate_patient_files(
    directory: Path = PATIENTS_DIR,
    *,
    quarantine_invalid: bool = False,
    write_report: bool = True,
) -> ValidationReport:
    """
    Validate all patient JSON files from a directory.

    If quarantine_invalid=True, patient files with FAIL issues are copied to
    data/quarantine/ with a per-patient validation issue file.
    """
    ensure_project_directories()

    loaded = load_patient_files(directory)
    patients = [patient for _, patient in loaded]
    report = validate_patients(patients)

    if quarantine_invalid:
        _quarantine_failed_files(loaded, report.issues)

    if write_report:
        write_validation_report(report, validation_report_path())

    return report


def _quarantine_failed_files(
    loaded: list[tuple[Path, dict[str, Any]]],
    issues: list[ValidationIssue],
) -> None:
    """Copy invalid patient files and their issue reports into quarantine."""
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

    failed_patient_ids = {
        issue.patient_id
        for issue in issues
        if issue.severity == "FAIL"
    }

    for source_path, patient in loaded:
        patient_id = patient.get("patient_id", source_path.stem)

        if patient_id not in failed_patient_ids:
            continue

        target_json = QUARANTINE_DIR / source_path.name
        shutil.copy2(source_path, target_json)

        patient_issues = issues_for_patient(patient_id, issues)
        issue_payload = [
            {
                "rule_id": issue.rule_id,
                "severity": issue.severity,
                "patient_id": issue.patient_id,
                "message": issue.message,
                "location": issue.location,
            }
            for issue in patient_issues
        ]

        target_report = QUARANTINE_DIR / f"{patient_id}.validation_issues.json"
        target_report.write_text(
            json.dumps(issue_payload, indent=JSON_INDENT, ensure_ascii=False),
            encoding=JSON_ENCODING,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate patient JSON files.")
    parser.add_argument(
        "--directory",
        type=Path,
        default=PATIENTS_DIR,
        help="Directory containing PAT-*.json files.",
    )
    parser.add_argument(
        "--quarantine",
        action="store_true",
        help="Copy invalid patient files to data/quarantine/.",
    )
    args = parser.parse_args()

    report = validate_patient_files(
        args.directory,
        quarantine_invalid=args.quarantine,
        write_report=True,
    )

    print_validation_report(report)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())