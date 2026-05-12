"""
validators/validation_report.py

Readable validation report generation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from config.constants import JSON_ENCODING, JSON_INDENT
from validators.rules import ValidationIssue


@dataclass(frozen=True)
class ValidationReport:
    """Aggregated validation result."""

    patients_checked: int
    fail_count: int
    warn_count: int
    issues: list[ValidationIssue]

    @property
    def passed(self) -> bool:
        return self.fail_count == 0


def build_validation_report(
    patients_checked: int,
    issues: list[ValidationIssue],
) -> ValidationReport:
    fail_count = sum(issue.severity == "FAIL" for issue in issues)
    warn_count = sum(issue.severity == "WARN" for issue in issues)

    return ValidationReport(
        patients_checked=patients_checked,
        fail_count=fail_count,
        warn_count=warn_count,
        issues=issues,
    )


def print_validation_report(report: ValidationReport) -> None:
    """Print a readable validation report."""
    print("\n=== VALIDATION REPORT ===")
    print(f"Patients checked: {report.patients_checked}")
    print(f"FAIL violations:  {report.fail_count}")
    print(f"WARN flags:       {report.warn_count}")
    print(f"Status:           {'PASS' if report.passed else 'FAIL'}")

    failures = [issue for issue in report.issues if issue.severity == "FAIL"]
    warnings = [issue for issue in report.issues if issue.severity == "WARN"]

    if failures:
        print("\n--- FAIL VIOLATIONS ---")
        for issue in failures:
            _print_issue(issue)

    if warnings:
        print("\n--- WARNINGS ---")
        for issue in warnings:
            _print_issue(issue)


def write_validation_report(report: ValidationReport, path: Path) -> None:
    """Write validation report to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "patients_checked": report.patients_checked,
        "fail_count": report.fail_count,
        "warn_count": report.warn_count,
        "passed": report.passed,
        "issues": [asdict(issue) for issue in report.issues],
    }

    path.write_text(
        json.dumps(payload, indent=JSON_INDENT, ensure_ascii=False),
        encoding=JSON_ENCODING,
    )


def issues_for_patient(
    patient_id: str,
    issues: list[ValidationIssue],
) -> list[ValidationIssue]:
    return [issue for issue in issues if issue.patient_id == patient_id]


def _print_issue(issue: ValidationIssue) -> None:
    location = f" @ {issue.location}" if issue.location else ""
    print(
        f"[{issue.severity}] [{issue.rule_id}] "
        f"{issue.patient_id}{location} — {issue.message}"
    )