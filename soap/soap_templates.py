"""
soap/soap_templates.py

Deterministic v1.7 Lite SOAP template registry.

Purpose:
    Store approved deterministic SOAP templates for diversified, retrieval-aware
    SOAP generation.

v1.7 Lite alignment:
    SOAP notes are narrative only. Medical truth must come only from structured
    patient JSON and rendered fact context. This registry provides wording
    diversity through the three controlled SOAP styles:

    - concise
    - problem_oriented
    - timeline_oriented

Safety contract:
    - Templates contain wording only.
    - Templates do not calculate medical values.
    - Templates do not infer diagnoses.
    - Templates do not select medications.
    - Templates do not select labs.
    - Templates do not modify structured facts.
    - Templates do not contain real patient data.
    - Templates do not contain hardcoded clinical values.
    - Templates do not contain hardcoded medication names, diagnosis names,
      lab values, patient IDs, visit IDs, document IDs, allergen names, or BP
      numeric values.
    - Templates do not call LLMs.
    - Templates do not use randomization.

Important:
    The medical truth must continue to come only from structured patient JSON
    through the fact context built by soap_semantics.py / soap_renderers.py.

Architecture:
    soap_contract.py   -> owns shared SOAP sections/types/template dataclass
    soap_safety.py     -> owns shared SOAP safety phrase constants
    soap_semantics.py  -> owns condition-aware semantic phrase construction
    soap_renderers.py  -> owns fact extraction and exact formatting
    soap_templates.py  -> owns template registry only
    soap_selector.py   -> owns deterministic template selection
    soap_generator.py  -> owns final SOAP assembly
    soap_auditor.py    -> owns safety checks

Template grouping:
    section -> tier -> templates

Supported sections:
    - subjective
    - objective
    - assessment
    - plan

Supported tiers:
    - normal
    - moderate
    - chronic

Template count:
    - normal:   3 templates per SOAP section
    - moderate: 4 templates per SOAP section
    - chronic:  5 templates per SOAP section

Total:
    48 templates.
"""

from __future__ import annotations

from string import Formatter
from typing import Final, Mapping

from soap.soap_contract import (
    ALLOWED_TEMPLATE_PLACEHOLDERS,
    EXPECTED_TEMPLATE_COUNT_PER_SECTION_BY_TIER,
    EXPECTED_TEMPLATE_COUNT_PER_STYLE_BY_SECTION,
    EXPECTED_TOTAL_TEMPLATE_COUNT,
    PATIENT_TIERS,
    SOAP_SECTIONS,
    SOAP_STYLES,
    PatientTier,
    SoapSection,
    SoapStyle,
    SoapTemplate,
)


TEMPLATE_VERSION: Final[str] = "soap-templates-v1.7-lite"


# ---------------------------------------------------------------------
# Template distribution
# ---------------------------------------------------------------------

# Distribution is intentionally balanced per SOAP section:
#   normal   -> 1 concise, 1 problem_oriented, 1 timeline_oriented
#   moderate -> 1 concise, 2 problem_oriented, 1 timeline_oriented
#   chronic  -> 2 concise, 1 problem_oriented, 2 timeline_oriented
# Total per section: 4 concise, 4 problem_oriented, 4 timeline_oriented.
STYLE_DISTRIBUTION_BY_TIER: Final[Mapping[PatientTier, tuple[SoapStyle, ...]]] = {
    "normal": ("concise", "problem_oriented", "timeline_oriented"),
    "moderate": (
        "concise",
        "problem_oriented",
        "problem_oriented",
        "timeline_oriented",
    ),
    "chronic": (
        "concise",
        "concise",
        "problem_oriented",
        "timeline_oriented",
        "timeline_oriented",
    ),
}

SECTION_CODE: Final[Mapping[SoapSection, str]] = {
    "subjective": "SUBJ",
    "objective": "OBJ",
    "assessment": "ASM",
    "plan": "PLAN",
}

TIER_CODE: Final[Mapping[PatientTier, str]] = {
    "normal": "NRM",
    "moderate": "MOD",
    "chronic": "CHR",
}

STYLE_CODE: Final[Mapping[SoapStyle, str]] = {
    "concise": "CON",
    "problem_oriented": "PROB",
    "timeline_oriented": "TIME",
}


# ---------------------------------------------------------------------
# Style-specific text banks
# ---------------------------------------------------------------------

TEXT_VARIANTS: Final[
    Mapping[SoapSection, Mapping[SoapStyle, tuple[str, str, str, str]]]
] = {
    "subjective": {
        "concise": (
            (
                "The chart records a {age}-year-old {sex} patient at a "
                "{visit_type} visit. Conditions: {condition_text}. "
                "{visit_role_text} {clinical_event_text}"
            ),
            (
                "This {visit_type} note describes a {age}-year-old {sex} "
                "patient. Documented conditions are {condition_text}. "
                "{condition_focus_text} {visit_context_text}"
            ),
            (
                "The encounter concerns a {age}-year-old {sex} patient with "
                "recorded conditions: {condition_text}. {visit_role_text} "
                "{retrieval_focus_text}"
            ),
            (
                "For this {visit_type} encounter, the record identifies a "
                "{age}-year-old {sex} patient. Conditions listed: "
                "{condition_text}. {clinical_event_text} {retrieval_focus_text}"
            ),
        ),
        "problem_oriented": (
            (
                "The subjective section frames the documented problem context "
                "for a {age}-year-old {sex} patient. Conditions in the record: "
                "{condition_text}. {condition_focus_text} {primary_evidence_text}"
            ),
            (
                "This visit is organized around the charted clinical focus. "
                "The patient is a {age}-year-old {sex}; recorded conditions are "
                "{condition_text}. {visit_role_text} {clinical_event_text}"
            ),
            (
                "Problem context for this {visit_type} encounter is limited to "
                "the structured record. Conditions: {condition_text}. "
                "{condition_focus_text} {retrieval_intent_tags_text}"
            ),
            (
                "The note describes the documented issue for this visit without "
                "adding new symptoms or diagnoses. Patient context: {age}-year-old "
                "{sex}; conditions: {condition_text}. {clinical_event_text} "
                "{retrieval_focus_text}"
            ),
        ),
        "timeline_oriented": (
            (
                "The timeline context places this {visit_type} visit in the "
                "patient record for a {age}-year-old {sex}. Conditions: "
                "{condition_text}. {timeline_context_text} {visit_role_text}"
            ),
            (
                "At this point in the documented timeline, the chart records a "
                "{visit_type} visit for a {age}-year-old {sex} patient. "
                "Conditions: {condition_text}. {timeline_context_text} "
                "{clinical_event_text}"
            ),
            (
                "This encounter is described as part of the longitudinal record. "
                "The patient is {age} years old and {sex}; conditions are "
                "{condition_text}. {timeline_context_text} {retrieval_focus_text}"
            ),
            (
                "Compared with the surrounding record context, this {visit_type} "
                "visit is documented with conditions {condition_text}. "
                "{timeline_context_text} {visit_role_text} {clinical_event_text}"
            ),
        ),
    },
    "objective": {
        "concise": (
            (
                "Objective data are documented as {bp_text}; heart rate "
                "{heart_rate} bpm; weight {weight_kg} kg; BMI {bmi}. Labs: "
                "{lab_text}. {monitoring_focus_text} Linked documents: "
                "{linked_documents_text}."
            ),
            (
                "Recorded measurements include {bp_text}, heart rate "
                "{heart_rate} bpm, weight {weight_kg} kg, and BMI {bmi}. "
                "Laboratory entries: {lab_text}. {lab_trend_text} "
                "Linked documents: {linked_documents_text}."
            ),
            (
                "The objective record lists {bp_text}; heart rate {heart_rate} "
                "bpm; weight {weight_kg} kg; BMI {bmi}. Lab record: "
                "{lab_text}. {monitoring_focus_text} Linked documents: "
                "{linked_documents_text}."
            ),
            (
                "Vitals and labs for this encounter are recorded as follows: "
                "{bp_text}; heart rate {heart_rate} bpm; weight {weight_kg} kg; "
                "BMI {bmi}; labs: {lab_text}. {lab_trend_text} Linked documents: "
                "{linked_documents_text}."
            ),
        ),
        "problem_oriented": (
            (
                "Objective findings are presented around the documented clinical "
                "focus. Vitals: {bp_text}; heart rate {heart_rate} bpm; weight "
                "{weight_kg} kg; BMI {bmi}. Labs: {lab_text}. "
                "{monitoring_focus_text} {primary_evidence_text}"
            ),
            (
                "The visit objective data support the charted problem context: "
                "{bp_text}; heart rate {heart_rate} bpm; weight {weight_kg} kg; "
                "BMI {bmi}. Lab entries: {lab_text}. {lab_trend_text} "
                "Linked documents: {linked_documents_text}."
            ),
            (
                "Structured measurements for the documented issue include "
                "{bp_text}, heart rate {heart_rate} bpm, weight {weight_kg} kg, "
                "and BMI {bmi}. Laboratory evidence: {lab_text}. "
                "{monitoring_focus_text} {retrieval_focus_text}"
            ),
            (
                "The objective section keeps evidence tied to structured fields: "
                "{bp_text}; heart rate {heart_rate} bpm; weight {weight_kg} kg; "
                "BMI {bmi}. Labs: {lab_text}. {lab_trend_text} "
                "Linked documents: {linked_documents_text}."
            ),
        ),
        "timeline_oriented": (
            (
                "At this timeline point, objective data record {bp_text}, heart "
                "rate {heart_rate} bpm, weight {weight_kg} kg, and BMI {bmi}. "
                "Labs: {lab_text}. {timeline_context_text} {lab_trend_text}"
            ),
            (
                "For the current visit in sequence, measurements include "
                "{bp_text}; heart rate {heart_rate} bpm; weight {weight_kg} kg; "
                "BMI {bmi}. Laboratory record: {lab_text}. "
                "{timeline_context_text} Linked documents: {linked_documents_text}."
            ),
            (
                "The longitudinal objective record for this encounter includes "
                "{bp_text}, heart rate {heart_rate} bpm, weight {weight_kg} kg, "
                "and BMI {bmi}. Labs: {lab_text}. {lab_trend_text} "
                "{monitoring_focus_text}"
            ),
            (
                "Objective evidence at this visit is recorded as {bp_text}; "
                "heart rate {heart_rate} bpm; weight {weight_kg} kg; BMI {bmi}. "
                "Labs: {lab_text}. {timeline_context_text} {primary_evidence_text}"
            ),
        ),
    },
    "assessment": {
        "concise": (
            (
                "Assessment is limited to diagnoses documented for this visit: "
                "{diagnosis_text}. {diagnosis_focus_text} {clinical_event_text}"
            ),
            (
                "The diagnosis summary for this encounter is {diagnosis_text}. "
                "{diagnosis_focus_text} {condition_focus_text}"
            ),
            (
                "Recorded assessment: {diagnosis_text}. {clinical_event_text} "
                "{primary_evidence_text}"
            ),
            (
                "The visit assessment lists {diagnosis_text}. "
                "{diagnosis_focus_text} {retrieval_focus_text}"
            ),
        ),
        "problem_oriented": (
            (
                "The assessment connects the documented diagnosis list to the "
                "charted problem focus: {diagnosis_text}. {diagnosis_focus_text} "
                "{condition_focus_text}"
            ),
            (
                "Problem-oriented assessment remains limited to recorded diagnoses: "
                "{diagnosis_text}. {clinical_event_text} {primary_evidence_text}"
            ),
            (
                "The current clinical focus is summarized from structured facts only. "
                "Diagnoses: {diagnosis_text}. {diagnosis_focus_text} "
                "{monitoring_focus_text}"
            ),
            (
                "Assessment emphasizes the documented issue without adding new "
                "conditions. Visit diagnoses: {diagnosis_text}. "
                "{clinical_event_text} {retrieval_focus_text}"
            ),
        ),
        "timeline_oriented": (
            (
                "In the visit timeline, assessment records {diagnosis_text}. "
                "{timeline_context_text} {clinical_event_text}"
            ),
            (
                "This assessment is placed within the longitudinal record. "
                "Documented diagnoses: {diagnosis_text}. {timeline_context_text} "
                "{diagnosis_focus_text}"
            ),
            (
                "Across the documented sequence, this encounter lists diagnoses as "
                "{diagnosis_text}. {clinical_event_text} {primary_evidence_text}"
            ),
            (
                "The timeline-oriented assessment records only the visit diagnoses: "
                "{diagnosis_text}. {timeline_context_text} {retrieval_focus_text}"
            ),
        ),
    },
    "plan": {
        "concise": (
            (
                "Plan data list medication entries as documented: {medication_text}. "
                "{medication_focus_text} {prior_text} {allergy_context_text}"
            ),
            (
                "The plan keeps medication information in recorded form: "
                "{medication_text}. {medication_trajectory_text} {prior_text}"
            ),
            (
                "Medication entries for this visit are documented as "
                "{medication_text}. {medication_focus_text} {allergy_context_text}"
            ),
            (
                "Recorded plan information: {medication_text}. "
                "{medication_trajectory_text} {prior_text} {retrieval_focus_text}"
            ),
        ),
        "problem_oriented": (
            (
                "The plan section is tied to documented medication facts only: "
                "{medication_text}. {medication_focus_text} "
                "{medication_trajectory_text} {allergy_context_text}"
            ),
            (
                "Problem-oriented plan wording preserves the recorded medication "
                "entries: {medication_text}. {medication_focus_text} {prior_text}"
            ),
            (
                "Medication context for the documented issue is recorded as "
                "{medication_text}. {medication_trajectory_text} "
                "{retrieval_focus_text} {allergy_context_text}"
            ),
            (
                "The plan does not introduce new treatment instructions; it records "
                "medication data as {medication_text}. {medication_focus_text} "
                "{prior_text}"
            ),
        ),
        "timeline_oriented": (
            (
                "Within the timeline, plan data record medications as "
                "{medication_text}. {medication_trajectory_text} "
                "{timeline_context_text} {prior_text}"
            ),
            (
                "At this visit point, medication information remains grounded in the "
                "record: {medication_text}. {medication_trajectory_text} "
                "{allergy_context_text}"
            ),
            (
                "The longitudinal medication context is documented as "
                "{medication_text}. {medication_trajectory_text} "
                "{timeline_context_text} {retrieval_focus_text}"
            ),
            (
                "Compared with prior record context, the plan lists only documented "
                "medication entries: {medication_text}. {prior_text} "
                "{medication_trajectory_text} {allergy_context_text}"
            ),
        ),
    },
}


# ---------------------------------------------------------------------
# Registry construction
# ---------------------------------------------------------------------


def _build_templates_for_section(section: SoapSection) -> Mapping[PatientTier, tuple[SoapTemplate, ...]]:
    """Build deterministic templates for one SOAP section."""
    style_variant_index: dict[SoapStyle, int] = {style: 0 for style in SOAP_STYLES}
    section_templates: dict[PatientTier, tuple[SoapTemplate, ...]] = {}

    for tier in PATIENT_TIERS:
        built: list[SoapTemplate] = []
        for ordinal, style in enumerate(STYLE_DISTRIBUTION_BY_TIER[tier], start=1):
            variant_index = style_variant_index[style]
            text = TEXT_VARIANTS[section][style][variant_index]
            style_variant_index[style] = variant_index + 1

            built.append(
                SoapTemplate(
                    template_id=(
                        f"{SECTION_CODE[section]}-{TIER_CODE[tier]}-"
                        f"{STYLE_CODE[style]}-{ordinal:03d}"
                    ),
                    section=section,
                    tier=tier,
                    text=text,
                    style=style,
                )
            )

        section_templates[tier] = tuple(built)

    return section_templates


SOAP_TEMPLATES: Final[
    Mapping[SoapSection, Mapping[PatientTier, tuple[SoapTemplate, ...]]]
] = {section: _build_templates_for_section(section) for section in SOAP_SECTIONS}


TOTAL_TEMPLATE_COUNT: Final[int] = sum(
    len(tier_templates)
    for section_templates in SOAP_TEMPLATES.values()
    for tier_templates in section_templates.values()
)


# ---------------------------------------------------------------------
# Lightweight registry inspection helpers for tests
# ---------------------------------------------------------------------


def iter_templates() -> tuple[SoapTemplate, ...]:
    """Return all templates in deterministic section/tier order."""
    return tuple(
        template
        for section in SOAP_SECTIONS
        for tier in PATIENT_TIERS
        for template in SOAP_TEMPLATES[section][tier]
    )


def count_templates_by_section_tier() -> dict[SoapSection, dict[PatientTier, int]]:
    """Return template counts by section and tier."""
    return {
        section: {tier: len(SOAP_TEMPLATES[section][tier]) for tier in PATIENT_TIERS}
        for section in SOAP_SECTIONS
    }


def count_templates_by_section_style() -> dict[SoapSection, dict[SoapStyle, int]]:
    """Return template counts by section and style."""
    counts: dict[SoapSection, dict[SoapStyle, int]] = {
        section: {style: 0 for style in SOAP_STYLES} for section in SOAP_SECTIONS
    }
    for template in iter_templates():
        counts[template.section][template.style] += 1
    return counts


def extract_template_placeholders(template_text: str) -> frozenset[str]:
    """Extract format placeholders used by a template string."""
    return frozenset(
        field_name
        for _, field_name, _, _ in Formatter().parse(template_text)
        if field_name
    )


def validate_template_registry() -> tuple[str, ...]:
    """
    Validate registry structure without performing SOAP generation.

    This helper is intended for tests and smoke checks. It does not select a
    template, render text, inspect patient records, or perform audit logic.
    """
    errors: list[str] = []
    templates = iter_templates()

    if TOTAL_TEMPLATE_COUNT != EXPECTED_TOTAL_TEMPLATE_COUNT:
        errors.append(
            f"Expected {EXPECTED_TOTAL_TEMPLATE_COUNT} templates; "
            f"found {TOTAL_TEMPLATE_COUNT}."
        )

    if len({template.template_id for template in templates}) != len(templates):
        errors.append("Template IDs must be unique.")

    for section in SOAP_SECTIONS:
        for tier in PATIENT_TIERS:
            expected = EXPECTED_TEMPLATE_COUNT_PER_SECTION_BY_TIER[tier]
            actual = len(SOAP_TEMPLATES[section][tier])
            if actual != expected:
                errors.append(
                    f"{section}/{tier} expected {expected} templates; found {actual}."
                )

    style_counts = count_templates_by_section_style()
    for section in SOAP_SECTIONS:
        for style in SOAP_STYLES:
            expected = EXPECTED_TEMPLATE_COUNT_PER_STYLE_BY_SECTION[style]
            actual = style_counts[section][style]
            if actual != expected:
                errors.append(
                    f"{section}/{style} expected {expected} templates; found {actual}."
                )

    for template in templates:
        if template.section not in SOAP_SECTIONS:
            errors.append(f"{template.template_id} has invalid section {template.section!r}.")
        if template.tier not in PATIENT_TIERS:
            errors.append(f"{template.template_id} has invalid tier {template.tier!r}.")
        if template.style not in SOAP_STYLES:
            errors.append(f"{template.template_id} has invalid style {template.style!r}.")

        unknown = extract_template_placeholders(template.text) - ALLOWED_TEMPLATE_PLACEHOLDERS
        if unknown:
            errors.append(
                f"{template.template_id} contains unknown placeholders: "
                f"{', '.join(sorted(unknown))}."
            )

    return tuple(errors)


__all__ = (
    "SOAP_TEMPLATES",
    "TEMPLATE_VERSION",
    "TOTAL_TEMPLATE_COUNT",
    "STYLE_DISTRIBUTION_BY_TIER",
    "TEXT_VARIANTS",
    "iter_templates",
    "count_templates_by_section_tier",
    "count_templates_by_section_style",
    "extract_template_placeholders",
    "validate_template_registry",
)
