"""
tests/test_soap_selector.py

Unit tests for deterministic SOAP template selection utilities.

Purpose:
    Validate that soap_selector.py remains deterministic, reproducible,
    contract-aware, and limited to template selection only.

The selector must:
    - use stable SHA-256 based indexing,
    - never use Python built-in hash(),
    - route by SOAP section and patient tier,
    - preserve canonical SOAP section order,
    - return templates from the approved registry,
    - expose deterministic selection metadata,
    - reject invalid section, tier, seed, and fact-context inputs.

These tests intentionally avoid SOAP rendering and medical fact formatting.
"""

from __future__ import annotations

from typing import Any

import pytest

from soap.soap_contract import (
    PATIENT_TIERS,
    SOAP_SECTIONS,
    PatientTier,
    SoapSection,
    SoapTemplate,
)
from soap.soap_selector import (
    SoapTemplateSelection,
    build_template_seed_key,
    get_template_group,
    select_template,
    select_template_with_metadata,
    select_templates_for_visit,
    select_templates_for_visit_with_metadata,
    select_templates_from_fact_context,
    select_templates_from_fact_context_with_metadata,
    stable_index,
)
from soap.soap_templates import SOAP_TEMPLATES, TEMPLATE_VERSION


MODERATE_FACT_CONTEXT: dict[str, Any] = {
    "patient_id": "PAT-MOD-003",
    "visit_id": "VST-MOD-003-004",
    "tier": "moderate",
    "visit_type": "follow_up",
}


NORMAL_FACT_CONTEXT: dict[str, Any] = {
    "patient_id": "PAT-NRM-001",
    "visit_id": "VST-NRM-001-001",
    "tier": "normal",
    "visit_type": "initial",
}


CHRONIC_FACT_CONTEXT: dict[str, Any] = {
    "patient_id": "PAT-CHR-002",
    "visit_id": "VST-CHR-002-004",
    "tier": "chronic",
    "visit_type": "follow_up",
}


def test_template_version_is_available_for_selection_seed() -> None:
    """The selector must use the semantic v1.1 template registry version."""
    assert TEMPLATE_VERSION == "soap-templates-v1.1"


def test_build_template_seed_key_preserves_exact_field_order() -> None:
    """
    Seed-key field order is part of the deterministic selection contract.

    Do not change this order unless intentionally versioning selector behavior.
    """
    seed_key = build_template_seed_key(
        template_version=TEMPLATE_VERSION,
        patient_id="PAT-MOD-003",
        visit_id="VST-MOD-003-004",
        section="objective",
        tier="moderate",
        visit_type="follow_up",
    )

    assert (
        seed_key
        == "soap-templates-v1.1|PAT-MOD-003|VST-MOD-003-004|"
        "objective|moderate|follow_up"
    )


def test_build_template_seed_key_trims_edge_whitespace() -> None:
    """Seed-key inputs should be trimmed before deterministic selection."""
    seed_key = build_template_seed_key(
        template_version=f"  {TEMPLATE_VERSION}  ",
        patient_id="  PAT-MOD-003  ",
        visit_id="  VST-MOD-003-004  ",
        section="  objective  ",
        tier="  moderate  ",
        visit_type="  follow_up  ",
    )

    assert (
        seed_key
        == "soap-templates-v1.1|PAT-MOD-003|VST-MOD-003-004|"
        "objective|moderate|follow_up"
    )


def test_stable_index_is_deterministic_for_same_seed() -> None:
    """The same seed and group size must always produce the same index."""
    seed_key = (
        "soap-templates-v1.1|PAT-MOD-003|VST-MOD-003-004|"
        "objective|moderate|follow_up"
    )

    first = stable_index(seed_key=seed_key, size=4)
    second = stable_index(seed_key=seed_key, size=4)
    third = stable_index(seed_key=seed_key, size=4)

    assert first == second == third
    assert first == 3


def test_stable_index_returns_value_inside_group_bounds() -> None:
    """Stable index must always be in range [0, size)."""
    seed_key = "selector-test-seed"

    for size in range(1, 20):
        index = stable_index(seed_key=seed_key, size=size)

        assert 0 <= index < size


def test_stable_index_rejects_empty_seed_key() -> None:
    """Empty seed strings must be rejected."""
    with pytest.raises(ValueError):
        stable_index(seed_key="", size=3)


def test_stable_index_rejects_empty_template_group_size() -> None:
    """A selector cannot choose from an empty template group."""
    with pytest.raises(ValueError):
        stable_index(seed_key="valid-seed", size=0)


def test_get_template_group_returns_registered_tuple_for_each_section_and_tier() -> None:
    """Every section/tier pair must return the exact registry tuple."""
    for section in SOAP_SECTIONS:
        for tier in PATIENT_TIERS:
            group = get_template_group(section=section, tier=tier)

            assert isinstance(group, tuple)
            assert group == SOAP_TEMPLATES[section][tier]
            assert len(group) > 0
            assert all(isinstance(template, SoapTemplate) for template in group)


def test_get_template_group_rejects_invalid_section() -> None:
    """Invalid SOAP sections must fail fast."""
    with pytest.raises(ValueError):
        get_template_group(section="history", tier="moderate")


def test_get_template_group_rejects_invalid_tier() -> None:
    """Invalid patient tiers must fail fast."""
    with pytest.raises(ValueError):
        get_template_group(section="objective", tier="critical")


def test_select_template_returns_registered_template() -> None:
    """select_template must return a SoapTemplate from the correct group."""
    template = select_template(
        patient_id="PAT-MOD-003",
        visit_id="VST-MOD-003-004",
        section="objective",
        tier="moderate",
        visit_type="follow_up",
    )

    assert isinstance(template, SoapTemplate)
    assert template in SOAP_TEMPLATES["objective"]["moderate"]
    assert template.section == "objective"
    assert template.tier == "moderate"


def test_select_template_with_metadata_returns_complete_selection_record() -> None:
    """Metadata selection must expose deterministic selection details."""
    selection = select_template_with_metadata(
        patient_id="PAT-MOD-003",
        visit_id="VST-MOD-003-004",
        section="objective",
        tier="moderate",
        visit_type="follow_up",
    )

    assert isinstance(selection, SoapTemplateSelection)
    assert selection.section == "objective"
    assert selection.tier == "moderate"
    assert selection.visit_type == "follow_up"
    assert selection.template == SOAP_TEMPLATES["objective"]["moderate"][3]
    assert selection.template_index == 3
    assert selection.template_version == TEMPLATE_VERSION
    assert selection.seed_key == (
        "soap-templates-v1.1|PAT-MOD-003|VST-MOD-003-004|"
        "objective|moderate|follow_up"
    )


def test_select_template_is_deterministic_for_same_inputs() -> None:
    """Repeated calls with the same inputs must return the same template."""
    first = select_template(
        patient_id="PAT-MOD-003",
        visit_id="VST-MOD-003-004",
        section="plan",
        tier="moderate",
        visit_type="follow_up",
    )
    second = select_template(
        patient_id="PAT-MOD-003",
        visit_id="VST-MOD-003-004",
        section="plan",
        tier="moderate",
        visit_type="follow_up",
    )

    assert first == second
    assert first.template_id == "PLAN-MOD-001"


def test_select_templates_for_visit_returns_all_sections_in_canonical_order() -> None:
    """Whole-visit selection must return one template per SOAP section."""
    selected = select_templates_for_visit(
        patient_id="PAT-MOD-003",
        visit_id="VST-MOD-003-004",
        tier="moderate",
        visit_type="follow_up",
    )

    assert tuple(selected.keys()) == SOAP_SECTIONS

    for section in SOAP_SECTIONS:
        template = selected[section]

        assert isinstance(template, SoapTemplate)
        assert template.section == section
        assert template.tier == "moderate"


def test_select_templates_for_visit_with_metadata_returns_all_sections() -> None:
    """Whole-visit metadata selection must preserve canonical section order."""
    selected = select_templates_for_visit_with_metadata(
        patient_id="PAT-MOD-003",
        visit_id="VST-MOD-003-004",
        tier="moderate",
        visit_type="follow_up",
    )

    assert tuple(selected.keys()) == SOAP_SECTIONS

    for section in SOAP_SECTIONS:
        selection = selected[section]

        assert isinstance(selection, SoapTemplateSelection)
        assert selection.section == section
        assert selection.tier == "moderate"
        assert selection.visit_type == "follow_up"
        assert selection.template.section == section
        assert selection.template.tier == "moderate"


def test_select_templates_from_fact_context_uses_required_context_keys() -> None:
    """Fact-context selection must read patient_id, visit_id, tier, and visit_type."""
    selected = select_templates_from_fact_context(MODERATE_FACT_CONTEXT)

    assert tuple(selected.keys()) == SOAP_SECTIONS
    assert selected["subjective"].template_id == "SUBJ-MOD-002"
    assert selected["objective"].template_id == "OBJ-MOD-004"
    assert selected["assessment"].template_id == "ASM-MOD-003"
    assert selected["plan"].template_id == "PLAN-MOD-001"


def test_select_templates_from_fact_context_with_metadata_uses_required_keys() -> None:
    """Fact-context metadata selection must expose stable selector metadata."""
    selected = select_templates_from_fact_context_with_metadata(MODERATE_FACT_CONTEXT)

    assert tuple(selected.keys()) == SOAP_SECTIONS

    for section in SOAP_SECTIONS:
        selection = selected[section]

        assert selection.section == section
        assert selection.tier == "moderate"
        assert selection.visit_type == "follow_up"
        assert selection.template_version == TEMPLATE_VERSION
        assert "PAT-MOD-003" in selection.seed_key
        assert "VST-MOD-003-004" in selection.seed_key


def test_selection_for_moderate_fixture_is_regression_stable() -> None:
    """Template IDs for the moderate regression fixture must remain stable."""
    selected = select_templates_from_fact_context(MODERATE_FACT_CONTEXT)

    assert selected["subjective"].template_id == "SUBJ-MOD-002"
    assert selected["objective"].template_id == "OBJ-MOD-004"
    assert selected["assessment"].template_id == "ASM-MOD-003"
    assert selected["plan"].template_id == "PLAN-MOD-001"


def test_selection_for_normal_fixture_is_regression_stable() -> None:
    """Template IDs for the normal regression fixture must remain stable."""
    selected = select_templates_from_fact_context(NORMAL_FACT_CONTEXT)

    assert selected["subjective"].template_id == "SUBJ-NRM-001"
    assert selected["objective"].template_id == "OBJ-NRM-002"
    assert selected["assessment"].template_id == "ASM-NRM-003"
    assert selected["plan"].template_id == "PLAN-NRM-001"


def test_selection_for_chronic_fixture_is_regression_stable() -> None:
    """Template IDs for the chronic regression fixture must remain stable."""
    selected = select_templates_from_fact_context(CHRONIC_FACT_CONTEXT)

    assert selected["subjective"].template_id == "SUBJ-CHR-004"
    assert selected["objective"].template_id == "OBJ-CHR-003"
    assert selected["assessment"].template_id == "ASM-CHR-001"
    assert selected["plan"].template_id == "PLAN-CHR-005"


def test_different_visit_ids_can_select_different_templates_without_randomness() -> None:
    """
    Different stable visit IDs may route to different templates deterministically.

    This protects deterministic diversification without introducing randomness.
    """
    selected_ids_by_section: dict[SoapSection, set[str]] = {
        section: set()
        for section in SOAP_SECTIONS
    }

    for visit_number in range(1, 11):
        selected = select_templates_for_visit(
            patient_id="PAT-MOD-999",
            visit_id=f"VST-MOD-999-{visit_number:03d}",
            tier="moderate",
            visit_type="follow_up",
        )

        for section, template in selected.items():
            selected_ids_by_section[section].add(template.template_id)

    for section in SOAP_SECTIONS:
        assert len(selected_ids_by_section[section]) >= 2


@pytest.mark.parametrize("section", SOAP_SECTIONS)
def test_select_template_accepts_every_soap_section(section: SoapSection) -> None:
    """Selector must accept every canonical SOAP section."""
    template = select_template(
        patient_id="PAT-MOD-003",
        visit_id="VST-MOD-003-004",
        section=section,
        tier="moderate",
        visit_type="follow_up",
    )

    assert isinstance(template, SoapTemplate)
    assert template.section == section


@pytest.mark.parametrize("tier", PATIENT_TIERS)
def test_select_template_accepts_every_patient_tier(tier: PatientTier) -> None:
    """Selector must accept every canonical patient tier."""
    template = select_template(
        patient_id="PAT-MOD-003",
        visit_id="VST-MOD-003-004",
        section="subjective",
        tier=tier,
        visit_type="follow_up",
    )

    assert isinstance(template, SoapTemplate)
    assert template.tier == tier


@pytest.mark.parametrize(
    "field_name, kwargs",
    [
        (
            "patient_id",
            {
                "patient_id": "",
                "visit_id": "VST-MOD-003-004",
                "section": "objective",
                "tier": "moderate",
                "visit_type": "follow_up",
            },
        ),
        (
            "visit_id",
            {
                "patient_id": "PAT-MOD-003",
                "visit_id": "",
                "section": "objective",
                "tier": "moderate",
                "visit_type": "follow_up",
            },
        ),
        (
            "visit_type",
            {
                "patient_id": "PAT-MOD-003",
                "visit_id": "VST-MOD-003-004",
                "section": "objective",
                "tier": "moderate",
                "visit_type": "",
            },
        ),
        (
            "template_version",
            {
                "patient_id": "PAT-MOD-003",
                "visit_id": "VST-MOD-003-004",
                "section": "objective",
                "tier": "moderate",
                "visit_type": "follow_up",
                "template_version": "",
            },
        ),
    ],
)
def test_select_template_rejects_empty_seed_inputs(
    field_name: str,
    kwargs: dict[str, str],
) -> None:
    """Selector must reject empty seed inputs."""
    with pytest.raises(ValueError, match=field_name):
        select_template(**kwargs)


@pytest.mark.parametrize(
    "bad_context",
    [
        {
            "visit_id": "VST-MOD-003-004",
            "tier": "moderate",
            "visit_type": "follow_up",
        },
        {
            "patient_id": "PAT-MOD-003",
            "tier": "moderate",
            "visit_type": "follow_up",
        },
        {
            "patient_id": "PAT-MOD-003",
            "visit_id": "VST-MOD-003-004",
            "visit_type": "follow_up",
        },
        {
            "patient_id": "PAT-MOD-003",
            "visit_id": "VST-MOD-003-004",
            "tier": "moderate",
        },
    ],
)
def test_select_templates_from_fact_context_rejects_missing_required_keys(
    bad_context: dict[str, Any],
) -> None:
    """Fact-context selection must fail if a required routing key is missing."""
    with pytest.raises(ValueError):
        select_templates_from_fact_context(bad_context)


@pytest.mark.parametrize(
    "bad_context",
    [
        {
            "patient_id": 123,
            "visit_id": "VST-MOD-003-004",
            "tier": "moderate",
            "visit_type": "follow_up",
        },
        {
            "patient_id": "PAT-MOD-003",
            "visit_id": None,
            "tier": "moderate",
            "visit_type": "follow_up",
        },
        {
            "patient_id": "PAT-MOD-003",
            "visit_id": "VST-MOD-003-004",
            "tier": ["moderate"],
            "visit_type": "follow_up",
        },
        {
            "patient_id": "PAT-MOD-003",
            "visit_id": "VST-MOD-003-004",
            "tier": "moderate",
            "visit_type": 42,
        },
    ],
)
def test_select_templates_from_fact_context_rejects_non_string_required_values(
    bad_context: dict[str, Any],
) -> None:
    """Fact-context routing values must be strings."""
    with pytest.raises(ValueError):
        select_templates_from_fact_context(bad_context)


def test_select_templates_from_fact_context_rejects_invalid_tier() -> None:
    """Invalid tier values in fact context must be rejected."""
    bad_context = dict(MODERATE_FACT_CONTEXT)
    bad_context["tier"] = "critical"

    with pytest.raises(ValueError):
        select_templates_from_fact_context(bad_context)


def test_select_templates_from_fact_context_rejects_invalid_section_indirectly() -> None:
    """Invalid section values are rejected by public single-template selection."""
    with pytest.raises(ValueError):
        select_template(
            patient_id="PAT-MOD-003",
            visit_id="VST-MOD-003-004",
            section="summary",
            tier="moderate",
            visit_type="follow_up",
        )
