"""
scripts/generate_soap.py

Generate deterministic SOAP notes for existing patient JSON files.

Run from project root:

    python scripts/generate_soap.py
    python scripts/generate_soap.py --dry-run
    python scripts/generate_soap.py --patient-id PAT-MOD-003
    python scripts/generate_soap.py --source-dir data/patients --output-dir data/patients

Purpose:
    This script regenerates visit["soap_note"] for patient JSON files using the
    deterministic SOAP pipeline, then audits the generated SOAP notes before
    writing them back.

Pipeline:
    1. Load patient JSON files.
    2. Run structured validation before SOAP generation.
    3. Skip SOAP generation for any patient with FAIL-level validation issues.
    4. Generate SOAP notes with add_soap_notes_to_patient().
    5. Audit generated SOAP notes with audit_patient_soap().
    6. Write updated patient JSON files only if validation and SOAP audit have
       zero FAIL issues.

Safety contract:
    - Validation is the hard gate before SOAP generation.
    - No LLM calls.
    - No randomization.
    - No schema changes.
    - No medical inference.
    - No medication, lab, diagnosis, vital, or condition generation.
    - SOAP text is generated only from structured patient JSON facts.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.constants import JSON_ENCODING, JSON_INDENT  # noqa: E402
from config.paths import (  # noqa: E402
    PATIENTS_DIR,
    QUARANTINE_DIR,
    ensure_project_directories,
)
from soap.soap_auditor import (  # noqa: E402
    SoapAuditIssue,
    SoapAuditSeverity,
    audit_patient_soap,
    flatten_issues,
)
from soap.soap_generator import add_soap_notes_to_patient  # noqa: E402
from validators.rules import ValidationIssue, validate_patient  # noqa: E402


@dataclass(frozen=True)
class SoapGenerationFileResult:
    """
    Result for one processed patient file.

    Attributes:
        patient_id:
            Patient identifier from the JSON file or file stem if loading fails.
        path:
            Source patient JSON path.
        output_path:
            Destination path where the updated patient JSON would be written.
        validation_failures:
            FAIL-level structured validation issues found before SOAP generation.
        validation_warnings:
            WARN-level structured validation issues found before SOAP generation.
        soap_failures:
            FAIL-level SOAP audit issues after SOAP generation.
        soap_warnings:
            WARN-level SOAP audit issues after SOAP generation.
        skipped:
            True when SOAP generation was skipped because validation failed or
            the patient file could not be loaded.
        written:
            True if an updated patient JSON file was written.
    """

    patient_id: str
    path: Path
    output_path: Path
    validation_failures: tuple[ValidationIssue, ...]
    validation_warnings: tuple[ValidationIssue, ...]
    soap_failures: tuple[SoapAuditIssue, ...]
    soap_warnings: tuple[SoapAuditIssue, ...]
    skipped: bool
    written: bool

    @property
    def passed(self) -> bool:
        """Return True only if validation and SOAP audit both have zero FAIL issues."""
        return not self.validation_failures and not self.soap_failures


def generate_soap_for_files(
    *,
    source_dir: Path = PATIENTS_DIR,
    output_dir: Path = PATIENTS_DIR,
    patient_ids: set[str] | None = None,
    dry_run: bool = False,
) -> list[SoapGenerationFileResult]:
    """
    Generate SOAP notes for patient JSON files.

    Args:
        source_dir:
            Directory containing input patient JSON files.
        output_dir:
            Directory where updated patient JSON files should be written.
        patient_ids:
            Optional set of patient IDs to process. If None, all patient files
            in source_dir are processed.
        dry_run:
            If True, validate, generate, and audit SOAP notes without writing
            patient files.

    Returns:
        List of SoapGenerationFileResult objects.
    """
    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()

    patient_files = _patient_files(source_dir, patient_ids=patient_ids)
    results: list[SoapGenerationFileResult] = []

    for path in patient_files:
        output_path = output_dir / path.name
        patient, load_issue = _read_patient_json_safely(path)

        if load_issue is not None:
            _write_generation_issue_report(
                patient_id=load_issue.patient_id,
                validation_issues=(load_issue,),
                soap_issues=(),
            )
            results.append(
                SoapGenerationFileResult(
                    patient_id=load_issue.patient_id,
                    path=path,
                    output_path=output_path,
                    validation_failures=(load_issue,),
                    validation_warnings=(),
                    soap_failures=(),
                    soap_warnings=(),
                    skipped=True,
                    written=False,
                )
            )
            continue

        patient_id = str(patient.get("patient_id", path.stem))
        validation_issues = tuple(validate_patient(patient))
        validation_failures = tuple(
            issue for issue in validation_issues if issue.severity == "FAIL"
        )
        validation_warnings = tuple(
            issue for issue in validation_issues if issue.severity == "WARN"
        )

        if validation_failures:
            _write_generation_issue_report(
                patient_id=patient_id,
                validation_issues=validation_issues,
                soap_issues=(),
            )
            results.append(
                SoapGenerationFileResult(
                    patient_id=patient_id,
                    path=path,
                    output_path=output_path,
                    validation_failures=validation_failures,
                    validation_warnings=validation_warnings,
                    soap_failures=(),
                    soap_warnings=(),
                    skipped=True,
                    written=False,
                )
            )
            continue

        updated_patient = add_soap_notes_to_patient(patient)
        audit_results = audit_patient_soap(updated_patient)
        soap_issues = tuple(flatten_issues(audit_results))

        soap_failures = tuple(
            issue
            for issue in soap_issues
            if issue.severity == SoapAuditSeverity.FAIL
        )
        soap_warnings = tuple(
            issue
            for issue in soap_issues
            if issue.severity == SoapAuditSeverity.WARN
        )

        written = False

        if not soap_failures and not dry_run:
            _write_patient_json(output_path, updated_patient)
            written = True

        if soap_failures:
            _write_generation_issue_report(
                patient_id=patient_id,
                validation_issues=validation_issues,
                soap_issues=soap_issues,
            )

        results.append(
            SoapGenerationFileResult(
                patient_id=patient_id,
                path=path,
                output_path=output_path,
                validation_failures=validation_failures,
                validation_warnings=validation_warnings,
                soap_failures=soap_failures,
                soap_warnings=soap_warnings,
                skipped=False,
                written=written,
            )
        )

    return results


def _patient_files(
    source_dir: Path,
    *,
    patient_ids: set[str] | None,
) -> list[Path]:
    """
    Return sorted patient JSON files from source_dir.

    Args:
        source_dir:
            Directory containing patient JSON files.
        patient_ids:
            Optional patient IDs to include.

    Returns:
        Sorted list of patient JSON paths.

    Raises:
        FileNotFoundError:
            If source_dir does not exist or no matching patient files are found.
    """
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory does not exist: {source_dir}")

    files = sorted(source_dir.glob("PAT-*.json"))

    if patient_ids is not None:
        files = [path for path in files if path.stem in patient_ids]

    if not files:
        if patient_ids:
            selected = ", ".join(sorted(patient_ids))
            raise FileNotFoundError(
                f"No matching patient JSON files found in {source_dir} "
                f"for patient IDs: {selected}"
            )

        raise FileNotFoundError(f"No PAT-*.json files found in {source_dir}")

    return files


def _read_patient_json_safely(path: Path) -> tuple[dict[str, Any], ValidationIssue | None]:
    """
    Read one patient JSON file without crashing the whole SOAP generation run.

    Returns:
        (patient, None) when loading succeeds.
        ({}, ValidationIssue) when loading fails.
    """
    try:
        return json.loads(path.read_text(encoding=JSON_ENCODING)), None
    except json.JSONDecodeError as exc:
        return {}, ValidationIssue(
            rule_id="LOAD",
            severity="FAIL",
            patient_id=path.stem,
            location=str(path),
            message=f"Invalid JSON: {exc}",
        )
    except OSError as exc:
        return {}, ValidationIssue(
            rule_id="LOAD",
            severity="FAIL",
            patient_id=path.stem,
            location=str(path),
            message=f"Could not read patient JSON file: {exc}",
        )


def _write_patient_json(path: Path, patient: dict[str, Any]) -> None:
    """Write one patient JSON file using project JSON formatting constants."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(patient, indent=JSON_INDENT, ensure_ascii=False),
        encoding=JSON_ENCODING,
    )


def _write_generation_issue_report(
    *,
    patient_id: str,
    validation_issues: Iterable[ValidationIssue],
    soap_issues: Iterable[SoapAuditIssue],
) -> None:
    """
    Write generation issue report to data/quarantine.

    The report may contain validation issues, SOAP audit issues, or both.
    """
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "patient_id": patient_id,
        "validation_issues": [
            {
                "rule_id": issue.rule_id,
                "severity": issue.severity,
                "patient_id": issue.patient_id,
                "location": issue.location,
                "message": issue.message,
            }
            for issue in validation_issues
        ],
        "soap_issues": [
            {
                "rule_id": issue.rule_id,
                "severity": issue.severity.value,
                "patient_id": issue.patient_id,
                "visit_id": issue.visit_id,
                "section": issue.section,
                "message": issue.message,
            }
            for issue in soap_issues
        ],
    }

    report_path = QUARANTINE_DIR / f"{patient_id}.soap_generation_issues.json"
    report_path.write_text(
        json.dumps(payload, indent=JSON_INDENT, ensure_ascii=False),
        encoding=JSON_ENCODING,
    )


def _print_summary(results: list[SoapGenerationFileResult], *, dry_run: bool) -> None:
    """Print a readable command-line summary."""
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    failed = total - passed
    skipped = sum(1 for result in results if result.skipped)
    written = sum(1 for result in results if result.written)
    validation_failures = sum(len(result.validation_failures) for result in results)
    validation_warnings = sum(len(result.validation_warnings) for result in results)
    soap_failures = sum(len(result.soap_failures) for result in results)
    soap_warnings = sum(len(result.soap_warnings) for result in results)

    print("\n=== SOAP GENERATION COMPLETE ===")
    print(f"Patients checked:      {total}")
    print(f"Patients passed:       {passed}")
    print(f"Patients failed:       {failed}")
    print(f"SOAP skipped:          {skipped}")
    print(f"Validation failures:   {validation_failures}")
    print(f"Validation warnings:   {validation_warnings}")
    print(f"SOAP failures:         {soap_failures}")
    print(f"SOAP warnings:         {soap_warnings}")
    print(f"Files written:         {written}")
    print(f"Dry run:               {dry_run}")

    if not results:
        return

    print("\n--- FILE RESULTS ---")

    for result in results:
        status = "PASS" if result.passed else "FAIL"
        write_status = "written" if result.written else "not written"
        skip_status = "skipped" if result.skipped else "processed"

        print(
            f"[{status}] {result.patient_id} "
            f"validation_failures={len(result.validation_failures)} "
            f"soap_failures={len(result.soap_failures)} "
            f"validation_warnings={len(result.validation_warnings)} "
            f"soap_warnings={len(result.soap_warnings)} "
            f"({skip_status}, {write_status})"
        )

        for issue in result.validation_failures:
            print(
                f"  - [{issue.severity}] "
                f"{issue.rule_id} / {issue.location}: {issue.message}"
            )

        for issue in result.soap_failures:
            section = issue.section if issue.section else "whole_note"
            print(
                f"  - [{issue.severity.value}] "
                f"{issue.rule_id} / {issue.visit_id} / {section}: "
                f"{issue.message}"
            )


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate deterministic SOAP notes for patient JSON files."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=PATIENTS_DIR,
        help="Directory containing PAT-*.json patient files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PATIENTS_DIR,
        help="Directory where updated patient files should be written.",
    )
    parser.add_argument(
        "--patient-id",
        action="append",
        default=None,
        help=(
            "Optional patient ID to process. Can be repeated. "
            "Example: --patient-id PAT-MOD-003"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate, generate, and audit SOAP notes without writing patient files.",
    )

    args = parser.parse_args()

    ensure_project_directories()

    patient_ids = set(args.patient_id) if args.patient_id else None

    try:
        results = generate_soap_for_files(
            source_dir=args.source_dir,
            output_dir=args.output_dir,
            patient_ids=patient_ids,
            dry_run=args.dry_run,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _print_summary(results, dry_run=args.dry_run)

    failed_results = [result for result in results if not result.passed]

    if failed_results:
        print(
            "\nERROR: One or more patient files failed validation or SOAP audit. "
            f"Issue reports were written to: {QUARANTINE_DIR}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
