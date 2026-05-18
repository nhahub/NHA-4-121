"""
scripts/validate_all.py

Validate all generated patient JSON files.

Run from project root:

    python scripts/validate_all.py
    python scripts/validate_all.py --quarantine
    python scripts/validate_all.py --mode pilot
    python scripts/validate_all.py --mode full

This script keeps V1-V11 validation inside validators/ and adds only
small dataset-level checks that belong to the command-line workflow:

- expected patient count for the selected mode
- expected tier distribution for the selected mode
- duplicate patient_id detection across files
- CKD patient count limit
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
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
    PILOT_PATIENT_DISTRIBUTION,
)
from config.paths import PATIENTS_DIR, ensure_project_directories  # noqa: E402
from validators.validate import load_patient_files, validate_patient_files  # noqa: E402
from validators.validation_report import print_validation_report  # noqa: E402


_MAX_CKD_PATIENTS = 2


def _expected_patient_count_for_mode(mode: str) -> int:
    """
    Return the expected patient count for the selected dataset mode.
    """
    if mode == DATASET_MODE_PILOT:
        return EXPECTED_PILOT_PATIENT_COUNT

    if mode == DATASET_MODE_FULL:
        return EXPECTED_FULL_PATIENT_COUNT

    raise ValueError(f"Unsupported dataset mode: {mode}")


def _expected_distribution_for_mode(mode: str) -> dict[str, int]:
    """
    Return the expected tier distribution for the selected dataset mode.
    """
    if mode == DATASET_MODE_PILOT:
        return dict(PILOT_PATIENT_DISTRIBUTION)

    if mode == DATASET_MODE_FULL:
        return dict(FINAL_PATIENT_DISTRIBUTION)

    raise ValueError(f"Unsupported dataset mode: {mode}")


def _load_patients_for_dataset_checks(directory: Path) -> list[dict[str, Any]]:
    """
    Load patient records using the same tolerant loader as validators.validate.

    Malformed JSON files are represented as minimal records with _load_error,
    which allows dataset checks to report count/distribution problems without
    crashing the script.
    """
    return [patient for _, patient in load_patient_files(directory)]


def _dataset_count_issues(
    *,
    patients_checked: int,
    mode: str,
) -> list[str]:
    """
    Validate expected patient count for the selected mode.
    """
    expected_count = _expected_patient_count_for_mode(mode)

    if patients_checked == expected_count:
        return []

    return [
        "Patient count mismatch. "
        f"Expected {expected_count} patients for mode='{mode}', "
        f"but validated {patients_checked}."
    ]


def _dataset_distribution_issues(
    *,
    patients: list[dict[str, Any]],
    mode: str,
) -> list[str]:
    """
    Validate tier distribution across all loaded patient records.
    """
    expected_distribution = _expected_distribution_for_mode(mode)
    actual_counter: Counter[str] = Counter()

    for patient in patients:
        metadata = patient.get("metadata", {})
        tier = metadata.get("tier") if isinstance(metadata, dict) else None
        actual_counter[str(tier)] += 1

    actual_distribution = {
        tier: actual_counter.get(tier, 0)
        for tier in expected_distribution
    }

    unexpected_tiers = {
        tier: count
        for tier, count in actual_counter.items()
        if tier not in expected_distribution
    }

    issues: list[str] = []

    if actual_distribution != expected_distribution:
        issues.append(
            "Tier distribution mismatch. "
            f"Expected {expected_distribution}, got {actual_distribution}."
        )

    if unexpected_tiers:
        issues.append(
            "Unexpected tier values found in dataset: "
            f"{unexpected_tiers}."
        )

    return issues


def _dataset_patient_id_issues(patients: list[dict[str, Any]]) -> list[str]:
    """
    Validate patient_id uniqueness across the dataset.
    """
    patient_ids = [str(patient.get("patient_id", "<missing-patient-id>")) for patient in patients]
    counts = Counter(patient_ids)
    duplicates = sorted(
        patient_id
        for patient_id, count in counts.items()
        if count > 1
    )

    if not duplicates:
        return []

    return [f"Duplicate patient_id values found across dataset: {duplicates}."]


def _dataset_ckd_issues(patients: list[dict[str, Any]]) -> list[str]:
    """
    Validate the dataset-level CKD patient count limit.

    Per-patient CKD co-occurrence remains enforced by V7. This check only
    prevents accidentally expanding CKD beyond the locked dataset scope.
    """
    ckd_patient_ids: list[str] = []

    for patient in patients:
        conditions = patient.get("conditions", [])

        if not isinstance(conditions, list):
            continue

        if "CKD" in conditions:
            ckd_patient_ids.append(str(patient.get("patient_id", "<missing-patient-id>")))

    if len(ckd_patient_ids) <= _MAX_CKD_PATIENTS:
        return []

    return [
        "CKD patient count exceeds locked scope. "
        f"Maximum allowed is {_MAX_CKD_PATIENTS}, "
        f"found {len(ckd_patient_ids)}: {ckd_patient_ids}."
    ]


def run_dataset_level_checks(
    *,
    directory: Path,
    mode: str,
    patients_checked: int,
) -> list[str]:
    """
    Run dataset-level checks that are outside per-patient V1-V11 validation.
    """
    patients = _load_patients_for_dataset_checks(directory)

    issues: list[str] = []
    issues.extend(_dataset_count_issues(patients_checked=patients_checked, mode=mode))
    issues.extend(_dataset_distribution_issues(patients=patients, mode=mode))
    issues.extend(_dataset_patient_id_issues(patients))
    issues.extend(_dataset_ckd_issues(patients))

    return issues


def print_dataset_level_report(issues: list[str]) -> None:
    """
    Print dataset-level check results.
    """
    print("\n=== DATASET-LEVEL CHECKS ===")

    if not issues:
        print("Status: PASS")
        return

    print("Status: FAIL")

    for issue in issues:
        print(f"ERROR: {issue}")


def main() -> int:
    """
    Validate generated patient JSON files and enforce dataset-level checks.
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

    dataset_issues = run_dataset_level_checks(
        directory=PATIENTS_DIR,
        mode=args.mode,
        patients_checked=report.patients_checked,
    )
    print_dataset_level_report(dataset_issues)

    if dataset_issues:
        return 1

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
