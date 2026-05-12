"""
generators/patient_generator.py

Deterministic patient blueprint and patient shell generation.

This module creates patient shells only:
- schema_version
- patient_id
- demographics
- conditions
- empty allergy_registry
- empty visits
- metadata.tier

It does NOT generate:
- visits
- vitals
- labs
- medications
- allergies
- SOAP notes

Those are handled by downstream generator modules.

The generator supports two modes:
- pilot: first 5 patients only
- full: full 30-patient dataset

This file does not use runtime randomness. All patient identities, IDs,
tiers, conditions, first visit dates, and visit counts are deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.constants import (
    CHRONIC_ARCHETYPES,
    DATASET_MODE_FULL,
    DATASET_MODE_PILOT,
    DEFAULT_DATASET_MODE,
    EXPECTED_FULL_PATIENT_COUNT,
    EXPECTED_PILOT_PATIENT_COUNT,
    FEMALE_PATIENT_NAMES,
    FINAL_PATIENT_DISTRIBUTION,
    MALE_PATIENT_NAMES,
    MODERATE_ARCHETYPES,
    PILOT_PATIENT_DISTRIBUTION,
    SCHEMA_VERSION,
    TIER_TO_ID_PREFIX,
    VISIT_COUNT_PATTERNS,
)


@dataclass(frozen=True)
class PatientBlueprint:
    """
    Deterministic source configuration for one synthetic patient.

    Downstream generators use this object to build visits, labs,
    medications, allergies, and SOAP notes without guessing patient-level facts.
    """

    patient_id: str
    tier: str
    name: str
    date_of_birth: str
    sex: str
    conditions: tuple[str, ...]
    first_visit_date: str
    visit_count: int
    archetype: str


# These local overrides preserve the first five already-generated pilot identities
# without keeping the old global config constant PILOT_PATIENT_NAMES.
_LEGACY_PILOT_NAME_OVERRIDES: dict[tuple[str, int], str] = {
    ("normal", 1): "Omar Samir",
    ("normal", 2): "Mariam Adel",
    ("moderate", 1): "Karim Hassan",
    ("moderate", 2): "Nour Ahmed",
    ("chronic", 1): "Youssef Mahmoud",
}


_LEGACY_PILOT_SEX_OVERRIDES: dict[tuple[str, int], str] = {
    ("normal", 1): "male",
    ("normal", 2): "female",
    ("moderate", 1): "male",
    ("moderate", 2): "female",
    ("chronic", 1): "male",
}


_LEGACY_RESERVED_NAMES: set[str] = set(_LEGACY_PILOT_NAME_OVERRIDES.values())


def get_patient_blueprints(
    mode: str = DEFAULT_DATASET_MODE,
) -> list[PatientBlueprint]:
    """
    Generate deterministic patient blueprints.

    Args:
        mode:
            - "pilot": generate first 5 patients only
            - "full": generate full 30-patient dataset

    Returns:
        List of PatientBlueprint objects.
    """
    if mode == DATASET_MODE_PILOT:
        return get_pilot_blueprints()

    if mode == DATASET_MODE_FULL:
        return get_full_blueprints()

    raise ValueError(
        f"Unsupported dataset mode '{mode}'. "
        f"Expected '{DATASET_MODE_PILOT}' or '{DATASET_MODE_FULL}'."
    )


def get_full_blueprints() -> list[PatientBlueprint]:
    """
    Generate the full locked 30-patient dataset:
    - 10 normal
    - 13 moderate
    - 7 chronic
    """
    blueprints: list[PatientBlueprint] = []
    used_names: set[str] = set()

    for tier, count in FINAL_PATIENT_DISTRIBUTION.items():
        for index in range(1, count + 1):
            blueprint = _build_blueprint(
                tier=tier,
                index=index,
                used_names=used_names,
            )
            blueprints.append(blueprint)
            used_names.add(blueprint.name)

    _assert_expected_count(
        blueprints=blueprints,
        expected_count=EXPECTED_FULL_PATIENT_COUNT,
        mode=DATASET_MODE_FULL,
    )
    _assert_distribution(
        blueprints=blueprints,
        expected_distribution=FINAL_PATIENT_DISTRIBUTION,
    )
    _assert_unique_patient_ids(blueprints)
    _assert_unique_names(blueprints)
    _assert_ckd_constraints(blueprints)

    return blueprints


def get_pilot_blueprints() -> list[PatientBlueprint]:
    """
    Return the first 5 deterministic pilot patients:
    - 2 normal
    - 2 moderate
    - 1 chronic

    This keeps backward compatibility with the original milestone.
    """
    blueprint_keys = (
        ("normal", 1),
        ("normal", 2),
        ("moderate", 1),
        ("moderate", 2),
        ("chronic", 1),
    )

    blueprints: list[PatientBlueprint] = []
    used_names: set[str] = set()

    for tier, index in blueprint_keys:
        blueprint = _build_blueprint(
            tier=tier,
            index=index,
            used_names=used_names,
        )
        blueprints.append(blueprint)
        used_names.add(blueprint.name)

    _assert_expected_count(
        blueprints=blueprints,
        expected_count=EXPECTED_PILOT_PATIENT_COUNT,
        mode=DATASET_MODE_PILOT,
    )
    _assert_distribution(
        blueprints=blueprints,
        expected_distribution=PILOT_PATIENT_DISTRIBUTION,
    )
    _assert_unique_patient_ids(blueprints)
    _assert_unique_names(blueprints)
    _assert_ckd_constraints(blueprints)

    return blueprints


def create_patient_shell(blueprint: PatientBlueprint) -> dict[str, Any]:
    """
    Build the base patient JSON object.

    The shell follows the locked patient schema but leaves visit-level content
    empty for later deterministic generator modules.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "patient_id": blueprint.patient_id,
        "demographics": {
            "name": blueprint.name,
            "date_of_birth": blueprint.date_of_birth,
            "sex": blueprint.sex,
        },
        "conditions": list(blueprint.conditions),
        "allergy_registry": [],
        "visits": [],
        "metadata": {
            "tier": blueprint.tier,
        },
    }


def generate_patient_shells(
    mode: str = DEFAULT_DATASET_MODE,
) -> list[dict[str, Any]]:
    """
    Generate patient shells for the requested dataset mode.
    """
    return [
        create_patient_shell(blueprint)
        for blueprint in get_patient_blueprints(mode=mode)
    ]


def generate_pilot_patient_shells() -> list[dict[str, Any]]:
    """
    Backward-compatible wrapper for old scripts.

    Prefer generate_patient_shells(mode="pilot") in new code.
    """
    return generate_patient_shells(mode=DATASET_MODE_PILOT)


def generate_full_patient_shells() -> list[dict[str, Any]]:
    """
    Generate all 30 patient shells.
    """
    return generate_patient_shells(mode=DATASET_MODE_FULL)


def blueprint_by_patient_id(
    mode: str = DEFAULT_DATASET_MODE,
) -> dict[str, PatientBlueprint]:
    """
    Return patient blueprints keyed by patient_id.

    Downstream generators use this to access visit_count, tier, first_visit_date,
    and condition profile for each patient.
    """
    return {
        blueprint.patient_id: blueprint
        for blueprint in get_patient_blueprints(mode=mode)
    }


def _build_blueprint(
    tier: str,
    index: int,
    used_names: set[str] | None = None,
) -> PatientBlueprint:
    """
    Build a deterministic blueprint for one patient by tier and per-tier index.
    """
    patient_id = _make_patient_id(tier=tier, index=index)
    sex = _sex_for(tier=tier, index=index)
    name = _name_for(
        sex=sex,
        tier=tier,
        index=index,
        used_names=used_names or set(),
    )

    conditions = _conditions_for(tier=tier, index=index)
    archetype = _archetype_for(tier=tier, conditions=conditions)
    visit_count = _visit_count_for(tier=tier, index=index)
    first_visit_date = _first_visit_date_for(tier=tier, index=index)
    date_of_birth = _date_of_birth_for(tier=tier, index=index, sex=sex)

    return PatientBlueprint(
        patient_id=patient_id,
        tier=tier,
        name=name,
        date_of_birth=date_of_birth,
        sex=sex,
        conditions=conditions,
        first_visit_date=first_visit_date,
        visit_count=visit_count,
        archetype=archetype,
    )


def _make_patient_id(tier: str, index: int) -> str:
    """
    Create stable patient ID:
    PAT-NRM-001, PAT-MOD-001, PAT-CHR-001, etc.
    """
    if tier not in TIER_TO_ID_PREFIX:
        raise ValueError(f"Unsupported tier '{tier}'.")

    return f"PAT-{TIER_TO_ID_PREFIX[tier]}-{index:03d}"


def _conditions_for(tier: str, index: int) -> tuple[str, ...]:
    """
    Return deterministic condition tuple for the patient.
    """
    if tier == "normal":
        return ()

    if tier == "moderate":
        return tuple(MODERATE_ARCHETYPES[index])

    if tier == "chronic":
        return tuple(CHRONIC_ARCHETYPES[index])

    raise ValueError(f"Unsupported tier '{tier}'.")


def _archetype_for(tier: str, conditions: tuple[str, ...]) -> str:
    """
    Return human-readable archetype label for internal generation logic.
    """
    if tier == "normal":
        return "acute_simple"

    if "CKD" in conditions:
        return "t2dm_htn_ckd"

    if set(conditions) == {"T2DM", "HTN"}:
        return "t2dm_htn"

    return "_".join(condition.lower() for condition in conditions)


def _visit_count_for(tier: str, index: int) -> int:
    """
    Assign deterministic visit count using tier-specific visit count patterns.
    """
    pattern = VISIT_COUNT_PATTERNS[tier]
    return pattern[(index - 1) % len(pattern)]


def _first_visit_date_for(tier: str, index: int) -> str:
    """
    Assign deterministic first visit dates.

    Normal patients start in 2024.
    Moderate patients start in 2023.
    Chronic patients start in 2021.

    The month varies by index to avoid repeated identical timelines.
    """
    month = ((index - 1) % 12) + 1

    if tier == "normal":
        return f"2024-{month:02d}-05"

    if tier == "moderate":
        return f"2023-{month:02d}-10"

    if tier == "chronic":
        return f"2021-{month:02d}-15"

    raise ValueError(f"Unsupported tier '{tier}'.")


def _date_of_birth_for(tier: str, index: int, sex: str) -> str:
    """
    Generate deterministic adult date_of_birth values.

    The values are designed to keep age_at_visit within 18–80 years.
    """
    if tier == "normal":
        base_year = 1992 if sex == "male" else 1996
    elif tier == "moderate":
        base_year = 1980 if sex == "male" else 1986
    elif tier == "chronic":
        base_year = 1968 if sex == "male" else 1972
    else:
        raise ValueError(f"Unsupported tier '{tier}'.")

    year = base_year + (index % 7)
    month = ((index * 3) % 12) + 1
    day = ((index * 5) % 24) + 1

    return f"{year:04d}-{month:02d}-{day:02d}"


def _sex_for(tier: str, index: int) -> str:
    """
    Deterministically alternate sex values while keeping the first five
    pilot patients aligned with the original dataset.
    """
    if (tier, index) in _LEGACY_PILOT_SEX_OVERRIDES:
        return _LEGACY_PILOT_SEX_OVERRIDES[(tier, index)]

    return "male" if index % 2 == 1 else "female"


def _name_for(
    sex: str,
    tier: str,
    index: int,
    used_names: set[str],
) -> str:
    """
    Select a deterministic unique name from the configured name pools.

    Legacy pilot names are preserved for the first five known patients.
    For all later patients, the function selects the first unused name from
    the correct sex-specific pool while avoiding reserved pilot names.
    """
    override_key = (tier, index)
    if override_key in _LEGACY_PILOT_NAME_OVERRIDES:
        override_name = _LEGACY_PILOT_NAME_OVERRIDES[override_key]
        if override_name in used_names:
            raise ValueError(f"Duplicate legacy patient name detected: {override_name}")
        return override_name

    if sex == "male":
        pool = MALE_PATIENT_NAMES
    elif sex == "female":
        pool = FEMALE_PATIENT_NAMES
    else:
        raise ValueError(f"Unsupported sex '{sex}'.")

    tier_offset = {
        "normal": 0,
        "moderate": 5,
        "chronic": 10,
    }[tier]

    start_index = (tier_offset + index - 1) % len(pool)
    ordered_candidates = pool[start_index:] + pool[:start_index]

    for candidate in ordered_candidates:
        if candidate in used_names:
            continue
        if candidate in _LEGACY_RESERVED_NAMES:
            continue
        return candidate

    raise ValueError(
        f"No unused {sex} patient names remain for tier='{tier}', index={index}."
    )


def _assert_expected_count(
    blueprints: list[PatientBlueprint],
    expected_count: int,
    mode: str,
) -> None:
    if len(blueprints) != expected_count:
        raise ValueError(
            f"Invalid {mode} blueprint count. "
            f"Expected {expected_count}, got {len(blueprints)}."
        )


def _assert_distribution(
    blueprints: list[PatientBlueprint],
    expected_distribution: dict[str, int],
) -> None:
    """
    Fail fast if tier distribution does not match the selected dataset mode.
    """
    actual = {tier: 0 for tier in expected_distribution}

    for blueprint in blueprints:
        actual[blueprint.tier] = actual.get(blueprint.tier, 0) + 1

    if actual != expected_distribution:
        raise ValueError(
            f"Invalid tier distribution. "
            f"Expected {expected_distribution}, got {actual}."
        )


def _assert_unique_patient_ids(blueprints: list[PatientBlueprint]) -> None:
    patient_ids = [blueprint.patient_id for blueprint in blueprints]

    if len(patient_ids) != len(set(patient_ids)):
        raise ValueError("Duplicate patient_id detected in generated blueprints.")


def _assert_unique_names(blueprints: list[PatientBlueprint]) -> None:
    names = [blueprint.name for blueprint in blueprints]

    if len(names) != len(set(names)):
        duplicates = sorted(name for name in set(names) if names.count(name) > 1)
        raise ValueError(f"Duplicate patient names detected: {duplicates}")


def _assert_ckd_constraints(blueprints: list[PatientBlueprint]) -> None:
    """
    Enforce CKD semantic rule before patient JSON generation.

    CKD is complication-only:
    - chronic tier only
    - requires T2DM
    - requires HTN
    """
    for blueprint in blueprints:
        conditions = set(blueprint.conditions)

        if "CKD" not in conditions:
            continue

        if blueprint.tier != "chronic":
            raise ValueError(f"{blueprint.patient_id}: CKD requires chronic tier.")

        if "T2DM" not in conditions or "HTN" not in conditions:
            raise ValueError(f"{blueprint.patient_id}: CKD requires T2DM and HTN.")
