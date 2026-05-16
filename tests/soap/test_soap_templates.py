"""
tests/test_soap_templates.py

Validation tests for the deterministic SOAP template registry.

Purpose:
    This file protects the safety, structure, and maintainability of
    soap/soap_templates.py before templates are connected to SOAP generation.

Safety contract:
    - Templates must be deterministic.
    - Templates must contain wording only.
    - Templates must not contain hardcoded patient-specific facts.
    - Templates must not contain hardcoded clinical values.
    - Templates must not contain unsafe medical interpretation language.
    - Templates must use only approved placeholders from build_fact_context().
    - Templates must remain grouped by SOAP section and patient tier.

These tests intentionally validate the template registry before it affects
soap_generator.py or RAG ingestion.
"""

from __future__ import annotations

import re
import string
from collections import Counter
from typing import Any

import pytest

from soap.soap_contract import (
    ALLOWED_TEMPLATE_PLACEHOLDERS,
    EXPECTED_TEMPLATE_COUNTS,
    PATIENT_TIERS,
    SOAP_SECTIONS,
    SoapTemplate,
)
from soap.soap_safety import FORBIDDEN_CLINICAL_PHRASES
from soap.soap_templates import SOAP_TEMPLATES, TEMPLATE_VERSION, TOTAL_TEMPLATE_COUNT


EXPECTED_TOTAL_TEMPLATE_COUNT = 48


REQUIRED_PLACEHOLDERS_BY_SECTION: dict[str, set[str]] = {
    "subjective": {
        "age",
        "sex",
        "visit_type",
        "condition_text",
    },
    "objective": {
        "bp_systolic",
        "bp_diastolic",
        "heart_rate",
        "weight_kg",
        "bmi",
        "lab_text",
        "linked_documents_text",
    },
    "assessment": {
        "diagnosis_text",
    },
    "plan": {
        "medication_text",
        "prior_text",
    },
}


SAMPLE_FACT_CONTEXT: dict[str, Any] = {
    "patient_id": "PAT-MOD-003",
    "visit_id": "VST-MOD-003-004",
    "date_of_birth": "1968-06-01",
    "visit_date": "2024-06-15",
    "sex": "male",
    "visit_type": "follow_up",
    "age": 56,
    "condition_text": "T2DM, HTN",
    "diagnosis_text": "T2DM, HTN",
    "lab_text": "HbA1c 7.8 % (HIGH); FBG 148 mg/dL (HIGH)",
    "medication_text": "Metformin 500 mg twice_daily via oral",
    "linked_documents_text": "DOC-MOD-003-004",
    "prior_text": "Prior visit reference is VST-MOD-003-003.",
    "bp_systolic": 142,
    "bp_diastolic": 88,
    "bp_text": "142/88 mmHg",
    "heart_rate": 78,
    "weight_kg": 82.4,
    "bmi": 29.1,
}


HARDCODED_MEDICAL_TERMS_FORBIDDEN_IN_TEMPLATES = (
    "Metformin",
    "Glibenclamide",
    "Lisinopril",
    "Amlodipine",
    "Losartan",
    "Salbutamol inhaler",
    "Budesonide inhaler",
    "Ferrous sulfate",
    "Omeprazole",
    "HbA1c",
    "FBG",
    "Creatinine",
    "Hemoglobin",
    "Ferritin",
    "T2DM",
    "HTN",
    "Asthma",
    "IDA",
    "GERD",
    "CKD",
)


IDENTIFIER_PATTERNS_FORBIDDEN_IN_TEMPLATES = (
    re.compile(r"\bPAT-(NRM|MOD|CHR)-\d{3}\b"),
    re.compile(r"\bVST-(NRM|MOD|CHR)-\d{3}-\d{3}\b"),
    re.compile(r"\bDOC-(NRM|MOD|CHR)-\d{3}-\d{3}\b"),
)


NUMERIC_CLINICAL_VALUE_PATTERNS_FORBIDDEN_IN_TEMPLATES = (
    re.compile(r"\b\d{2,3}/\d{2,3}\s*mmHg\b"),
    re.compile(r"\b\d+(\.\d+)?\s*mg/dL\b"),
    re.compile(r"\b\d+(\.\d+)?\s*g/dL\b"),
    re.compile(r"\b\d+(\.\d+)?\s*ng/mL\b"),
    re.compile(r"\b\d+(\.\d+)?\s*%\b"),
)


def _iter_templates() -> list[SoapTemplate]:
    """Return all templates as a flat list for registry-wide tests."""
    return [
        template
        for section_templates in SOAP_TEMPLATES.values()
        for tier_templates in section_templates.values()
        for template in tier_templates
    ]


def _extract_placeholders(template_text: str) -> set[str]:
    """Extract Python format placeholders from a template string."""
    formatter = string.Formatter()
    placeholders: set[str] = set()

    for _, field_name, _, _ in formatter.parse(template_text):
        if field_name:
            placeholders.add(field_name)

    return placeholders


def _normalize_for_phrase_check(text: str) -> str:
    """Normalize text for case-insensitive forbidden phrase checks."""
    return " ".join(text.lower().split())


def test_template_version_is_locked_and_non_empty() -> None:
    """Template version must be explicit for deterministic regression tracking."""
    assert TEMPLATE_VERSION == "soap-templates-v1.0"


def test_total_template_count_is_expected() -> None:
    """The initial registry must contain exactly 48 templates."""
    assert TOTAL_TEMPLATE_COUNT == EXPECTED_TOTAL_TEMPLATE_COUNT


def test_all_required_soap_sections_exist() -> None:
    """The template registry must contain all four SOAP sections."""
    assert tuple(SOAP_TEMPLATES.keys()) == SOAP_SECTIONS
    assert SOAP_SECTIONS == (
        "subjective",
        "objective",
        "assessment",
        "plan",
    )


def test_all_required_patient_tiers_exist_for_each_section() -> None:
    """Every SOAP section must contain normal, moderate, and chronic tiers."""
    for section in SOAP_SECTIONS:
        assert tuple(SOAP_TEMPLATES[section].keys()) == PATIENT_TIERS

    assert PATIENT_TIERS == (
        "normal",
        "moderate",
        "chronic",
    )


def test_expected_template_count_per_tier_for_each_section() -> None:
    """
    Each section must use the planned tier-based template distribution.

    Expected:
        normal   -> 3 templates per section
        moderate -> 4 templates per section
        chronic  -> 5 templates per section
    """
    assert EXPECTED_TEMPLATE_COUNTS == {
        "normal": 3,
        "moderate": 4,
        "chronic": 5,
    }

    for section in SOAP_SECTIONS:
        for tier in PATIENT_TIERS:
            assert len(SOAP_TEMPLATES[section][tier]) == EXPECTED_TEMPLATE_COUNTS[tier]


def test_every_registry_entry_is_soap_template_instance() -> None:
    """All template entries must be immutable SoapTemplate instances."""
    for template in _iter_templates():
        assert isinstance(template, SoapTemplate)


def test_template_section_and_tier_match_registry_location() -> None:
    """Each template must declare the same section and tier as its registry path."""
    for section in SOAP_SECTIONS:
        for tier in PATIENT_TIERS:
            for template in SOAP_TEMPLATES[section][tier]:
                assert template.section == section
                assert template.tier == tier


def test_template_ids_are_unique() -> None:
    """Template IDs must be globally unique across the full registry."""
    template_ids = [template.template_id for template in _iter_templates()]
    duplicate_ids = [
        template_id
        for template_id, count in Counter(template_ids).items()
        if count > 1
    ]

    assert duplicate_ids == []


def test_template_ids_follow_expected_naming_pattern() -> None:
    """Template IDs must be stable and readable for debugging."""
    expected_pattern = re.compile(r"^(SUBJ|OBJ|ASM|PLAN)-(NRM|MOD|CHR)-\d{3}$")

    for template in _iter_templates():
        assert expected_pattern.match(template.template_id) is not None


def test_template_id_prefix_matches_section() -> None:
    """Template ID prefixes must match their SOAP section."""
    expected_prefix_by_section = {
        "subjective": "SUBJ",
        "objective": "OBJ",
        "assessment": "ASM",
        "plan": "PLAN",
    }

    for template in _iter_templates():
        expected_prefix = expected_prefix_by_section[template.section]
        assert template.template_id.startswith(f"{expected_prefix}-")


def test_template_id_tier_code_matches_tier() -> None:
    """Template ID tier code must match the declared patient tier."""
    expected_tier_code = {
        "normal": "NRM",
        "moderate": "MOD",
        "chronic": "CHR",
    }

    for template in _iter_templates():
        assert f"-{expected_tier_code[template.tier]}-" in template.template_id


def test_templates_are_non_empty_strings() -> None:
    """Every template text must be a non-empty string with no edge whitespace."""
    for template in _iter_templates():
        assert isinstance(template.text, str)
        assert template.text
        assert template.text == template.text.strip()


def test_templates_use_only_allowed_placeholders() -> None:
    """Templates must only use placeholders supported by build_fact_context()."""
    for template in _iter_templates():
        placeholders = _extract_placeholders(template.text)
        assert placeholders <= ALLOWED_TEMPLATE_PLACEHOLDERS


def test_templates_include_required_placeholders_for_their_section() -> None:
    """Each template must include the required placeholders for its SOAP section."""
    for template in _iter_templates():
        placeholders = _extract_placeholders(template.text)
        required = REQUIRED_PLACEHOLDERS_BY_SECTION[template.section]

        assert required <= placeholders


def test_templates_render_successfully_with_sample_fact_context() -> None:
    """Every template must render using the standard sample fact context."""
    for template in _iter_templates():
        rendered = template.text.format(**SAMPLE_FACT_CONTEXT)

        assert isinstance(rendered, str)
        assert rendered
        assert "{" not in rendered
        assert "}" not in rendered


def test_rendered_templates_preserve_fact_values_through_placeholders() -> None:
    """
    Rendered templates must include section-critical structured facts.

    This protects against templates that are grammatically valid but fail to
    include retrieval-important facts.
    """
    for template in _iter_templates():
        rendered = template.text.format(**SAMPLE_FACT_CONTEXT)

        if template.section == "subjective":
            assert "56" in rendered
            assert "male" in rendered
            assert "follow_up" in rendered
            assert "T2DM, HTN" in rendered

        if template.section == "objective":
            assert "142/88 mmHg" in rendered
            assert "78 bpm" in rendered
            assert "82.4 kg" in rendered
            assert "29.1" in rendered
            assert "HbA1c 7.8 % (HIGH); FBG 148 mg/dL (HIGH)" in rendered
            assert "DOC-MOD-003-004" in rendered

        if template.section == "assessment":
            assert "T2DM, HTN" in rendered

        if template.section == "plan":
            assert "Metformin 500 mg twice_daily via oral" in rendered
            assert "Prior visit reference is VST-MOD-003-003." in rendered


def test_templates_do_not_contain_forbidden_template_phrases() -> None:
    """Templates must not contain unsafe clinical interpretation phrases."""
    for template in _iter_templates():
        normalized_text = _normalize_for_phrase_check(template.text)

        for forbidden_phrase in FORBIDDEN_CLINICAL_PHRASES:
            assert forbidden_phrase not in normalized_text


def test_templates_do_not_contain_hardcoded_medical_terms() -> None:
    """
    Templates must not hardcode diagnoses, medications, or lab types.

    These values must always come from build_fact_context() placeholders.
    """
    for template in _iter_templates():
        for forbidden_term in HARDCODED_MEDICAL_TERMS_FORBIDDEN_IN_TEMPLATES:
            assert forbidden_term not in template.text


def test_templates_do_not_contain_hardcoded_patient_identifiers() -> None:
    """Templates must not hardcode patient, visit, or document IDs."""
    for template in _iter_templates():
        for pattern in IDENTIFIER_PATTERNS_FORBIDDEN_IN_TEMPLATES:
            assert pattern.search(template.text) is None


def test_templates_do_not_contain_hardcoded_numeric_clinical_values() -> None:
    """Templates must not hardcode BP, lab, or other clinical numeric values."""
    for template in _iter_templates():
        for pattern in NUMERIC_CLINICAL_VALUE_PATTERNS_FORBIDDEN_IN_TEMPLATES:
            assert pattern.search(template.text) is None


def test_templates_do_not_reference_llm_or_random_behavior() -> None:
    """Templates must not mention or imply LLM, random, or probabilistic behavior."""
    forbidden_terms = (
        "llm",
        "language model",
        "random",
        "probabilistic",
        "generated by ai",
    )

    for template in _iter_templates():
        normalized_text = _normalize_for_phrase_check(template.text)

        for forbidden_term in forbidden_terms:
            assert forbidden_term not in normalized_text


def test_template_registry_is_deterministic_across_reads() -> None:
    """Repeated reads of the registry must return the same template IDs in order."""
    first_read_ids = [template.template_id for template in _iter_templates()]
    second_read_ids = [template.template_id for template in _iter_templates()]

    assert first_read_ids == second_read_ids


def test_legacy_baseline_templates_exist_for_safe_migration() -> None:
    """
    Each SOAP section and tier must include a -001 baseline template.

    This provides a safe migration bridge from the Phase 1 fixed SOAP wording.
    """
    for section in SOAP_SECTIONS:
        for tier in PATIENT_TIERS:
            template_ids = {
                template.template_id
                for template in SOAP_TEMPLATES[section][tier]
            }

            if section == "subjective":
                prefix = "SUBJ"
            elif section == "objective":
                prefix = "OBJ"
            elif section == "assessment":
                prefix = "ASM"
            else:
                prefix = "PLAN"

            tier_code = {
                "normal": "NRM",
                "moderate": "MOD",
                "chronic": "CHR",
            }[tier]

            assert f"{prefix}-{tier_code}-001" in template_ids


def test_no_template_text_is_duplicated_within_same_section_and_tier() -> None:
    """
    Within each section-tier group, template texts should not be duplicated.

    This keeps diversification meaningful and prevents silent copy-paste mistakes.
    """
    for section in SOAP_SECTIONS:
        for tier in PATIENT_TIERS:
            texts = [
                template.text
                for template in SOAP_TEMPLATES[section][tier]
            ]
            duplicate_texts = [
                text
                for text, count in Counter(texts).items()
                if count > 1
            ]

            assert duplicate_texts == []


def test_all_templates_are_hashable_and_immutable_by_dataclass_contract() -> None:
    """
    SoapTemplate instances should be hashable due to frozen dataclass behavior.

    This supports deterministic use in tests, selectors, and debugging.
    """
    for template in _iter_templates():
        assert isinstance(hash(template), int)


def test_allowed_placeholder_set_contains_expected_fact_context_keys() -> None:
    """The placeholder allowlist must include keys required by current templates."""
    expected_required_keys = {
        "age",
        "sex",
        "visit_type",
        "condition_text",
        "diagnosis_text",
        "lab_text",
        "medication_text",
        "linked_documents_text",
        "prior_text",
        "bp_systolic",
        "bp_diastolic",
        "heart_rate",
        "weight_kg",
        "bmi",
    }

    assert expected_required_keys <= ALLOWED_TEMPLATE_PLACEHOLDERS


def test_template_registry_contains_no_unknown_sections_or_tiers() -> None:
    """Registry structure must remain limited to approved SOAP sections and tiers."""
    assert set(SOAP_TEMPLATES.keys()) == set(SOAP_SECTIONS)

    for section, section_templates in SOAP_TEMPLATES.items():
        assert section in SOAP_SECTIONS
        assert set(section_templates.keys()) == set(PATIENT_TIERS)

        for tier in section_templates:
            assert tier in PATIENT_TIERS


def test_each_template_group_order_is_stable() -> None:
    """
    Template ordering must be stable because deterministic selector indexes
    depend on tuple order.
    """
    expected_first_ids = {
        ("subjective", "normal"): "SUBJ-NRM-001",
        ("subjective", "moderate"): "SUBJ-MOD-001",
        ("subjective", "chronic"): "SUBJ-CHR-001",
        ("objective", "normal"): "OBJ-NRM-001",
        ("objective", "moderate"): "OBJ-MOD-001",
        ("objective", "chronic"): "OBJ-CHR-001",
        ("assessment", "normal"): "ASM-NRM-001",
        ("assessment", "moderate"): "ASM-MOD-001",
        ("assessment", "chronic"): "ASM-CHR-001",
        ("plan", "normal"): "PLAN-NRM-001",
        ("plan", "moderate"): "PLAN-MOD-001",
        ("plan", "chronic"): "PLAN-CHR-001",
    }

    for (section, tier), expected_template_id in expected_first_ids.items():
        assert SOAP_TEMPLATES[section][tier][0].template_id == expected_template_id


@pytest.mark.parametrize("section", SOAP_SECTIONS)
def test_each_section_has_templates_for_all_tiers(section: str) -> None:
    """Parametrized section coverage check for maintainability."""
    assert set(SOAP_TEMPLATES[section].keys()) == set(PATIENT_TIERS)


@pytest.mark.parametrize("tier", PATIENT_TIERS)
def test_each_tier_has_templates_for_all_sections(tier: str) -> None:
    """Parametrized tier coverage check for maintainability."""
    for section in SOAP_SECTIONS:
        assert len(SOAP_TEMPLATES[section][tier]) == EXPECTED_TEMPLATE_COUNTS[tier]