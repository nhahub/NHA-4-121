"""
scripts/generate_soap.py

Generate deterministic SOAP notes for existing v1.7 Lite patient JSON files.

Run from project root:

    python scripts/generate_soap.py
    python scripts/generate_soap.py --dry-run
    python scripts/generate_soap.py --patient-id PAT-MOD-003
    python scripts/generate_soap.py --source-dir data/patients --output-dir data/patients

Purpose:
    This script is an orchestration layer only. It validates structured patient
    records, generates deterministic SOAP notes from structured facts, audits
    the generated SOAP notes, and writes the updated JSON files only when both
    validation and SOAP audit have zero FAIL issues.

Pipeline:
    1. Load PAT-*.json patient files.
    2. Run V1-V12 structured validation as the hard pre-SOAP gate.
    3. Skip SOAP generation for any selected patient with FAIL-level validation
       issues.
    4. Generate SOAP notes with soap.soap_generator.add_soap_notes_to_patient().
    5. Audit generated SOAP notes with soap.soap_auditor.audit_patient_soap().
    6. Write updated patient JSON files only if validation and SOAP audit have
       zero FAIL issues.

Safety contract:
    - Validation is the hard gate before SOAP generation.
    - No LLM calls.
    - No randomization.
    - No schema changes except replacing visit["soap_note"].
    - No medical inference.
    - No medication, lab, diagnosis, vital, or condition generation.
    - SOAP text is generated only from structured patient JSON facts.
    - This script does not contain SOAP template, rendering, selector, or audit
      business logic.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.constants import (  # noqa: E402
    DATASET_VERSION,
    EXPECTED_FULL_PATIENT_COUNT,
    JSON_ENCODING,
    JSON_INDENT,
)
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
from soap.soap_generator import (  # noqa: E402
    SOAP_GENERATOR_VERSION,
    add_soap_notes_to_patient,
)
from validators.rules import (  # noqa: E402
    FAIL,
    WARN,
    ValidationIssue,
    validate_dataset,
)


SCRIPT_VERSION = "generate-soap-v1.7-lite"


@dataclass(frozen=True)
class SoapGenerationFileResult:
    """Result for one processed patient file."""

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
        """Return True when this patient has no FAIL validation or SOAP issues."""
        return not self.validation_failures and not self.soap_failures


@dataclass(frozen=True)
class LoadedPatientFile:
    """Loaded patient file and parsed JSON record."""

    path: Path
    patient: dict[str, Any]

    @property
    def patient_id(self) -> str:
        return str(self.patient.get("patient_id") or self.path.stem)


@dataclass(frozen=True)
class SoapGenerationRunResult:
    """Aggregate SOAP generation run result."""

    results: tuple[SoapGenerationFileResult, ...]
    source_dir: Path
    output_dir: Path
    dry_run: bool
    strict_diversity: bool

    @property
    def failed(self) -> bool:
        return any(not result.passed for result in self.results)

    @property
    def passed(self) -> bool:
        return not self.failed

    @property
    def files_written(self) -> int:
        return sum(1 for result in self.results if result.written)

    @property
    def patients_checked(self) -> int:
        return len(self.results)

    @property
    def validation_fail_count(self) -> int:
        return sum(len(result.validation_failures) for result in self.results)

    @property
    def validation_warn_count(self) -> int:
        return sum(len(result.validation_warnings) for result in self.results)

    @property
    def soap_fail_count(self) -> int:
        return sum(len(result.soap_failures) for result in self.results)

    @property
    def soap_warn_count(self) -> int:
        return sum(len(result.soap_warnings) for result in self.results)


def generate_soap_for_files(
    *,
    source_dir: Path = PATIENTS_DIR,
    output_dir: Path = PATIENTS_DIR,
    patient_ids: set[str] | None = None,
    dry_run: bool = False,
    strict_diversity: bool = True,
    write_issue_reports: bool = True,
) -> SoapGenerationRunResult:
    """
    Generate SOAP notes for selected patient JSON files.

    Dataset-level validation is run over all available patient files in
    source_dir, not only the selected patient IDs. This keeps V12 diversity
    checks meaningful while still allowing --patient-id to process only one
    file.
    """
    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()

    all_files = _patient_files(source_dir, patient_ids=None)
    selected_files = _select_patient_files(all_files, patient_ids=patient_ids)

    loaded_files, load_issues = _load_patient_files(all_files)
    loaded_by_path = {loaded.path: loaded for loaded in loaded_files}

    validation_issues = list(load_issues)
    if loaded_files:
        validation_issues.extend(
            validate_dataset(
                [loaded.patient for loaded in loaded_files],
                strict_diversity=strict_diversity,
            ).issues
        )

    validation_by_patient = _group_validation_issues_by_patient(validation_issues)
    global_validation_failures = tuple(
        issue
        for issue in validation_issues
        if _validation_issue_severity(issue) == FAIL
        and _validation_issue_patient_id(issue) not in _loaded_patient_ids(loaded_files)
    )

    results: list[SoapGenerationFileResult] = []

    for path in selected_files:
        output_path = output_dir / path.name
        loaded = loaded_by_path.get(path)
        patient_id = loaded.patient_id if loaded is not None else path.stem

        patient_validation_issues = tuple(validation_by_patient.get(patient_id, ()))
        validation_failures = tuple(
            issue
            for issue in (*global_validation_failures, *patient_validation_issues)
            if _validation_issue_severity(issue) == FAIL
        )
        validation_warnings = tuple(
            issue
            for issue in patient_validation_issues
            if _validation_issue_severity(issue) == WARN
        )

        if loaded is None or validation_failures:
            if write_issue_reports:
                _write_generation_issue_report(
                    patient_id=patient_id,
                    validation_issues=(*global_validation_failures, *patient_validation_issues),
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

        updated_patient = add_soap_notes_to_patient(loaded.patient)
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

        if soap_failures and write_issue_reports:
            _write_generation_issue_report(
                patient_id=patient_id,
                validation_issues=patient_validation_issues,
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

    return SoapGenerationRunResult(
        results=tuple(results),
        source_dir=source_dir,
        output_dir=output_dir,
        dry_run=dry_run,
        strict_diversity=strict_diversity,
    )


def _patient_files(source_dir: Path, *, patient_ids: set[str] | None) -> list[Path]:
    """Return sorted PAT-*.json files from source_dir."""
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


def _select_patient_files(
    all_files: Sequence[Path],
    *,
    patient_ids: set[str] | None,
) -> list[Path]:
    """Select files for processing while validating requested IDs exist."""
    if patient_ids is None:
        return list(all_files)

    available = {path.stem: path for path in all_files}
    missing = sorted(patient_id for patient_id in patient_ids if patient_id not in available)
    if missing:
        raise FileNotFoundError(
            "No matching patient JSON files found for patient IDs: "
            + ", ".join(missing)
        )

    return [available[patient_id] for patient_id in sorted(patient_ids)]


def _load_patient_files(
    patient_files: Iterable[Path],
) -> tuple[list[LoadedPatientFile], list[ValidationIssue]]:
    """Load patient files and convert JSON/read errors to validation issues."""
    loaded: list[LoadedPatientFile] = []
    issues: list[ValidationIssue] = []

    for path in patient_files:
        patient, issue = _read_patient_json_safely(path)
        if issue is not None:
            issues.append(issue)
            continue
        loaded.append(LoadedPatientFile(path=path, patient=patient))

    return loaded, issues


def _read_patient_json_safely(path: Path) -> tuple[dict[str, Any], ValidationIssue | None]:
    """Read one patient JSON file without crashing the full run."""
    try:
        loaded = json.loads(path.read_text(encoding=JSON_ENCODING))
    except json.JSONDecodeError as exc:
        return {}, ValidationIssue(
            rule_id="LOAD",
            severity=FAIL,
            patient_id=path.stem,
            message=f"Invalid JSON: {exc}",
            path=str(path),
        )
    except OSError as exc:
        return {}, ValidationIssue(
            rule_id="LOAD",
            severity=FAIL,
            patient_id=path.stem,
            message=f"Could not read patient JSON file: {exc}",
            path=str(path),
        )

    if not isinstance(loaded, dict):
        return {}, ValidationIssue(
            rule_id="LOAD",
            severity=FAIL,
            patient_id=path.stem,
            message="Patient JSON root must be an object.",
            path=str(path),
        )

    return loaded, None


def _write_patient_json(path: Path, patient: dict[str, Any]) -> None:
    """Write one patient JSON file using project JSON formatting constants."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(patient, indent=JSON_INDENT, ensure_ascii=False) + "\n",
        encoding=JSON_ENCODING,
    )


def _write_generation_issue_report(
    *,
    patient_id: str,
    validation_issues: Iterable[ValidationIssue],
    soap_issues: Iterable[SoapAuditIssue],
) -> Path:
    """Write SOAP generation issue report to data/quarantine."""
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "script_version": SCRIPT_VERSION,
        "dataset_version": DATASET_VERSION,
        "patient_id": patient_id,
        "created_at_utc": _utc_timestamp(),
        "validation_issues": [
            _validation_issue_to_dict(issue)
            for issue in validation_issues
        ],
        "soap_issues": [
            _soap_issue_to_dict(issue)
            for issue in soap_issues
        ],
    }

    report_path = QUARANTINE_DIR / f"{patient_id}.soap_generation_issues.json"
    report_path.write_text(
        json.dumps(payload, indent=JSON_INDENT, ensure_ascii=False) + "\n",
        encoding=JSON_ENCODING,
    )
    return report_path


def _write_run_report(run_result: SoapGenerationRunResult) -> Path:
    """Write one aggregate run report to data/quarantine for traceability."""
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    report_path = QUARANTINE_DIR / f"soap_generation_run_{_utc_timestamp()}.json"
    payload = {
        "script_version": SCRIPT_VERSION,
        "soap_generator_version": SOAP_GENERATOR_VERSION,
        "dataset_version": DATASET_VERSION,
        "source_dir": str(run_result.source_dir),
        "output_dir": str(run_result.output_dir),
        "dry_run": run_result.dry_run,
        "strict_diversity": run_result.strict_diversity,
        "patients_checked": run_result.patients_checked,
        "files_written": run_result.files_written,
        "validation_fail_count": run_result.validation_fail_count,
        "validation_warn_count": run_result.validation_warn_count,
        "soap_fail_count": run_result.soap_fail_count,
        "soap_warn_count": run_result.soap_warn_count,
        "status": "PASS" if run_result.passed else "FAIL",
        "results": [
            {
                "patient_id": result.patient_id,
                "source_path": str(result.path),
                "output_path": str(result.output_path),
                "passed": result.passed,
                "skipped": result.skipped,
                "written": result.written,
                "validation_failures": len(result.validation_failures),
                "validation_warnings": len(result.validation_warnings),
                "soap_failures": len(result.soap_failures),
                "soap_warnings": len(result.soap_warnings),
            }
            for result in run_result.results
        ],
    }
    report_path.write_text(
        json.dumps(payload, indent=JSON_INDENT, ensure_ascii=False) + "\n",
        encoding=JSON_ENCODING,
    )
    return report_path


def _print_summary(run_result: SoapGenerationRunResult) -> None:
    """Print a readable command-line summary."""
    passed = sum(1 for result in run_result.results if result.passed)
    failed = run_result.patients_checked - passed
    skipped = sum(1 for result in run_result.results if result.skipped)

    print("=" * 80)
    print("v1.7 Lite SOAP generation complete")
    print("=" * 80)
    print(f"Script version:       {SCRIPT_VERSION}")
    print(f"SOAP generator:       {SOAP_GENERATOR_VERSION}")
    print(f"Dataset version:      {DATASET_VERSION}")
    print(f"Source dir:           {run_result.source_dir}")
    print(f"Output dir:           {run_result.output_dir}")
    print(f"Strict diversity:     {run_result.strict_diversity}")
    print(f"Dry run:              {run_result.dry_run}")
    print(f"Patients checked:     {run_result.patients_checked}")
    print(f"Patients passed:      {passed}")
    print(f"Patients failed:      {failed}")
    print(f"SOAP skipped:         {skipped}")
    print(f"Validation failures:  {run_result.validation_fail_count}")
    print(f"Validation warnings:  {run_result.validation_warn_count}")
    print(f"SOAP failures:        {run_result.soap_fail_count}")
    print(f"SOAP warnings:        {run_result.soap_warn_count}")
    print(f"Files written:        {run_result.files_written}")

    if not run_result.results:
        return

    print("-" * 80)
    print("Patient results:")
    for result in run_result.results:
        status = "PASS" if result.passed else "FAIL"
        write_status = "written" if result.written else "not_written"
        skip_status = "skipped" if result.skipped else "processed"
        print(
            f"[{status}] {result.patient_id} "
            f"validation_failures={len(result.validation_failures)} "
            f"soap_failures={len(result.soap_failures)} "
            f"validation_warnings={len(result.validation_warnings)} "
            f"soap_warnings={len(result.soap_warnings)} "
            f"({skip_status}, {write_status})"
        )

        for issue in result.validation_failures[:5]:
            print(
                f"  - [{_validation_issue_severity(issue)}] "
                f"{issue.rule_id} / {_validation_issue_path(issue)}: {issue.message}"
            )
        if len(result.validation_failures) > 5:
            print(f"  - ... {len(result.validation_failures) - 5} more validation failures")

        for issue in result.soap_failures[:5]:
            section = issue.section if issue.section else "whole_note"
            print(
                f"  - [{issue.severity.value}] "
                f"{issue.rule_id} / {issue.visit_id} / {section}: {issue.message}"
            )
        if len(result.soap_failures) > 5:
            print(f"  - ... {len(result.soap_failures) - 5} more SOAP failures")

    print("=" * 80)
    if run_result.passed:
        print("Next step: run scripts/validate_all.py again after SOAP generation.")


def _group_validation_issues_by_patient(
    issues: Iterable[ValidationIssue],
) -> dict[str, list[ValidationIssue]]:
    grouped: dict[str, list[ValidationIssue]] = {}
    for issue in issues:
        grouped.setdefault(_validation_issue_patient_id(issue), []).append(issue)
    return grouped


def _loaded_patient_ids(loaded_files: Iterable[LoadedPatientFile]) -> set[str]:
    return {loaded.patient_id for loaded in loaded_files}


def _validation_issue_patient_id(issue: ValidationIssue) -> str:
    return str(getattr(issue, "patient_id", "DATASET"))


def _validation_issue_severity(issue: ValidationIssue) -> str:
    return str(getattr(issue, "severity", ""))


def _validation_issue_path(issue: ValidationIssue) -> str:
    return str(getattr(issue, "path", getattr(issue, "location", "")))


def _validation_issue_to_dict(issue: ValidationIssue) -> dict[str, Any]:
    as_dict = getattr(issue, "as_dict", None)
    if callable(as_dict):
        return dict(as_dict())
    return {
        "rule_id": getattr(issue, "rule_id", "UNKNOWN"),
        "severity": _validation_issue_severity(issue),
        "patient_id": _validation_issue_patient_id(issue),
        "path": _validation_issue_path(issue),
        "message": str(getattr(issue, "message", "")),
    }


def _soap_issue_to_dict(issue: SoapAuditIssue) -> dict[str, Any]:
    return {
        "rule_id": issue.rule_id,
        "severity": issue.severity.value,
        "patient_id": issue.patient_id,
        "visit_id": issue.visit_id,
        "section": issue.section,
        "message": issue.message,
    }


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate deterministic SOAP notes for v1.7 Lite patient JSON files."
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
        help="Optional patient ID to process. Can be repeated.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate, generate, and audit SOAP notes without writing patient files.",
    )
    parser.add_argument(
        "--development",
        action="store_true",
        help="Downgrade strict V12 diversity behavior during active development.",
    )
    parser.add_argument(
        "--no-issue-reports",
        action="store_true",
        help="Do not write per-patient issue reports to quarantine on failure.",
    )
    parser.add_argument(
        "--run-report",
        action="store_true",
        help="Write an aggregate SOAP generation run report to quarantine.",
    )

    args = parser.parse_args()
    ensure_project_directories()

    patient_ids = set(args.patient_id) if args.patient_id else None

    try:
        run_result = generate_soap_for_files(
            source_dir=args.source_dir,
            output_dir=args.output_dir,
            patient_ids=patient_ids,
            dry_run=args.dry_run,
            strict_diversity=not args.development,
            write_issue_reports=not args.no_issue_reports,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _print_summary(run_result)

    if args.run_report:
        report_path = _write_run_report(run_result)
        print(f"Run report written: {report_path}")

    if run_result.failed:
        print(
            "\nERROR: One or more patient files failed validation or SOAP audit. "
            f"Issue reports were written to: {QUARANTINE_DIR}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
