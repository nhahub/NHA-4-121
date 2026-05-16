"""
scripts/validate_all.py

Validate all generated patient JSON files.

Run from project root:

    python scripts/validate_all.py
    python scripts/validate_all.py --quarantine
    python scripts/validate_all.py --mode pilot
    python scripts/validate_all.py --mode full
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.constants import (  # noqa: E402
    DATASET_MODE_FULL,
    DATASET_MODE_PILOT,
    DEFAULT_DATASET_MODE,
    EXPECTED_FULL_PATIENT_COUNT,
    EXPECTED_PILOT_PATIENT_COUNT,
)
from config.paths import PATIENTS_DIR, ensure_project_directories  # noqa: E402
from validators.validate import validate_patient_files  # noqa: E402
from validators.validation_report import print_validation_report  # noqa: E402


def _expected_patient_count_for_mode(mode: str) -> int:
    """
    Return the expected patient count for the selected dataset mode.
    """
    if mode == DATASET_MODE_PILOT:
        return EXPECTED_PILOT_PATIENT_COUNT

    if mode == DATASET_MODE_FULL:
        return EXPECTED_FULL_PATIENT_COUNT

    raise ValueError(f"Unsupported dataset mode: {mode}")


def main() -> int:
    """
    Validate generated patient JSON files and enforce expected dataset size.
    """
    parser = argparse.ArgumentParser(
        description="Validate all patient records."
    )

    parser.add_argument(
        "--quarantine",
        action="store_true",
        help="Copy invalid files and issue reports to data/quarantine/.",
    )

    parser.add_argument(
        "--mode",
        choices=(DATASET_MODE_PILOT, DATASET_MODE_FULL),
        default=DEFAULT_DATASET_MODE,
        help="Expected dataset mode. Defaults to configured default mode.",
    )

    args = parser.parse_args()

    ensure_project_directories()

    report = validate_patient_files(
        directory=PATIENTS_DIR,
        quarantine_invalid=args.quarantine,
        write_report=True,
    )

    print_validation_report(report)

    expected_count = _expected_patient_count_for_mode(args.mode)

    if report.patients_checked != expected_count:
        print(
            "\nERROR: Patient count mismatch. "
            f"Expected {expected_count} patients for mode='{args.mode}', "
            f"but validated {report.patients_checked}.",
            file=sys.stderr,
        )
        return 1

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())