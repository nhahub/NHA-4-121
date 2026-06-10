"""
validators/validation_report.py

Human-readable validation report formatting for the v1.7 Lite synthetic
clinical dataset.

This module is intentionally presentation/serialization focused. It formats
already-produced validation results into JSON, Markdown, and console summaries.
It must not implement core validation rules, mutate patient files, generate
patient data, generate SOAP, create chunks, call ChromaDB, or call any LLM/API.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


# Support both execution styles:
#   python validators/validation_report.py --from-json logs/validation_reports/x.json
#   python -m validators.validation_report --from-json logs/validation_reports/x.json
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
    INFO,
    REPORT,
    WARN,
    ValidationIssue,
    ValidationSummary,
)

DEFAULT_REPORT_DIR = _PROJECT_ROOT / "logs" / "validation_reports"
DEFAULT_MAX_ISSUES = 40


@dataclass(frozen=True)
class ReportWriteResult:
    """Paths created by write_report_files()."""

    json_path: Path | None = None
    markdown_path: Path | None = None

    @property
    def created_paths(self) -> tuple[Path, ...]:
        paths: list[Path] = []
        if self.json_path is not None:
            paths.append(self.json_path)
        if self.markdown_path is not None:
            paths.append(self.markdown_path)
        return tuple(paths)


# ---------------------------------------------------------------------------
# JSON payload construction
# ---------------------------------------------------------------------------


def build_validation_report(
    *,
    summary: ValidationSummary | Mapping[str, Any],
    patients_path: Path | str,
    files_checked: int,
    patient_ids: Sequence[str],
    strict_diversity: bool = True,
    v13_report: Mapping[str, Any] | None = None,
    generated_at_utc: str | None = None,
    extra_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable validation report payload.

    The function accepts either a ValidationSummary object or a summary-like
    mapping. It does not run validation; it only formats the results supplied by
    validators.rules or validators.validate.
    """

    issues = _extract_issues(summary)
    counts = _severity_counts(issues)
    passed = counts[FAIL] == 0
    generated_at_utc = generated_at_utc or datetime.now(timezone.utc).isoformat()

    report: dict[str, Any] = {
        "project": PROJECT_NAME,
        "dataset_version": DATASET_VERSION,
        "generated_at_utc": generated_at_utc,
        "status": "PASS" if passed else "FAIL",
        "strict_diversity": strict_diversity,
        "patients_path": str(patients_path),
        "files_checked": files_checked,
        "expected_patient_count": EXPECTED_V17_LITE_PATIENT_COUNT,
        "patient_ids": list(patient_ids),
        "summary": {
            "passed": passed,
            "fail_count": counts[FAIL],
            "warn_count": counts[WARN],
            "info_count": counts[INFO] + counts[REPORT],
            "issue_count": len(issues),
            "issues": issues,
        },
        "issues_by_rule": group_issues_by_rule(issues),
        "issues_by_patient": group_issues_by_patient(issues),
        "v12_diversity_report": build_v12_diversity_report(issues),
        "v13_similarity_report": build_v13_similarity_report(v13_report),
        "approval_gate": build_approval_gate(
            passed=passed,
            v13_report=v13_report,
        ),
    }

    if extra_context:
        report["extra_context"] = dict(extra_context)

    return report


# Backward-compatible alias that can be imported by validators.validate later.
build_report_payload = build_validation_report


def build_approval_gate(
    *,
    passed: bool,
    v13_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact approval-gate section for downstream pipeline steps."""

    v13_summary = build_v13_similarity_report(v13_report)
    v13_critical_count = int(v13_summary.get("critical_count", 0))

    can_proceed = passed and v13_critical_count == 0
    return {
        "can_generate_soap": passed,
        "can_run_ingestion": can_proceed,
        "can_handoff_to_rag": can_proceed,
        "requires_manual_v13_review": v13_critical_count > 0,
        "reason": _approval_reason(passed=passed, v13_critical_count=v13_critical_count),
    }


def build_v12_diversity_report(issues: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize V12 issues without re-running diversity validation."""

    v12_issues = [issue for issue in issues if str(issue.get("rule_id", "")).startswith("V12")]
    counts = _severity_counts(v12_issues)
    return {
        "status": "PASS" if counts[FAIL] == 0 else "FAIL",
        "issue_count": len(v12_issues),
        "fail_count": counts[FAIL],
        "warn_count": counts[WARN],
        "info_count": counts[INFO] + counts[REPORT],
        "issues": list(v12_issues),
    }


def build_v13_similarity_report(v13_report: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize the optional V13 report-only similarity payload."""

    if not v13_report:
        return {
            "available": False,
            "status": "NOT_RUN",
            "critical_count": 0,
            "warning_count": 0,
            "critical": [],
            "warnings": [],
        }

    critical = list(v13_report.get("critical", []) or [])
    warnings = list(v13_report.get("warnings", []) or [])
    return {
        "available": True,
        "status": "REVIEW_REQUIRED" if critical else "OK",
        "model": v13_report.get("model") or v13_report.get("embedding_model"),
        "chunks_checked": v13_report.get("chunks_checked"),
        "critical_count": len(critical),
        "warning_count": len(warnings),
        "critical": critical,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Grouping helpers
# ---------------------------------------------------------------------------


def group_issues_by_rule(issues: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return counts and issue references grouped by rule_id."""

    grouped: dict[str, dict[str, Any]] = {}
    for issue in issues:
        rule_id = str(issue.get("rule_id") or "UNKNOWN")
        severity = str(issue.get("severity") or INFO)
        bucket = grouped.setdefault(
            rule_id,
            {"total": 0, FAIL: 0, WARN: 0, INFO: 0, REPORT: 0, "issues": []},
        )
        bucket["total"] += 1
        bucket[severity] = int(bucket.get(severity, 0)) + 1
        bucket["issues"].append(_compact_issue(issue))
    return grouped


def group_issues_by_patient(issues: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return counts grouped by patient_id."""

    grouped: dict[str, dict[str, Any]] = {}
    for issue in issues:
        patient_id = str(issue.get("patient_id") or "UNKNOWN")
        severity = str(issue.get("severity") or INFO)
        bucket = grouped.setdefault(
            patient_id,
            {"total": 0, FAIL: 0, WARN: 0, INFO: 0, REPORT: 0, "rules": {}},
        )
        bucket["total"] += 1
        bucket[severity] = int(bucket.get(severity, 0)) + 1
        rule_id = str(issue.get("rule_id") or "UNKNOWN")
        bucket["rules"][rule_id] = int(bucket["rules"].get(rule_id, 0)) + 1
    return grouped


# ---------------------------------------------------------------------------
# Markdown / console formatting
# ---------------------------------------------------------------------------


def format_markdown_report(
    report: Mapping[str, Any],
    *,
    max_issues: int = DEFAULT_MAX_ISSUES,
) -> str:
    """Render a validation report payload as Markdown."""

    summary = _summary(report)
    status = str(report.get("status", "UNKNOWN"))
    status_icon = "✅" if status == "PASS" else "❌"
    patient_ids = list(report.get("patient_ids", []) or [])

    lines: list[str] = [
        f"# Validation Report — {report.get('dataset_version', DATASET_VERSION)}",
        "",
        f"**Project:** {report.get('project', PROJECT_NAME)}",
        f"**Generated at UTC:** {report.get('generated_at_utc', 'unknown')}",
        f"**Status:** {status_icon} {status}",
        f"**Strict diversity:** {report.get('strict_diversity', 'unknown')}",
        f"**Patients path:** `{report.get('patients_path', '')}`",
        f"**Files checked:** {report.get('files_checked', 0)} / expected {report.get('expected_patient_count', EXPECTED_V17_LITE_PATIENT_COUNT)}",
        "",
        "## Summary",
        "",
        "| Severity | Count |",
        "|---|---:|",
        f"| FAIL | {summary.get('fail_count', 0)} |",
        f"| WARN | {summary.get('warn_count', 0)} |",
        f"| INFO/REPORT | {summary.get('info_count', 0)} |",
        f"| Total issues | {summary.get('issue_count', len(summary.get('issues', [])))} |",
        "",
    ]

    if patient_ids:
        lines.extend([
            "## Patient Files Checked",
            "",
            ", ".join(f"`{patient_id}`" for patient_id in patient_ids),
            "",
        ])

    lines.extend(_format_rule_table(report))
    lines.extend(_format_patient_table(report))
    lines.extend(_format_v12_section(report))
    lines.extend(_format_v13_section(report))
    lines.extend(_format_approval_section(report))
    lines.extend(_format_issue_details(summary.get("issues", []), max_issues=max_issues))

    return "\n".join(lines).rstrip() + "\n"


def format_console_report(
    report: Mapping[str, Any],
    *,
    max_issues: int = 25,
) -> str:
    """Render a compact console-friendly report string."""

    summary = _summary(report)
    issues = list(summary.get("issues", []) or [])
    lines = [
        "=" * 80,
        "V1-V12 DATASET VALIDATION REPORT",
        "=" * 80,
        f"Status:            {report.get('status', 'UNKNOWN')}",
        f"Dataset version:   {report.get('dataset_version', DATASET_VERSION)}",
        f"Patients path:     {report.get('patients_path', '')}",
        f"Files checked:     {report.get('files_checked', 0)}",
        f"Expected patients: {report.get('expected_patient_count', EXPECTED_V17_LITE_PATIENT_COUNT)}",
        f"Strict diversity:  {report.get('strict_diversity', 'unknown')}",
        f"FAIL:              {summary.get('fail_count', 0)}",
        f"WARN:              {summary.get('warn_count', 0)}",
        f"INFO/REPORT:       {summary.get('info_count', 0)}",
    ]

    if issues:
        lines.extend(["-" * 80, f"Issues shown:      {min(max_issues, len(issues))}/{len(issues)}"])
        for issue in issues[:max_issues]:
            location = f" at {issue.get('path')}" if issue.get("path") else ""
            lines.append(
                f"[{issue.get('severity')}] {issue.get('rule_id')} "
                f"{issue.get('patient_id')}{location}: {issue.get('message')}"
            )
        if len(issues) > max_issues:
            lines.append(f"... {len(issues) - max_issues} more issue(s) hidden. See full report.")

    v13 = report.get("v13_similarity_report") or {}
    if v13.get("available"):
        lines.extend([
            "-" * 80,
            "V13 EMBEDDING SIMILARITY REPORT",
            f"Status:            {v13.get('status')}",
            f"Critical:          {v13.get('critical_count', 0)}",
            f"Warnings:          {v13.get('warning_count', 0)}",
        ])

    lines.append("=" * 80)
    return "\n".join(lines)


def print_report(report: Mapping[str, Any], *, max_issues: int = 25) -> None:
    """Print the compact report to stdout."""

    print(format_console_report(report, max_issues=max_issues))


# ---------------------------------------------------------------------------
# File writing / loading
# ---------------------------------------------------------------------------


def write_report_files(
    report: Mapping[str, Any],
    *,
    report_dir: Path | str = DEFAULT_REPORT_DIR,
    basename: str | None = None,
    write_json: bool = True,
    write_markdown: bool = True,
    max_issues: int = DEFAULT_MAX_ISSUES,
) -> ReportWriteResult:
    """Write JSON and/or Markdown report files."""

    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    basename = _normalize_basename(basename)

    json_path: Path | None = None
    markdown_path: Path | None = None

    if write_json:
        json_path = report_dir / f"{basename}.json"
        write_json_report(report, json_path)

    if write_markdown:
        markdown_path = report_dir / f"{basename}.md"
        write_markdown_report(report, markdown_path, max_issues=max_issues)

    return ReportWriteResult(json_path=json_path, markdown_path=markdown_path)


def write_json_report(report: Mapping[str, Any], path: Path | str) -> Path:
    """Write report payload as JSON."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=JSON_ENCODING) as handle:
        json.dump(report, handle, indent=JSON_INDENT, ensure_ascii=False)
        handle.write("\n")
    return path


def write_markdown_report(
    report: Mapping[str, Any],
    path: Path | str,
    *,
    max_issues: int = DEFAULT_MAX_ISSUES,
) -> Path:
    """Write report payload as Markdown."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_markdown_report(report, max_issues=max_issues), encoding=JSON_ENCODING)
    return path


def load_report_json(path: Path | str) -> dict[str, Any]:
    """Load an existing JSON report for Markdown/console rendering."""

    path = Path(path)
    with path.open("r", encoding=JSON_ENCODING) as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Validation report JSON must contain an object at the root.")
    return data


# ---------------------------------------------------------------------------
# CLI: render an existing JSON report; does not run validation.
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    report = load_report_json(args.from_json)

    if args.print:
        print_report(report, max_issues=args.max_issues)

    if args.markdown_out:
        write_markdown_report(report, args.markdown_out, max_issues=args.max_issues)

    if args.json_out:
        write_json_report(report, args.json_out)

    return 0


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render an existing validation JSON report as Markdown or compact console text. "
            "This command does not run validation."
        ),
    )
    parser.add_argument(
        "--from-json",
        type=Path,
        required=True,
        help="Existing validation report JSON to render.",
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=None,
        help="Optional Markdown output path.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional normalized JSON output path.",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print compact console summary.",
    )
    parser.add_argument(
        "--max-issues",
        type=int,
        default=DEFAULT_MAX_ISSUES,
        help="Maximum issue rows to include in Markdown/console details.",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_issues(summary: ValidationSummary | Mapping[str, Any]) -> list[dict[str, Any]]:
    if isinstance(summary, ValidationSummary):
        return [issue.as_dict() for issue in summary.issues]

    if not isinstance(summary, Mapping):
        raise TypeError("summary must be a ValidationSummary or mapping payload.")

    # Accept the full validate.py report payload or summary.as_dict() shape.
    if "summary" in summary and isinstance(summary.get("summary"), Mapping):
        return _extract_issues(summary["summary"])

    raw_issues = summary.get("issues", []) or []
    return [_issue_to_dict(issue) for issue in raw_issues]


def _issue_to_dict(issue: Any) -> dict[str, Any]:
    if isinstance(issue, ValidationIssue):
        return issue.as_dict()
    if isinstance(issue, Mapping):
        return {
            "rule_id": str(issue.get("rule_id", "UNKNOWN")),
            "severity": str(issue.get("severity", INFO)),
            "patient_id": str(issue.get("patient_id", "UNKNOWN")),
            "path": str(issue.get("path", "")),
            "message": str(issue.get("message", "")),
            "context": dict(issue.get("context", {}) or {}),
        }
    raise TypeError(f"Unsupported issue type: {type(issue).__name__}")


def _compact_issue(issue: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "severity": issue.get("severity", INFO),
        "patient_id": issue.get("patient_id", "UNKNOWN"),
        "path": issue.get("path", ""),
        "message": issue.get("message", ""),
    }


def _severity_counts(issues: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {FAIL: 0, WARN: 0, INFO: 0, REPORT: 0}
    for issue in issues:
        severity = str(issue.get("severity") or INFO)
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _summary(report: Mapping[str, Any]) -> Mapping[str, Any]:
    summary = report.get("summary")
    if isinstance(summary, Mapping):
        return summary
    return {"fail_count": 0, "warn_count": 0, "info_count": 0, "issue_count": 0, "issues": []}


def _format_rule_table(report: Mapping[str, Any]) -> list[str]:
    issues_by_rule = report.get("issues_by_rule") or {}
    if not issues_by_rule:
        return ["## Issues by Rule", "", "No rule-level issues found.", ""]

    lines = [
        "## Issues by Rule",
        "",
        "| Rule | Total | FAIL | WARN | INFO | REPORT |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for rule_id in sorted(issues_by_rule):
        row = issues_by_rule[rule_id]
        lines.append(
            f"| {rule_id} | {row.get('total', 0)} | {row.get(FAIL, 0)} | "
            f"{row.get(WARN, 0)} | {row.get(INFO, 0)} | {row.get(REPORT, 0)} |"
        )
    lines.append("")
    return lines


def _format_patient_table(report: Mapping[str, Any]) -> list[str]:
    issues_by_patient = report.get("issues_by_patient") or {}
    if not issues_by_patient:
        return ["## Issues by Patient", "", "No patient-level issues found.", ""]

    lines = [
        "## Issues by Patient",
        "",
        "| Patient | Total | FAIL | WARN | INFO | REPORT | Rules |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for patient_id in sorted(issues_by_patient):
        row = issues_by_patient[patient_id]
        rules = row.get("rules", {}) or {}
        rule_text = ", ".join(f"{rule}×{count}" for rule, count in sorted(rules.items()))
        lines.append(
            f"| {patient_id} | {row.get('total', 0)} | {row.get(FAIL, 0)} | "
            f"{row.get(WARN, 0)} | {row.get(INFO, 0)} | {row.get(REPORT, 0)} | {rule_text} |"
        )
    lines.append("")
    return lines


def _format_v12_section(report: Mapping[str, Any]) -> list[str]:
    v12 = report.get("v12_diversity_report") or {}
    lines = [
        "## V12 Diversity Report",
        "",
        f"**Status:** {v12.get('status', 'UNKNOWN')}",
        f"**Issues:** {v12.get('issue_count', 0)} total, {v12.get('fail_count', 0)} FAIL, {v12.get('warn_count', 0)} WARN",
        "",
    ]

    issues = list(v12.get("issues", []) or [])
    if issues:
        lines.extend(["| Severity | Patient | Path | Message |", "|---|---|---|---|"])
        for issue in issues:
            lines.append(
                f"| {issue.get('severity')} | {issue.get('patient_id')} | "
                f"`{issue.get('path', '')}` | {_escape_markdown_cell(issue.get('message', ''))} |"
            )
        lines.append("")
    return lines


def _format_v13_section(report: Mapping[str, Any]) -> list[str]:
    v13 = report.get("v13_similarity_report") or {}
    lines = ["## V13 Embedding Similarity Report", ""]

    if not v13.get("available"):
        lines.extend([
            "V13 was not run for this report. This is expected before SOAP/chunk dry-run.",
            "",
        ])
        return lines

    lines.extend([
        f"**Status:** {v13.get('status', 'UNKNOWN')}",
        f"**Model:** {v13.get('model') or 'unknown'}",
        f"**Chunks checked:** {v13.get('chunks_checked') or 'unknown'}",
        f"**Critical near-duplicates:** {v13.get('critical_count', 0)}",
        f"**Warnings:** {v13.get('warning_count', 0)}",
        "",
    ])

    for label, key in (("Critical", "critical"), ("Warnings", "warnings")):
        records = list(v13.get(key, []) or [])
        if records:
            lines.extend([f"### {label}", "", "| Similarity | Chunk A | Chunk B | Patients | Source type |", "|---:|---|---|---|---|"])
            for record in records:
                patients = f"{record.get('patient_a', '')} / {record.get('patient_b', '')}"
                lines.append(
                    f"| {record.get('similarity', '')} | `{record.get('chunk_a', '')}` | "
                    f"`{record.get('chunk_b', '')}` | {patients} | {record.get('source_type', '')} |"
                )
            lines.append("")

    return lines


def _format_approval_section(report: Mapping[str, Any]) -> list[str]:
    gate = report.get("approval_gate") or {}
    return [
        "## Approval Gate",
        "",
        "| Step | Allowed? |",
        "|---|---:|",
        f"| Generate SOAP | {_yes_no(gate.get('can_generate_soap'))} |",
        f"| Run ingestion | {_yes_no(gate.get('can_run_ingestion'))} |",
        f"| Handoff to RAG | {_yes_no(gate.get('can_handoff_to_rag'))} |",
        f"| Requires manual V13 review | {_yes_no(gate.get('requires_manual_v13_review'))} |",
        "",
        f"**Reason:** {gate.get('reason', '')}",
        "",
    ]


def _format_issue_details(issues: Iterable[Mapping[str, Any]], *, max_issues: int) -> list[str]:
    issues = list(issues)
    lines = ["## Issue Details", ""]
    if not issues:
        lines.extend(["No validation issues found.", ""])
        return lines

    shown = issues[:max_issues]
    lines.extend(["| Severity | Rule | Patient | Path | Message |", "|---|---|---|---|---|"])
    for issue in shown:
        lines.append(
            f"| {issue.get('severity', '')} | {issue.get('rule_id', '')} | {issue.get('patient_id', '')} | "
            f"`{issue.get('path', '')}` | {_escape_markdown_cell(issue.get('message', ''))} |"
        )
    lines.append("")
    if len(issues) > max_issues:
        lines.extend([f"_Only the first {max_issues} of {len(issues)} issues are shown._", ""])
    return lines


def _approval_reason(*, passed: bool, v13_critical_count: int) -> str:
    if not passed:
        return "Blocking FAIL issues exist. Do not generate SOAP, ingest, or hand off to RAG."
    if v13_critical_count > 0:
        return "V1-V12 passed, but V13 critical near-duplicates require manual review before RAG handoff."
    return "Zero FAIL issues. Dataset is eligible for the next configured pipeline step."


def _normalize_basename(basename: str | None) -> str:
    if basename:
        normalized = basename.strip().removesuffix(".json").removesuffix(".md")
        return normalized or _timestamped_basename()
    return _timestamped_basename()


def _timestamped_basename() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"validation_report_{timestamp}"


def _yes_no(value: Any) -> str:
    return "YES" if bool(value) else "NO"


def _escape_markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


__all__ = [
    "DEFAULT_REPORT_DIR",
    "DEFAULT_MAX_ISSUES",
    "ReportWriteResult",
    "build_validation_report",
    "build_report_payload",
    "build_approval_gate",
    "build_v12_diversity_report",
    "build_v13_similarity_report",
    "group_issues_by_rule",
    "group_issues_by_patient",
    "format_markdown_report",
    "format_console_report",
    "print_report",
    "write_report_files",
    "write_json_report",
    "write_markdown_report",
    "load_report_json",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
