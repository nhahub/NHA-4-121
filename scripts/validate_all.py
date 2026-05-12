"""
scripts/validate_all.py

Validate all generated patient JSON files.

Run from project root:

    python scripts/validate_all.py
    python scripts/validate_all.py --quarantine
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.paths import PATIENTS_DIR, ensure_project_directories  # noqa: E402
from validators.validate import validate_patient_files  # noqa: E402
from validators.validation_report import print_validation_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate all patient records.")
    parser.add_argument(
        "--quarantine",
        action="store_true",
        help="Copy invalid files and issue reports to data/quarantine/.",
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=PATIENTS_DIR,
        help="Directory containing PAT-*.json files.",
    )
    args = parser.parse_args()

    ensure_project_directories()

    report = validate_patient_files(
        directory=args.directory,
        quarantine_invalid=args.quarantine,
        write_report=True,
    )

    print_validation_report(report)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())