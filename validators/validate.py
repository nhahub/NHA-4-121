"""
validators/validate.py

Validation runner and approval gate for the v1.7 Lite synthetic clinical
dataset.

This module is orchestration only:
- load generated patient JSON files,
- run validators.rules V1-V12,
- write a structured validation report,
- return a failing exit code when blocking FAIL issues exist.

It must not mutate patient files, repair records, generate SOAP, create chunks,
call ChromaDB, or call any LLM/API.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


# Allow both execution styles:
#   python validators/validate.py
#   python -m validators.validate
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.constants import (  # noqa: E402
    DATASET_VERSION,
    EXPECTED_V17_LITE_PATIENT_COUNT,
    JSON_ENCODING,
    JSON_INDENT,
    PROJECT_NAME,
)
from validators.rules import (  # noqa: E402
    FAIL,
    WARN,
    ValidationIssue,
    ValidationSummary,
    run_all_rules,
)


DEFAULT_PATIENTS_DIR = _PROJECT_ROOT / "data" / "patients"
DEFAULT_REPORT_DIR = _PROJECT_ROOT / "logs" / "validation_reports"


@dataclass(frozen=True)
class LoadedPatientFile:
    """One successfully loaded patient JSON file."""

    path: Path
    patient: dict[str, Any]


@dataclass(frozen=True)
class ValidationRunResult:
    """Result returned by validate_patient_files()."""

    summary: ValidationSummary
    report_path: Path | None
    patients_dir: Path
    files_checked: int
    patient_ids: list[str]
    strict_diversity: bool

    @property
    def passed(self) -> bool:
        return self.summary.passed

    @property
    def exit_code(self) -> int:
        return 0 if self.passed else 1


class ValidationRunnerError(RuntimeError):
    """Raised when the validation runner cannot complete safely."""


# ---------------------------------------------------------------------------
# Public workflow
# ---------------------------------------------------------------------------


def validate_patient_files(
    *,
    patients_path: Path = DEFAULT_PATIENTS_DIR,
    report_dir: Path = DEFAULT_REPORT_DIR,
    strict_diversity: bool = True,
    write_report: bool = True,
    report_name: str | None = None,
) -> ValidationRunResult:
    """Load patient JSON files and run V1-V12 validation.

    Args:
        patients_path: Directory containing PAT-*.json files, or a single JSON
            file for focused debugging.
        report_dir: Directory where the JSON validation report is written.
        strict_diversity: Keep True before final ingestion so V12 diversity
            issues are blocking FAIL findings. Use False during active local
            development to downgrade some V12 duplicate findings to WARN.
        write_report: Whether to write a structured report JSON.
        report_name: Optional explicit report filename.

    Returns:
        ValidationRunResult with summary, report path, checked files, and IDs.
    """

    patients_path = patients_path.resolve()
    report_dir = report_dir.resolve()

    loaded_files, load_issues = load_patient_records(patients_path)
    patients = [item.patient for item in loaded_files]

    if patients:
        summary = run_all_rules(patients, strict_diversity=strict_diversity)
        all_issues = tuple(load_issues) + tuple(summary.issues)
    else:
        all_issues = tuple(load_issues) + (
            ValidationIssue(
                rule_id="LOAD",
                severity=FAIL,
                patient_id="UNKNOWN",
                path=str(patients_path),
                message="No patient JSON files were loaded for validation.",
                context={"patients_path": str(patients_path)},
            ),
        )

    final_summary = ValidationSummary(all_issues)
    patient_ids = [_safe_patient_id(item.patient, fallback=item.path.stem) for item in loaded_files]

    report_path: Path | None = None
    if write_report:
        report_path = write_validation_report(
            summary=final_summary,
            report_dir=report_dir,
            report_name=report_name,
            patients_path=patients_path,
            files_checked=len(loaded_files),
            patient_ids=patient_ids,
            strict_diversity=strict_diversity,
        )

    return ValidationRunResult(
        summary=final_summary,
        report_path=report_path,
        patients_dir=patients_path,
        files_checked=len(loaded_files),
        patient_ids=patient_ids,
        strict_diversity=strict_diversity,
    )


# Backward-compatible aliases for scripts/tests that may prefer shorter names.
validate_all = validate_patient_files
run_validation = validate_patient_files


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_patient_records(patients_path: Path) -> tuple[list[LoadedPatientFile], list[ValidationIssue]]:
    """Load patient records from a directory or single JSON file.

    JSON parse failures are returned as LOAD/FAIL issues instead of raising, so
    the caller can still receive a complete validation report.
    """

    issues: list[ValidationIssue] = []
    loaded: list[LoadedPatientFile] = []

    if not patients_path.exists():
        issues.append(ValidationIssue(
            rule_id="LOAD",
            severity=FAIL,
            patient_id="UNKNOWN",
            path=str(patients_path),
            message="Patient path does not exist.",
            context={"patients_path": str(patients_path)},
        ))
        return loaded, issues

    json_files = _resolve_patient_files(patients_path)
    if not json_files:
        issues.append(ValidationIssue(
            rule_id="LOAD",
            severity=FAIL,
            patient_id="UNKNOWN",
            path=str(patients_path),
            message="No PAT-*.json files found.",
            context={"patients_path": str(patients_path)},
        ))
        return loaded, issues

    seen_patient_ids: dict[str, Path] = {}

    for file_path in json_files:
        try:
            patient = _load_json_file(file_path)
        except Exception as exc:  # noqa: BLE001 - report as validation issue
            issues.append(ValidationIssue(
                rule_id="LOAD",
                severity=FAIL,
                patient_id=file_path.stem,
                path=str(file_path),
                message=f"Could not load patient JSON: {exc}",
                context={"file": str(file_path), "error_type": type(exc).__name__},
            ))
            continue

        if not isinstance(patient, dict):
            issues.append(ValidationIssue(
                rule_id="LOAD",
                severity=FAIL,
                patient_id=file_path.stem,
                path=str(file_path),
                message="Patient JSON root must be an object/dictionary.",
                context={"file": str(file_path), "actual_type": type(patient).__name__},
            ))
            continue

        patient_id = _safe_patient_id(patient, fallback=file_path.stem)
        if patient_id in seen_patient_ids:
            issues.append(ValidationIssue(
                rule_id="LOAD",
                severity=FAIL,
                patient_id=patient_id,
                path=str(file_path),
                message="Duplicate patient_id across loaded files.",
                context={
                    "first_file": str(seen_patient_ids[patient_id]),
                    "duplicate_file": str(file_path),
                },
            ))
        else:
            seen_patient_ids[patient_id] = file_path

        loaded.append(LoadedPatientFile(path=file_path, patient=patient))

    return loaded, issues


def _resolve_patient_files(patients_path: Path) -> list[Path]:
    if patients_path.is_file():
        return [patients_path]
    return sorted(p for p in patients_path.glob("PAT-*.json") if p.is_file())


def _load_json_file(file_path: Path) -> Any:
    with file_path.open("r", encoding=JSON_ENCODING) as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def write_validation_report(
    *,
    summary: ValidationSummary,
    report_dir: Path,
    patients_path: Path,
    files_checked: int,
    patient_ids: Sequence[str],
    strict_diversity: bool,
    report_name: str | None = None,
) -> Path:
    """Write a structured JSON validation report."""

    report_dir.mkdir(parents=True, exist_ok=True)
    if report_name is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_name = f"validation_report_{timestamp}.json"
    elif not report_name.endswith(".json"):
        report_name = f"{report_name}.json"

    report_path = report_dir / report_name
    report = build_report_payload(
        summary=summary,
        patients_path=patients_path,
        files_checked=files_checked,
        patient_ids=patient_ids,
        strict_diversity=strict_diversity,
    )

    with report_path.open("w", encoding=JSON_ENCODING) as handle:
        json.dump(report, handle, indent=JSON_INDENT, ensure_ascii=False)
        handle.write("\n")

    return report_path


def build_report_payload(
    *,
    summary: ValidationSummary,
    patients_path: Path,
    files_checked: int,
    patient_ids: Sequence[str],
    strict_diversity: bool,
) -> dict[str, Any]:
    """Build the JSON-serializable validation report payload."""

    issues_by_rule: dict[str, dict[str, int]] = {}
    for issue in summary.issues:
        bucket = issues_by_rule.setdefault(issue.rule_id, {FAIL: 0, WARN: 0, "INFO": 0, "REPORT": 0})
        bucket[issue.severity] = bucket.get(issue.severity, 0) + 1

    return {
        "project": PROJECT_NAME,
        "dataset_version": DATASET_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if summary.passed else "FAIL",
        "strict_diversity": strict_diversity,
        "patients_path": str(patients_path),
        "files_checked": files_checked,
        "expected_patient_count": EXPECTED_V17_LITE_PATIENT_COUNT,
        "patient_ids": list(patient_ids),
        "summary": summary.as_dict(),
        "issues_by_rule": issues_by_rule,
        "approval_gate": {
            "can_generate_soap": summary.passed,
            "can_run_ingestion": summary.passed,
            "can_handoff_to_rag": summary.passed,
            "reason": "Zero FAIL issues required before SOAP, ingestion, or RAG handoff.",
        },
    }


def print_validation_summary(
    result: ValidationRunResult,
    *,
    max_issues: int = 25,
) -> None:
    """Print a compact human-readable validation summary."""

    summary = result.summary
    status = "PASS" if summary.passed else "FAIL"

    print("=" * 80)
    print("V1-V12 DATASET VALIDATION")
    print("=" * 80)
    print(f"Status:            {status}")
    print(f"Dataset version:   {DATASET_VERSION}")
    print(f"Patients path:     {result.patients_dir}")
    print(f"Files checked:     {result.files_checked}")
    print(f"Expected patients: {EXPECTED_V17_LITE_PATIENT_COUNT}")
    print(f"Strict diversity:  {result.strict_diversity}")
    print(f"FAIL:              {summary.fail_count}")
    print(f"WARN:              {summary.warn_count}")
    print(f"INFO/REPORT:       {summary.info_count}")

    if result.report_path is not None:
        print(f"Report:            {result.report_path}")

    if summary.issues:
        print("-" * 80)
        print(f"Issues shown:      {min(max_issues, len(summary.issues))}/{len(summary.issues)}")
        for issue in summary.issues[:max_issues]:
            location = f" at {issue.path}" if issue.path else ""
            print(f"[{issue.severity}] {issue.rule_id} {issue.patient_id}{location}: {issue.message}")
        if len(summary.issues) > max_issues:
            print(f"... {len(summary.issues) - max_issues} more issue(s) hidden. See JSON report.")

    print("=" * 80)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    result = validate_patient_files(
        patients_path=args.patients_dir,
        report_dir=args.report_dir,
        strict_diversity=not args.development,
        write_report=not args.no_report,
        report_name=args.report_name,
    )

    if not args.quiet:
        print_validation_summary(result, max_issues=args.max_issues)

    return result.exit_code


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate generated v1.7 Lite patient JSON files with V1-V12 rules.",
    )
    parser.add_argument(
        "--patients-dir",
        type=Path,
        default=DEFAULT_PATIENTS_DIR,
        help="Directory containing PAT-*.json files, or a single patient JSON file.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="Directory where validation report JSON will be written.",
    )
    parser.add_argument(
        "--report-name",
        type=str,
        default=None,
        help="Optional report filename. .json is added if omitted.",
    )
    parser.add_argument(
        "--development",
        action="store_true",
        help="Development mode: downgrade selected V12 diversity duplicates to WARN via strict_diversity=False.",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Do not write a JSON validation report.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console summary. Exit code still reflects PASS/FAIL.",
    )
    parser.add_argument(
        "--max-issues",
        type=int,
        default=25,
        help="Maximum number of issues to show in console output.",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _safe_patient_id(patient: dict[str, Any], *, fallback: str = "UNKNOWN") -> str:
    patient_id = patient.get("patient_id")
    return str(patient_id) if patient_id else fallback


def _iter_failures(issues: Iterable[ValidationIssue]) -> Iterable[ValidationIssue]:
    for issue in issues:
        if issue.severity == FAIL:
            yield issue


def _iter_warnings(issues: Iterable[ValidationIssue]) -> Iterable[ValidationIssue]:
    for issue in issues:
        if issue.severity == WARN:
            yield issue


__all__ = [
    "DEFAULT_PATIENTS_DIR",
    "DEFAULT_REPORT_DIR",
    "LoadedPatientFile",
    "ValidationRunResult",
    "ValidationRunnerError",
    "validate_patient_files",
    "validate_all",
    "run_validation",
    "load_patient_records",
    "write_validation_report",
    "build_report_payload",
    "print_validation_summary",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
