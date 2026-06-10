"""
scripts/generate_all.py

Deterministic v1.7 Lite dataset generation entry point.

This script is orchestration only:
- load the curated v1.7 Lite blueprints via the PatientBlueprint dataclass API,
- call the full 5-stage generation pipeline,
- write the generated patient JSON files to data/patients,
- optionally quarantine failed generation outputs,
- print a compact generation summary.

Pipeline order (required):
    Stage 1 — generate_patients()                     patient shells
    Stage 2 — generate_visits_for_patient()           visit timelines
    Stage 3 — generate_medications_for_patient()      visit medications
    Stage 4 — generate_labs_for_patient()             visit labs
    Stage 5 — generate_allergy_registry_for_patient() allergy records

It must not contain clinical generation rules, SOAP generation logic,
validation business rules, chunking, metadata construction, ChromaDB ingestion,
or LLM/API calls.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


# Allow both execution styles:
#   python scripts/generate_all.py
#   python -m scripts.generate_all
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
    FINAL_PATIENT_DISTRIBUTION,
    JSON_ENCODING,
    JSON_INDENT,
)
from config.patient_blueprints import (  # noqa: E402
    ALL_BLUEPRINTS,
    BLUEPRINT_BY_ID,
    PILOT_BLUEPRINTS,
    PatientBlueprint,
)
from generators.patient_generator import (  # noqa: E402
    PatientGenerationError,
    generate_patients,
)
from generators.visit_generator import (  # noqa: E402
    generate_visits_for_patient,
)
from generators.medication_generator import (  # noqa: E402
    generate_medications_for_patient,
)
from generators.lab_generator import (  # noqa: E402
    generate_labs_for_patient,
)
from generators.allergy_generator import (  # noqa: E402
    generate_allergy_registry_for_patient,
)


DEFAULT_PATIENTS_DIR = _PROJECT_ROOT / "data" / "patients"
DEFAULT_QUARANTINE_DIR = _PROJECT_ROOT / "data" / "quarantine"
DEFAULT_LOG_DIR = _PROJECT_ROOT / "logs"

# Supported dataset modes for the CLI.
_SUPPORTED_MODES: tuple[str, ...] = (
    DATASET_MODE_V17_LITE,
    DATASET_MODE_FULL,
    DATASET_MODE_PILOT,
)


@dataclass(frozen=True)
class GenerationSummary:
    """Small immutable summary returned by the generation workflow."""

    mode: str
    generated_count: int
    written_count: int
    output_dir: Path
    quarantine_dir: Path
    dry_run: bool
    dataset_version: str
    tier_counts: dict[str, int]
    visit_count: int
    patient_ids: list[str]


class GenerateAllError(RuntimeError):
    """Raised when the generation script cannot complete safely."""


# ---------------------------------------------------------------------------
# Public workflow
# ---------------------------------------------------------------------------


def generate_dataset(
    *,
    mode: str = DEFAULT_DATASET_MODE,
    output_dir: Path = DEFAULT_PATIENTS_DIR,
    quarantine_dir: Path = DEFAULT_QUARANTINE_DIR,
    clean_output: bool = True,
    dry_run: bool = False,
    write_summary_log: bool = True,
) -> GenerationSummary:
    """Generate the full patient dataset for the specified mode.

    Runs a deterministic 5-stage pipeline using PatientBlueprint dataclasses:
        1. generate_patients()                     — patient shells
        2. generate_visits_for_patient()           — visit timelines (in-place)
        3. generate_medications_for_patient()      — medications (in-place)
        4. generate_labs_for_patient()             — lab results (in-place)
        5. generate_allergy_registry_for_patient() — allergy records (in-place)

    Args:
        mode: Dataset mode.  One of: v17_lite, full, pilot.
        output_dir: Directory that will receive approved generated patient JSON.
        quarantine_dir: Directory used to store generation failure details.
        clean_output: When True, remove old PAT-*.json files from output_dir
            before writing.  Prevents stale files from previous runs remaining
            alongside the new dataset.
        dry_run: Generate and validate patients without writing JSON files.
        write_summary_log: Append a compact log line to logs/pipeline_run.log.

    Returns:
        GenerationSummary describing the generated dataset.

    Raises:
        GenerateAllError: if any pipeline stage or file write fails.
    """
    if mode not in _SUPPORTED_MODES:
        raise GenerateAllError(
            f"Unsupported mode '{mode}'. Expected one of: {_SUPPORTED_MODES}"
        )

    output_dir = output_dir.resolve()
    quarantine_dir = quarantine_dir.resolve()

    try:
        patients = _run_full_pipeline(mode)
        _validate_generated_collection(patients, mode)
    except Exception as exc:  # noqa: BLE001
        _write_generation_failure(quarantine_dir, exc, mode=mode)
        raise GenerateAllError(f"Dataset generation failed: {exc}") from exc

    summary = _build_summary(
        patients,
        mode=mode,
        output_dir=output_dir,
        quarantine_dir=quarantine_dir,
        dry_run=dry_run,
    )

    if not dry_run:
        _prepare_output_dir(output_dir, clean_output=clean_output)
        _write_patient_files(patients, output_dir)

    if write_summary_log:
        _append_pipeline_log(summary)

    return summary


# ---------------------------------------------------------------------------
# Generation pipeline
# ---------------------------------------------------------------------------


def _run_full_pipeline(mode: str) -> list[dict[str, Any]]:
    """Execute all 5 generation stages and return the fully built patient list.

    Each stage operates in-place on the patient dicts produced by Stage 1.
    BLUEPRINT_BY_ID is used for O(1) blueprint lookup per patient.

    Args:
        mode: Dataset mode string — passed to generate_patients().

    Returns:
        Fully populated patient dicts (visits, medications, labs, allergies).

    Raises:
        PatientGenerationError: if any generator stage fails.
    """
    # ------------------------------------------------------------------
    # Stage 1: Patient shells
    # generate_patients() validates blueprints and returns patient dicts
    # with empty visits=[] and allergy_registry=[].
    # ------------------------------------------------------------------
    _log_stage(1, "Generating patient shells", extra=f"mode={mode!r}")
    patients = generate_patients(mode=mode)
    _log_stage_done(1, f"{len(patients)} patient shell(s) created.")

    # ------------------------------------------------------------------
    # Stage 2: Visit timelines
    # generate_visits_for_patient() mutates patient["visits"] in-place.
    # ------------------------------------------------------------------
    _log_stage(2, "Generating visit timelines")
    for patient in patients:
        pid = patient["patient_id"]
        blueprint = BLUEPRINT_BY_ID[pid]
        generate_visits_for_patient(patient, blueprint)
    total_visits = sum(len(p["visits"]) for p in patients)
    _log_stage_done(2, f"{total_visits} visit(s) generated across {len(patients)} patient(s).")

    # ------------------------------------------------------------------
    # Stage 3: Medications
    # generate_medications_for_patient() fills visit["medications"] lists.
    # start_date continuity is tracked across visits internally.
    # ------------------------------------------------------------------
    _log_stage(3, "Generating medications")
    for patient in patients:
        pid = patient["patient_id"]
        blueprint = BLUEPRINT_BY_ID[pid]
        generate_medications_for_patient(patient, blueprint)
    _log_stage_done(3, "Medication records populated for all patients.")

    # ------------------------------------------------------------------
    # Stage 4: Lab results
    # generate_labs_for_patient() fills visit["labs"] lists.
    # Patients with empty lab_focus receive empty lists (correct).
    # ------------------------------------------------------------------
    _log_stage(4, "Generating lab results")
    for patient in patients:
        pid = patient["patient_id"]
        blueprint = BLUEPRINT_BY_ID[pid]
        generate_labs_for_patient(patient, blueprint)
    _log_stage_done(4, "Lab results populated for all patients.")

    # ------------------------------------------------------------------
    # Stage 5: Allergy registries
    # generate_allergy_registry_for_patient() fills allergy_registry.
    # Patients with blueprint.allergen=None receive an empty list.
    # ------------------------------------------------------------------
    _log_stage(5, "Generating allergy registries")
    for patient in patients:
        pid = patient["patient_id"]
        blueprint = BLUEPRINT_BY_ID[pid]
        generate_allergy_registry_for_patient(patient, blueprint)
    _log_stage_done(5, "Allergy registries populated for all patients.")

    return patients


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""

    args = _parse_args(argv)
    clean = not args.no_clean  # --clean is the default; --no-clean disables it

    try:
        summary = generate_dataset(
            mode=args.mode,
            output_dir=args.output_dir,
            quarantine_dir=args.quarantine_dir,
            clean_output=clean,
            dry_run=args.dry_run,
            write_summary_log=not args.no_log,
        )
    except GenerateAllError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _print_summary(summary)
    return 0


# ---------------------------------------------------------------------------
# Validation and output helpers
# ---------------------------------------------------------------------------


def _validate_generated_collection(
    patients: Sequence[dict[str, Any]],
    mode: str,
) -> None:
    """Perform shallow script-level checks after all 5 pipeline stages.

    Full V1-V12 validation belongs to validators/rules.py and
    scripts/validate_all.py.  These checks only protect this script from
    writing an obviously incomplete or duplicated dataset.

    For v17_lite / full mode the count and tier distribution are verified.
    For pilot mode only uniqueness is checked (pilot has a smaller set).
    """
    patient_ids: set[str] = set()
    retrieval_signatures: set[str] = set()
    tier_counts: dict[str, int] = {tier: 0 for tier in FINAL_PATIENT_DISTRIBUTION}

    for patient in patients:
        patient_id = _require_str(patient, "patient_id")
        metadata = _require_dict(patient, "metadata")
        visits = _require_list(patient, "visits")

        if patient_id in patient_ids:
            raise GenerateAllError(f"Duplicate generated patient_id: {patient_id}")
        patient_ids.add(patient_id)

        if not visits:
            raise GenerateAllError(f"{patient_id}: generated with no visits.")

        dataset_version = metadata.get("dataset_version")
        if dataset_version != DATASET_VERSION:
            raise GenerateAllError(
                f"{patient_id}: dataset_version mismatch: "
                f"{dataset_version!r} != {DATASET_VERSION!r}"
            )

        tier = metadata.get("tier")
        if tier not in tier_counts:
            raise GenerateAllError(
                f"{patient_id}: invalid tier in metadata: {tier!r}"
            )
        tier_counts[str(tier)] += 1

        retrieval_signature = metadata.get("retrieval_signature")
        if not isinstance(retrieval_signature, str) or not retrieval_signature.strip():
            raise GenerateAllError(f"{patient_id}: missing retrieval_signature.")
        if retrieval_signature in retrieval_signatures:
            raise GenerateAllError(
                f"Duplicate retrieval_signature: {retrieval_signature}"
            )
        retrieval_signatures.add(retrieval_signature)

        _validate_visit_linkage(patient_id, visits)
        _validate_visit_medications_and_labs(patient_id, visits)
        _validate_allergy_registry(patient_id, patient)

    # Count / tier checks only apply to the full 15-patient modes.
    if mode in (DATASET_MODE_V17_LITE, DATASET_MODE_FULL):
        if len(patients) != EXPECTED_V17_LITE_PATIENT_COUNT:
            raise GenerateAllError(
                f"Expected {EXPECTED_V17_LITE_PATIENT_COUNT} patients "
                f"for mode '{mode}', got {len(patients)}."
            )
        if tier_counts != FINAL_PATIENT_DISTRIBUTION:
            raise GenerateAllError(
                f"Tier distribution mismatch for mode '{mode}'. "
                f"Expected {FINAL_PATIENT_DISTRIBUTION}, got {tier_counts}."
            )


def _validate_visit_linkage(patient_id: str, visits: Sequence[Any]) -> None:
    """Check visit IDs and prior_visit_id chaining."""
    previous_visit_id: str | None = None
    seen_visit_ids: set[str] = set()

    for index, raw_visit in enumerate(visits, start=1):
        if not isinstance(raw_visit, dict):
            raise GenerateAllError(
                f"{patient_id}: visit {index} is not an object."
            )

        visit_id = _require_str(
            raw_visit, "visit_id", context=f"{patient_id}.visits[{index}]"
        )
        prior_visit_id = raw_visit.get("prior_visit_id")

        if visit_id in seen_visit_ids:
            raise GenerateAllError(
                f"{patient_id}: duplicate visit_id: {visit_id}"
            )
        seen_visit_ids.add(visit_id)

        if index == 1 and prior_visit_id is not None:
            raise GenerateAllError(
                f"{patient_id}: first visit prior_visit_id must be null."
            )
        if index > 1 and prior_visit_id != previous_visit_id:
            raise GenerateAllError(
                f"{patient_id} visit {visit_id} prior_visit_id mismatch: "
                f"expected {previous_visit_id!r}, got {prior_visit_id!r}."
            )

        previous_visit_id = visit_id


def _validate_visit_medications_and_labs(
    patient_id: str, visits: Sequence[Any]
) -> None:
    """Verify that every visit has lists (even if empty) for medications and labs."""
    for index, visit in enumerate(visits, start=1):
        if not isinstance(visit.get("medications"), list):
            raise GenerateAllError(
                f"{patient_id} visit {index}: 'medications' must be a list "
                "(Stage 3 medication generation may have failed)."
            )
        if not isinstance(visit.get("labs"), list):
            raise GenerateAllError(
                f"{patient_id} visit {index}: 'labs' must be a list "
                "(Stage 4 lab generation may have failed)."
            )


def _validate_allergy_registry(patient_id: str, patient: dict[str, Any]) -> None:
    """Verify allergy_registry is a list (Stage 5 check)."""
    if not isinstance(patient.get("allergy_registry"), list):
        raise GenerateAllError(
            f"{patient_id}: 'allergy_registry' must be a list "
            "(Stage 5 allergy generation may have failed)."
        )


def _prepare_output_dir(output_dir: Path, *, clean_output: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    if not clean_output:
        return

    removed = 0
    for old_file in output_dir.glob("PAT-*.json"):
        if old_file.is_file():
            old_file.unlink()
            removed += 1
    if removed:
        print(f"  [clean] Removed {removed} existing PAT-*.json file(s) from {output_dir}")


def _write_patient_files(
    patients: Sequence[dict[str, Any]], output_dir: Path
) -> None:
    for patient in patients:
        patient_id = str(patient["patient_id"])
        output_path = output_dir / f"{patient_id}.json"
        _atomic_write_json(output_path, patient)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")

    with temp_path.open("w", encoding=JSON_ENCODING) as file:
        json.dump(payload, file, indent=JSON_INDENT, ensure_ascii=False)
        file.write("\n")

    temp_path.replace(path)


def _write_generation_failure(
    quarantine_dir: Path,
    exc: BaseException,
    *,
    mode: str = DEFAULT_DATASET_MODE,
) -> None:
    """Store a small failure report without pretending the dataset is valid."""
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _utc_timestamp_for_filename()
    report_path = quarantine_dir / f"generation_failure_{timestamp}.json"
    payload: dict[str, Any] = {
        "timestamp_utc": _utc_timestamp_iso(),
        "dataset_version": DATASET_VERSION,
        "mode": mode,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "note": "Generation failed before approved patient JSON files were written.",
    }
    _atomic_write_json(report_path, payload)


def _build_summary(
    patients: Sequence[dict[str, Any]],
    *,
    mode: str,
    output_dir: Path,
    quarantine_dir: Path,
    dry_run: bool,
) -> GenerationSummary:
    tier_counts: dict[str, int] = {tier: 0 for tier in FINAL_PATIENT_DISTRIBUTION}
    visit_count = 0
    patient_ids: list[str] = []

    for patient in patients:
        patient_ids.append(str(patient["patient_id"]))
        metadata = dict(patient["metadata"])
        tier = str(metadata.get("tier", ""))
        if tier in tier_counts:
            tier_counts[tier] += 1
        visit_count += len(patient["visits"])

    return GenerationSummary(
        mode=mode,
        generated_count=len(patients),
        written_count=0 if dry_run else len(patients),
        output_dir=output_dir,
        quarantine_dir=quarantine_dir,
        dry_run=dry_run,
        dataset_version=DATASET_VERSION,
        tier_counts=tier_counts,
        visit_count=visit_count,
        patient_ids=patient_ids,
    )


def _append_pipeline_log(summary: GenerationSummary) -> None:
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = DEFAULT_LOG_DIR / "pipeline_run.log"
    line = (
        f"{_utc_timestamp_iso()} | generate_all | "
        f"mode={summary.mode} | "
        f"dataset_version={summary.dataset_version} | "
        f"generated={summary.generated_count} | written={summary.written_count} | "
        f"visits={summary.visit_count} | dry_run={summary.dry_run} | "
        f"output_dir={summary.output_dir}\n"
    )
    with log_path.open("a", encoding=JSON_ENCODING) as file:
        file.write(line)


def _print_summary(summary: GenerationSummary) -> None:
    mode_label = "DRY RUN" if summary.dry_run else "WRITE"
    print("=" * 80)
    print(f"v1.7 Lite dataset generation complete ({mode_label})")
    print("=" * 80)
    print(f"Dataset mode:       {summary.mode}")
    print(f"Dataset version:    {summary.dataset_version}")
    print(f"Patients generated: {summary.generated_count}")
    print(f"Patients written:   {summary.written_count}")
    print(f"Total visits:       {summary.visit_count}")
    print(f"Tier counts:        {summary.tier_counts}")
    print(f"Output directory:   {summary.output_dir}")
    print(f"Quarantine dir:     {summary.quarantine_dir}")
    print("Patient IDs:")
    for patient_id in summary.patient_ids:
        print(f"  - {patient_id}")
    print("=" * 80)
    print("Next step: run scripts/validate_all.py --mode v17_lite before SOAP generation.")


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------


def _log_stage(stage: int, description: str, extra: str = "") -> None:
    """Print a stage-start banner for the 5-step pipeline."""
    extra_str = f"  [{extra}]" if extra else ""
    print(f"  [Stage {stage}/5] {description}{extra_str}")


def _log_stage_done(stage: int, message: str) -> None:
    """Print a stage-completion confirmation."""
    print(f"  [Stage {stage}/5] ✓ {message}")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the deterministic v1.7 Lite synthetic patient dataset "
            "using the PatientBlueprint dataclass pipeline."
        )
    )
    parser.add_argument(
        "--mode",
        choices=list(_SUPPORTED_MODES),
        default=DEFAULT_DATASET_MODE,
        help=(
            f"Dataset generation mode. "
            f"Default: {DEFAULT_DATASET_MODE!r}. "
            f"Choices: {', '.join(_SUPPORTED_MODES)}."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_PATIENTS_DIR,
        help="Directory for approved generated patient JSON files. Default: data/patients",
    )
    parser.add_argument(
        "--quarantine-dir",
        type=Path,
        default=DEFAULT_QUARANTINE_DIR,
        help="Directory for generation failure reports. Default: data/quarantine",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        default=False,
        help=(
            "Explicitly request that existing PAT-*.json files are removed from "
            "output-dir before writing.  This is the default behavior unless "
            "--no-clean is passed."
        ),
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not remove existing PAT-*.json files from output-dir before writing.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and check patients without writing JSON files.",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Do not append a summary line to logs/pipeline_run.log.",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Small parsing helpers
# ---------------------------------------------------------------------------


def _require_str(
    mapping: dict[str, Any], key: str, *, context: str = "patient"
) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GenerateAllError(
            f"{context} missing required string field: {key}"
        )
    return value


def _require_dict(
    mapping: dict[str, Any], key: str, *, context: str = "patient"
) -> dict[str, Any]:
    value = mapping.get(key)
    if not isinstance(value, dict):
        raise GenerateAllError(
            f"{context} missing required object field: {key}"
        )
    return value


def _require_list(
    mapping: dict[str, Any], key: str, *, context: str = "patient"
) -> list[Any]:
    value = mapping.get(key)
    if not isinstance(value, list):
        raise GenerateAllError(
            f"{context} missing required list field: {key}"
        )
    return value


def _utc_timestamp_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _utc_timestamp_for_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
