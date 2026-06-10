"""
scripts/validate_all.py

CLI orchestration command for validating the generated v1.7 Lite patient
JSON dataset.

This script is intentionally thin:
- it loads no business rules of its own,
- it delegates V1-V12 validation to validators.validate / validators.rules,
- it delegates JSON/Markdown report formatting to validators.validation_report,
- it exits with a non-zero status when blocking validation fails.

It must not mutate patient files, generate patient records, generate SOAP notes,
create chunks, call ChromaDB, or call any LLM/API.

Mode support
------------
--mode v17_lite  Validate against data/patients/  (default)
--mode full      Validate against data/patients/  (same directory as v17_lite)
--mode pilot     Validate against data/patients/  (pilot subset written there)

Use --patients-dir to override the directory explicitly.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


# Support both execution styles:
#   python scripts/validate_all.py
#   python -m scripts.validate_all
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.constants import (  # noqa: E402
    DATASET_MODE_FULL,
    DATASET_MODE_PILOT,
    DATASET_MODE_V17_LITE,
    DATASET_VERSION,
    DEFAULT_DATASET_MODE,
    EXPECTED_V17_LITE_PATIENT_COUNT,
    PROJECT_NAME,
)
from validators.validate import (  # noqa: E402
    DEFAULT_PATIENTS_DIR,
    DEFAULT_REPORT_DIR,
    ValidationRunResult,
    validate_patient_files,
)
from validators.validation_report import (  # noqa: E402
    build_validation_report,
    format_console_report,
    write_report_files,
)


DEFAULT_REPORT_BASENAME_PREFIX = "validation_report"

# Supported modes for the CLI.
_SUPPORTED_MODES: tuple[str, ...] = (
    DATASET_MODE_V17_LITE,
    DATASET_MODE_FULL,
    DATASET_MODE_PILOT,
)

# Maps each mode to its default patients directory.
# All current modes share data/patients/ because generate_all.py writes
# every mode to the same location by default.  Override with --patients-dir
# if a separate directory is used for a specific mode.
_MODE_PATIENTS_DIR: dict[str, Path] = {
    DATASET_MODE_V17_LITE: DEFAULT_PATIENTS_DIR,
    DATASET_MODE_FULL:     DEFAULT_PATIENTS_DIR,
    DATASET_MODE_PILOT:    DEFAULT_PATIENTS_DIR,
}


# ---------------------------------------------------------------------------
# Public workflow
# ---------------------------------------------------------------------------


def run_validate_all(
    *,
    mode: str = DEFAULT_DATASET_MODE,
    patients_dir: Path = DEFAULT_PATIENTS_DIR,
    report_dir: Path = DEFAULT_REPORT_DIR,
    strict_diversity: bool = True,
    write_json: bool = True,
    write_markdown: bool = True,
    report_basename: str | None = None,
    max_issues: int = 40,
    fail_on_warn: bool = False,
    print_summary: bool = True,
) -> int:
    """Run the full dataset validation command.

    Supports the new PatientBlueprint-based pipeline.  No dict-style blueprint
    access or old mapping assumptions are made here — validation operates
    entirely on the generated patient JSON files.

    V7, V11, and V12 execute as part of run_all_rules() inside
    validators.validate.validate_patient_files.

    Args:
        mode:            Dataset mode string — used for logging only; the actual
                         directory is determined by patients_dir.
        patients_dir:    Directory containing approved/generated PAT-*.json
                         files, or a single patient JSON file.
        report_dir:      Directory for validation report outputs.
        strict_diversity: True before final ingestion. False is allowed only
                         during active development to downgrade selected V12
                         diversity issues.
        write_json:      Write a JSON report.
        write_markdown:  Write a Markdown report.
        report_basename: Optional report filename basename without extension.
        max_issues:      Maximum issue details shown in console/Markdown.
        fail_on_warn:    Return a failing exit code when WARN issues exist.
        print_summary:   Print compact console report.

    Returns:
        Process exit code. 0 means approved for the next pipeline step.
    """
    if print_summary:
        print(f"  [validate_all] mode={mode!r}  patients_dir={patients_dir}")

    validation_result = validate_patient_files(
        patients_path=patients_dir,
        report_dir=report_dir,
        strict_diversity=strict_diversity,
        write_report=False,
    )

    report_payload = build_validation_report(
        summary=validation_result.summary,
        patients_path=validation_result.patients_dir,
        files_checked=validation_result.files_checked,
        patient_ids=validation_result.patient_ids,
        strict_diversity=strict_diversity,
        extra_context={
            "script":                "scripts/validate_all.py",
            "project_root":          str(_PROJECT_ROOT),
            "mode":                  mode,
            "expected_patient_count": EXPECTED_V17_LITE_PATIENT_COUNT,
            "fail_on_warn":          fail_on_warn,
        },
    )

    report_paths = None
    if write_json or write_markdown:
        report_paths = write_report_files(
            report_payload,
            report_dir=report_dir,
            basename=report_basename or _timestamped_report_basename(),
            write_json=write_json,
            write_markdown=write_markdown,
            max_issues=max_issues,
        )

        if report_paths.json_path is not None:
            report_payload["report_json_path"] = str(report_paths.json_path)
        if report_paths.markdown_path is not None:
            report_payload["report_markdown_path"] = str(report_paths.markdown_path)

    if print_summary:
        print(format_console_report(report_payload, max_issues=max_issues))
        if report_paths is not None and report_paths.created_paths:
            print("Reports written:")
            for path in report_paths.created_paths:
                print(f"  - {path}")

    return _exit_code(validation_result, fail_on_warn=fail_on_warn)


# Backward-compatible aliases for tests or future shell wrappers.
main_validate_all = run_validate_all
validate_all = run_validate_all


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    # Resolve the patients directory:
    # 1. If --patients-dir was given explicitly, use it.
    # 2. Otherwise resolve from --mode via _MODE_PATIENTS_DIR.
    if args.patients_dir != DEFAULT_PATIENTS_DIR:
        # Explicit override — honour it regardless of mode.
        patients_dir = args.patients_dir
    else:
        # Use the mode-specific default (currently all map to DEFAULT_PATIENTS_DIR).
        patients_dir = _MODE_PATIENTS_DIR.get(args.mode, DEFAULT_PATIENTS_DIR)

    write_json, write_markdown = _resolve_report_outputs(args)

    return run_validate_all(
        mode=args.mode,
        patients_dir=patients_dir,
        report_dir=args.report_dir,
        strict_diversity=not args.development,
        write_json=write_json,
        write_markdown=write_markdown,
        report_basename=args.report_basename,
        max_issues=args.max_issues,
        fail_on_warn=args.fail_on_warn,
        print_summary=not args.quiet,
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run V1-V12 validation for the v1.7 Lite synthetic patient dataset. "
            "Compatible with the PatientBlueprint dataclass pipeline. "
            "This command is an approval gate before SOAP generation, ingestion, "
            "and RAG handoff."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=list(_SUPPORTED_MODES),
        default=DEFAULT_DATASET_MODE,
        help=(
            f"Dataset mode to validate.  Determines which patients directory is "
            f"used when --patients-dir is not specified.  "
            f"Default: {DEFAULT_DATASET_MODE!r}.  "
            f"Choices: {', '.join(_SUPPORTED_MODES)}."
        ),
    )
    parser.add_argument(
        "--patients-dir",
        type=Path,
        default=DEFAULT_PATIENTS_DIR,
        help=(
            "Directory containing PAT-*.json files, or one patient JSON file. "
            "When omitted, the directory is resolved from --mode."
        ),
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="Directory where validation reports are written.",
    )
    parser.add_argument(
        "--report-basename",
        type=str,
        default=None,
        help=(
            "Optional report basename without extension. "
            "Timestamped name is used by default."
        ),
    )
    parser.add_argument(
        "--report-format",
        choices=("both", "json", "markdown", "none"),
        default="both",
        help="Report output format. Default: both JSON and Markdown.",
    )
    parser.add_argument(
        "--development",
        action="store_true",
        help=(
            "Development mode: pass strict_diversity=False so selected V12 diversity "
            "issues may be downgraded during active iteration. "
            "Do not use for final handoff."
        ),
    )
    parser.add_argument(
        "--fail-on-warn",
        action="store_true",
        help=(
            "Return non-zero if WARN issues exist, "
            "useful for stricter pre-handoff checks."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console summary. Exit code still reflects validation status.",
    )
    parser.add_argument(
        "--max-issues",
        type=int,
        default=40,
        help=(
            "Maximum number of issues to show in console and Markdown detail sections."
        ),
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_report_outputs(args: argparse.Namespace) -> tuple[bool, bool]:
    if args.report_format == "none":
        return False, False
    if args.report_format == "json":
        return True, False
    if args.report_format == "markdown":
        return False, True
    return True, True


def _timestamped_report_basename() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{DEFAULT_REPORT_BASENAME_PREFIX}_{timestamp}"


def _exit_code(result: ValidationRunResult, *, fail_on_warn: bool = False) -> int:
    if not result.passed:
        return 1
    if fail_on_warn and result.summary.warn_count > 0:
        return 1
    return 0


__all__ = [
    "DEFAULT_REPORT_BASENAME_PREFIX",
    "run_validate_all",
    "main_validate_all",
    "validate_all",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
