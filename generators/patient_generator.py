"""
generators/patient_generator.py

Generates patient shell objects for the 15-patient v1.7 Lite synthetic dataset.

RESPONSIBILITY
--------------
This module builds the patient root JSON object:
    schema_version, patient_id, demographics, conditions,
    allergy_registry (empty), visits (empty), metadata.

It does NOT generate:
    - visits            (→ generators/visit_generator.py)
    - labs              (→ generators/lab_generator.py)
    - medications       (→ generators/medication_generator.py)
    - allergy records   (→ generators/allergy_generator.py)
    - SOAP notes        (→ soap/soap_generator.py)
    - ChromaDB chunks   (→ ingestion/chunker.py)

Downstream generators call this module to get the patient shell, then
populate `visits` and `allergy_registry` in-place before the record is
exported to data/patients/.

DETERMINISM
-----------
All outputs are deterministic:
- blueprint.sex drives name-pool selection.
- The GLOBAL index of the blueprint in ALL_BLUEPRINTS drives name selection
  and DOB calculation — regardless of which mode (v17_lite / full / pilot) is
  active.  This guarantees that PAT-CHR-005, for example, always receives the
  same name and date_of_birth whether it is generated as part of the full
  15-patient run or the 5-patient pilot run.
- tier drives the age band.
- No random module usage anywhere in this file.

USAGE CONTRACT
--------------
- Import locked constants from config/constants.py only.
- Import blueprints from config/patient_blueprints.py only.
- Return plain Python dicts.
- Do not write files here.
- Do not call validators here.
- Do not call LLMs.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Final

from config.constants import (
    AGE_LIMITS,
    CONDITIONS,
    DATASET_MODE_FULL,
    DATASET_MODE_PILOT,
    DATASET_MODE_V17_LITE,
    DATASET_VERSION,
    EXPECTED_V17_LITE_PATIENT_COUNT,
    FEMALE_PATIENT_NAMES,
    FINAL_PATIENT_DISTRIBUTION,
    MALE_PATIENT_NAMES,
    PATIENT_ID_REGEX,
    REQUIRED_DEMOGRAPHICS_FIELDS,
    REQUIRED_PATIENT_METADATA_FIELDS_V17_LITE,
    REQUIRED_TOP_LEVEL_FIELDS,
    SCHEMA_VERSION,
    SEX_VALUES,
    TIERS,
)
from config.patient_blueprints import (
    ALL_BLUEPRINTS,
    BLUEPRINT_BY_ID,
    PILOT_BLUEPRINTS,
    PatientBlueprint,
)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

PatientRecord = dict  # top-level patient JSON-compatible dict
Demographics = dict   # {"name": str, "date_of_birth": str, "sex": str}


# ---------------------------------------------------------------------------
# Age bands per tier
# Reference year is fixed so DOB calculation is always identical.
# Bands are validated against AGE_LIMITS at module level (see bottom).
# ---------------------------------------------------------------------------

_REFERENCE_YEAR: Final[int] = 2026

_TIER_AGE_BANDS: Final[dict[str, tuple[int, int]]] = {
    "normal":   (24, 34),   # younger adults — short acute illness arc
    "moderate": (38, 62),   # middle adults  — managed condition stories
    "chronic":  (58, 75),   # older adults   — long-term multi-visit stories
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PatientGenerationError(ValueError):
    """Raised when a blueprint produces an invalid or incomplete patient shell."""


# ---------------------------------------------------------------------------
# Global index lookup
# ---------------------------------------------------------------------------

# Pre-built at import time: maps every patient_id to its 0-based position in
# ALL_BLUEPRINTS.  This is the single source of index truth for demographics
# generation.  Using the global position instead of the mode-local enumerate
# index guarantees that a given patient always receives the same name and
# date_of_birth regardless of which dataset mode is active.
_GLOBAL_INDEX: dict[str, int] = {
    bp.patient_id: idx for idx, bp in enumerate(ALL_BLUEPRINTS)
}


def _global_blueprint_index(patient_id: str) -> int:
    """Return the 0-based position of patient_id in ALL_BLUEPRINTS.

    This index is stable across all dataset modes (v17_lite, full, pilot).
    It must be used wherever demographics are generated so that name and
    date_of_birth are identical no matter which mode triggered generation.

    Raises:
        PatientGenerationError: if patient_id is not in ALL_BLUEPRINTS.
    """
    try:
        return _GLOBAL_INDEX[patient_id]
    except KeyError:
        raise PatientGenerationError(
            f"patient_id '{patient_id}' not found in ALL_BLUEPRINTS. "
            f"Known IDs: {list(_GLOBAL_INDEX.keys())}"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_blueprints_for_mode(mode: str) -> tuple[PatientBlueprint, ...]:
    """Return the correct blueprint tuple for the requested dataset mode.

    Supported modes:
        DATASET_MODE_V17_LITE  → all 15 curated blueprints (canonical)
        DATASET_MODE_FULL      → same as V17_LITE (v1.7 Lite IS the full dataset)
        DATASET_MODE_PILOT     → 5 blueprints for fast development testing

    Raises:
        ValueError: if mode is not recognised.
    """
    if mode in (DATASET_MODE_V17_LITE, DATASET_MODE_FULL):
        return ALL_BLUEPRINTS
    if mode == DATASET_MODE_PILOT:
        return PILOT_BLUEPRINTS
    raise ValueError(
        f"Unsupported dataset mode: '{mode}'. "
        f"Expected one of: {DATASET_MODE_V17_LITE!r}, "
        f"{DATASET_MODE_FULL!r}, {DATASET_MODE_PILOT!r}."
    )


def generate_patient_from_blueprint(
    blueprint: PatientBlueprint,
    index: int,
) -> PatientRecord:
    """Generate a single patient shell from a PatientBlueprint.

    The returned dict has empty visits and allergy_registry lists.
    Downstream generators (visit_generator, allergy_generator) populate
    those lists before the record is written to disk.

    Args:
        blueprint: A PatientBlueprint dataclass instance.
        index:     0-based position of this blueprint in ALL_BLUEPRINTS.
                   Must always be the GLOBAL position (use
                   _global_blueprint_index) — never the mode-local enumerate
                   index — so that name and DOB are stable across modes.

    Returns:
        A patient JSON-compatible dict matching the v1.7 Lite schema.

    Raises:
        PatientGenerationError: if any required field is missing or invalid.
    """
    _validate_blueprint_fields(blueprint)

    demographics = build_demographics(blueprint, index)
    metadata = _build_metadata(blueprint)

    patient: PatientRecord = {
        "schema_version": SCHEMA_VERSION,
        "patient_id": blueprint.patient_id,
        "demographics": demographics,
        "conditions": list(blueprint.conditions),
        "allergy_registry": [],  # populated by allergy_generator
        "visits": [],            # populated by visit_generator
        "metadata": metadata,
    }

    _validate_patient_shell(patient)
    return patient


def generate_patient_by_id(patient_id: str) -> PatientRecord:
    """Generate a single patient shell by patient_id.

    Convenience wrapper around generate_patient_from_blueprint.
    Always uses the global ALL_BLUEPRINTS index so demographics are
    identical to those produced by generate_patients() in any mode.

    Raises:
        KeyError: if patient_id is not in BLUEPRINT_BY_ID.
        PatientGenerationError: if generation fails.
    """
    if patient_id not in BLUEPRINT_BY_ID:
        raise KeyError(
            f"No blueprint found for patient_id='{patient_id}'. "
            f"Available IDs: {list(BLUEPRINT_BY_ID.keys())}"
        )
    blueprint = BLUEPRINT_BY_ID[patient_id]
    index = _global_blueprint_index(patient_id)
    return generate_patient_from_blueprint(blueprint, index)


def generate_patients(mode: str = DATASET_MODE_V17_LITE) -> list[PatientRecord]:
    """Generate all patient shells for the requested dataset mode.

    Returns a list of patient dicts with empty visits and allergy_registry.
    Ordering is deterministic and matches ALL_BLUEPRINTS or PILOT_BLUEPRINTS.

    Each blueprint is passed its GLOBAL ALL_BLUEPRINTS index (not its
    position within the mode-local subset) so that demographics are
    identical across modes.

    Args:
        mode: Dataset mode string — see get_blueprints_for_mode for options.

    Returns:
        List of patient shell dicts, one per blueprint.

    Raises:
        ValueError: if mode is not supported.
        PatientGenerationError: if any patient shell is invalid.
    """
    blueprints = get_blueprints_for_mode(mode)
    _validate_blueprint_collection(blueprints, mode)

    return [
        generate_patient_from_blueprint(bp, _global_blueprint_index(bp.patient_id))
        for bp in blueprints
    ]


def build_demographics(blueprint: PatientBlueprint, index: int) -> Demographics:
    """Build deterministic synthetic demographics from a blueprint.

    Rules:
    - sex comes from blueprint.sex (not derived from ordinal).
    - name is selected from the sex-appropriate name pool using index.
    - date_of_birth is derived from tier age band and index.
    - 'age' is NEVER stored (forbidden by schema contract).

    Args:
        blueprint: PatientBlueprint instance.
        index:     Global 0-based position from ALL_BLUEPRINTS (use
                   _global_blueprint_index).  Must be the global position,
                   not a mode-local enumerate value.

    Returns:
        {"name": str, "date_of_birth": "YYYY-MM-DD", "sex": str}
    """
    sex = blueprint.sex
    name = _deterministic_name(sex, index)
    dob  = _deterministic_date_of_birth(blueprint.tier, index)

    demographics: Demographics = {
        "name": name,
        "date_of_birth": dob,
        "sex": sex,
    }

    # Defensive: 'age' must never appear in generated demographics.
    if "age" in demographics:
        raise PatientGenerationError(
            f"{blueprint.patient_id}: 'age' field is forbidden in demographics."
        )

    _check_required_keys(demographics, REQUIRED_DEMOGRAPHICS_FIELDS, "demographics")
    return demographics


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------

def _build_metadata(blueprint: PatientBlueprint) -> dict:
    """Build the patient-level metadata dict from blueprint fields.

    Only v1.7 Lite metadata contract fields are included.
    Blueprint-only fields (visit_roles, lab_focus, initial_medications,
    added_medications, completed_medications, stopped_medications,
    medication_arc, retrieval_notes) are intentionally excluded — they
    belong to generators and documentation, not the patient JSON.
    """
    return {
        "tier":                    blueprint.tier,
        "dataset_version":         DATASET_VERSION,
        "story_arc":               blueprint.story_arc,
        "timeline_pattern":        blueprint.timeline_pattern,
        "semantic_focus":          blueprint.semantic_focus,
        "retrieval_signature":     blueprint.retrieval_signature,
        "retrieval_intent_tags":   list(blueprint.retrieval_intent_tags),
        "soap_style":              blueprint.soap_style,
        "primary_retrieval_targets": list(blueprint.primary_retrieval_targets),
    }


# ---------------------------------------------------------------------------
# Internal validation helpers
# ---------------------------------------------------------------------------

def _validate_blueprint_fields(blueprint: PatientBlueprint) -> None:
    """Lightweight contract check on the blueprint before generation.

    Full V7/V12 validation is handled by validators/rules.py at pipeline time.
    This function only checks the minimum fields this module needs.
    """
    pid = blueprint.patient_id

    if not re.fullmatch(PATIENT_ID_REGEX, pid):
        raise PatientGenerationError(f"Invalid patient_id format: '{pid}'")

    if blueprint.tier not in TIERS:
        raise PatientGenerationError(
            f"{pid}: tier '{blueprint.tier}' not in TIERS"
        )

    if blueprint.sex not in SEX_VALUES:
        raise PatientGenerationError(
            f"{pid}: sex '{blueprint.sex}' not in SEX_VALUES"
        )

    if not blueprint.conditions:
        raise PatientGenerationError(f"{pid}: conditions tuple is empty.")

    invalid = sorted(set(blueprint.conditions) - set(CONDITIONS))
    if invalid:
        raise PatientGenerationError(
            f"{pid}: invalid conditions: {invalid}"
        )

    if blueprint.visit_count <= 0:
        raise PatientGenerationError(
            f"{pid}: visit_count must be a positive integer."
        )

    if len(blueprint.visit_roles) != blueprint.visit_count:
        raise PatientGenerationError(
            f"{pid}: len(visit_roles)={len(blueprint.visit_roles)} "
            f"!= visit_count={blueprint.visit_count}"
        )


def _validate_patient_shell(patient: PatientRecord) -> None:
    """Check that the generated patient shell satisfies the schema contract."""
    _check_required_keys(patient, REQUIRED_TOP_LEVEL_FIELDS, "patient")

    if patient["schema_version"] != SCHEMA_VERSION:
        raise PatientGenerationError(
            f"schema_version mismatch: expected '{SCHEMA_VERSION}', "
            f"got '{patient['schema_version']}'."
        )

    if not isinstance(patient["visits"], list):
        raise PatientGenerationError("patient['visits'] must be a list.")

    if not isinstance(patient["allergy_registry"], list):
        raise PatientGenerationError("patient['allergy_registry'] must be a list.")

    # Metadata contract check.
    _check_required_keys(
        patient.get("metadata", {}),
        REQUIRED_PATIENT_METADATA_FIELDS_V17_LITE,
        "patient.metadata",
    )

    # 'age' must never exist anywhere in demographics.
    demographics = patient.get("demographics", {})
    if "age" in demographics:
        raise PatientGenerationError(
            f"{patient['patient_id']}: 'age' field must not be stored in demographics."
        )


def _validate_blueprint_collection(
    blueprints: tuple[PatientBlueprint, ...],
    mode: str,
) -> None:
    """Dataset-level checks before generating the full collection.

    Verifies count, tier distribution (full mode only), and uniqueness.
    This is NOT a replacement for validators/rules.py — it is a pre-flight
    guard inside the generator.
    """
    if mode in (DATASET_MODE_V17_LITE, DATASET_MODE_FULL):
        if len(blueprints) != EXPECTED_V17_LITE_PATIENT_COUNT:
            raise PatientGenerationError(
                f"Expected {EXPECTED_V17_LITE_PATIENT_COUNT} blueprints "
                f"for mode '{mode}', got {len(blueprints)}."
            )

        # Tier distribution check (full dataset only).
        tier_counts: dict[str, int] = {t: 0 for t in TIERS}
        for bp in blueprints:
            tier_counts[bp.tier] = tier_counts.get(bp.tier, 0) + 1

        for tier, expected in FINAL_PATIENT_DISTRIBUTION.items():
            actual = tier_counts.get(tier, 0)
            if actual != expected:
                raise PatientGenerationError(
                    f"Tier distribution mismatch for '{tier}': "
                    f"expected {expected}, got {actual}."
                )

    # Uniqueness checks apply to all modes.
    seen_ids: set[str] = set()
    seen_sigs: set[str] = set()
    for bp in blueprints:
        if bp.patient_id in seen_ids:
            raise PatientGenerationError(
                f"Duplicate patient_id in blueprint collection: '{bp.patient_id}'"
            )
        seen_ids.add(bp.patient_id)

        if bp.retrieval_signature in seen_sigs:
            raise PatientGenerationError(
                f"Duplicate retrieval_signature: '{bp.retrieval_signature}'"
            )
        seen_sigs.add(bp.retrieval_signature)


def _check_required_keys(
    mapping: object,
    required_keys: tuple[str, ...] | list[str],
    label: str,
) -> None:
    """Raise PatientGenerationError if any required key is absent."""
    if not isinstance(mapping, dict):
        raise PatientGenerationError(f"{label} must be a dict, got {type(mapping).__name__}.")
    missing = [k for k in required_keys if k not in mapping]
    if missing:
        raise PatientGenerationError(
            f"{label} missing required keys: {missing}"
        )


# ---------------------------------------------------------------------------
# Deterministic demographics helpers
# ---------------------------------------------------------------------------

def _deterministic_name(sex: str, index: int) -> str:
    """Select a synthetic name deterministically from the sex-specific pool.

    Uses `index` (0-based generation position) so the same blueprint always
    gets the same name regardless of which mode is active.
    """
    pool = FEMALE_PATIENT_NAMES if sex == "female" else MALE_PATIENT_NAMES
    if not pool:
        raise PatientGenerationError(
            f"Name pool for sex='{sex}' is empty in constants."
        )
    return pool[index % len(pool)]


def _deterministic_date_of_birth(tier: str, index: int) -> str:
    """Generate a deterministic date_of_birth string (YYYY-MM-DD).

    Strategy:
    - tier determines the age band (see _TIER_AGE_BANDS).
    - index cycles through ages within the band to ensure variety.
    - month cycles 1–12 using index.
    - day uses a small spread to avoid all patients sharing the same day.

    Age is always within AGE_LIMITS to satisfy V3 validation.
    """
    if tier not in _TIER_AGE_BANDS:
        raise PatientGenerationError(
            f"No age band defined for tier='{tier}'. "
            f"Expected one of: {list(_TIER_AGE_BANDS.keys())}"
        )

    min_age, max_age = _TIER_AGE_BANDS[tier]
    global_min, global_max = AGE_LIMITS

    # Defensive: bands must sit within global limits (caught at module level too).
    if min_age < global_min or max_age > global_max:
        raise PatientGenerationError(
            f"Age band ({min_age}–{max_age}) for tier='{tier}' "
            f"exceeds AGE_LIMITS ({global_min}–{global_max})."
        )

    age_span = max_age - min_age + 1
    age   = min_age + (index % age_span)
    year  = _REFERENCE_YEAR - age
    month = (index % 12) + 1
    day   = ((index * 3) % 27) + 1   # 1–27; avoids month-end edge cases

    return date(year, month, day).isoformat()


# ---------------------------------------------------------------------------
# Module-level band validation
# Catches any future edit to _TIER_AGE_BANDS that violates AGE_LIMITS.
# ---------------------------------------------------------------------------

def _assert_age_bands_valid() -> None:
    global_min, global_max = AGE_LIMITS
    for tier, (lo, hi) in _TIER_AGE_BANDS.items():
        assert lo >= global_min and hi <= global_max, (
            f"_TIER_AGE_BANDS['{tier}'] = ({lo}, {hi}) violates "
            f"AGE_LIMITS = {AGE_LIMITS}."
        )


_assert_age_bands_valid()


# ---------------------------------------------------------------------------
# Backward-compatible aliases
# The old generate_all.py script may call generate_all_patients() or
# generate_patient().  These thin wrappers preserve that contract.
# ---------------------------------------------------------------------------

def generate_all_patients(mode: str = DATASET_MODE_V17_LITE) -> list[PatientRecord]:
    """Backward-compatible alias for generate_patients()."""
    return generate_patients(mode)


def generate_patient(
    blueprint: PatientBlueprint,
    index: int = 0,
) -> PatientRecord:
    """Backward-compatible alias for generate_patient_from_blueprint()."""
    return generate_patient_from_blueprint(blueprint, index)
