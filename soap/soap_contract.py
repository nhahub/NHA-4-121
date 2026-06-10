"""
soap/soap_contract.py

Shared SOAP contract definitions for the deterministic SOAP layer.

Purpose:
    Define the stable SOAP-local contract used by the deterministic SOAP
    template registry, selector, generator, auditor, semantic context layer,
    renderers, and SOAP tests.

v1.7 Lite alignment:
    SOAP notes are narrative only. They must be generated from structured
    patient and visit facts, while supporting controlled style diversity for
    retrieval quality.

This module intentionally contains only shared structure, types, and constants.

It must not contain:
    - SOAP template text
    - template selection logic
    - SHA-256 logic
    - rendering logic
    - semantic text construction
    - fact extraction
    - lab formatting
    - medication formatting
    - audit checks
    - LLM calls
    - randomization
    - imports from other SOAP modules
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, Mapping


# ---------------------------------------------------------------------
# Core SOAP types
# ---------------------------------------------------------------------

SoapSection = Literal["subjective", "objective", "assessment", "plan"]
PatientTier = Literal["normal", "moderate", "chronic"]
SoapStyle = Literal["concise", "problem_oriented", "timeline_oriented"]

TimelinePattern = Literal[
    "regular_quarterly",
    "delayed_followup",
    "irregular_followup",
    "seasonal_exacerbation",
    "post_hospitalization",
]

SemanticFocus = Literal[
    "recovery",
    "lab_improvement",
    "poor_adherence",
    "medication_escalation",
    "symptom_control",
    "hospitalization_recovery",
    "ckd_monitoring",
    "dual_lab_trend",
    "dual_condition_control",
    "acute_treatment_completion",
]

VisitRole = Literal[
    "initial_diagnosis",
    "baseline_assessment",
    "routine_follow_up",
    "partial_adherence",
    "poor_adherence",
    "lab_trend_review",
    "medication_started",
    "medication_continued",
    "dose_adjustment",
    "second_medication_added",
    "acute_treatment_started",
    "course_completed",
    "symptom_flare",
    "symptom_control_review",
    "emergency_exacerbation",
    "hospitalization",
    "post_discharge_stabilization",
    "ckd_monitoring",
    "medication_reconciliation",
    "recovery_confirmed",
]

ClinicalEventType = Literal[
    "diagnosis_documented",
    "baseline_labs_reviewed",
    "lab_improvement",
    "lab_worsening",
    "adherence_issue",
    "medication_started",
    "medication_continued",
    "dose_adjustment",
    "medication_added",
    "short_course_completed",
    "symptom_flare",
    "symptom_improvement",
    "emergency_visit",
    "hospitalization",
    "post_discharge_review",
    "allergy_reviewed",
    "recovery_confirmed",
]


SOAP_SECTIONS: Final[tuple[SoapSection, ...]] = (
    "subjective",
    "objective",
    "assessment",
    "plan",
)

PATIENT_TIERS: Final[tuple[PatientTier, ...]] = (
    "normal",
    "moderate",
    "chronic",
)

SOAP_STYLES: Final[tuple[SoapStyle, ...]] = (
    "concise",
    "problem_oriented",
    "timeline_oriented",
)

TIMELINE_PATTERNS: Final[tuple[TimelinePattern, ...]] = (
    "regular_quarterly",
    "delayed_followup",
    "irregular_followup",
    "seasonal_exacerbation",
    "post_hospitalization",
)

SEMANTIC_FOCUS_VALUES: Final[tuple[SemanticFocus, ...]] = (
    "recovery",
    "lab_improvement",
    "poor_adherence",
    "medication_escalation",
    "symptom_control",
    "hospitalization_recovery",
    "ckd_monitoring",
    "dual_lab_trend",
    "dual_condition_control",
    "acute_treatment_completion",
)

VISIT_ROLES: Final[tuple[VisitRole, ...]] = (
    "initial_diagnosis",
    "baseline_assessment",
    "routine_follow_up",
    "partial_adherence",
    "poor_adherence",
    "lab_trend_review",
    "medication_started",
    "medication_continued",
    "dose_adjustment",
    "second_medication_added",
    "acute_treatment_started",
    "course_completed",
    "symptom_flare",
    "symptom_control_review",
    "emergency_exacerbation",
    "hospitalization",
    "post_discharge_stabilization",
    "ckd_monitoring",
    "medication_reconciliation",
    "recovery_confirmed",
)

CLINICAL_EVENT_TYPES: Final[tuple[ClinicalEventType, ...]] = (
    "diagnosis_documented",
    "baseline_labs_reviewed",
    "lab_improvement",
    "lab_worsening",
    "adherence_issue",
    "medication_started",
    "medication_continued",
    "dose_adjustment",
    "medication_added",
    "short_course_completed",
    "symptom_flare",
    "symptom_improvement",
    "emergency_visit",
    "hospitalization",
    "post_discharge_review",
    "allergy_reviewed",
    "recovery_confirmed",
)


# ---------------------------------------------------------------------
# Template contract
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class SoapTemplate:
    """
    Approved deterministic SOAP template definition.

    Attributes:
        template_id:
            Stable unique identifier for the template.
        section:
            SOAP section where the template is used.
        tier:
            Patient tier group where the template is allowed.
        text:
            Template text containing only approved placeholders.
        style:
            v1.7 Lite SOAP style target. The default keeps old four-argument
            SoapTemplate construction backward-compatible.

    Safety rule:
        Template text must never contain hardcoded medical facts such as
        medication names, lab values, BP values, diagnoses, allergens, or
        patient-specific identifiers. These must always come from the structured
        fact context.
    """

    template_id: str
    section: SoapSection
    tier: PatientTier
    text: str
    style: SoapStyle = "concise"


@dataclass(frozen=True)
class SoapTemplateKey:
    """
    Stable routing key for selecting a SOAP template.

    Selection logic belongs in soap_selector.py, not in this module.
    """

    section: SoapSection
    tier: PatientTier
    style: SoapStyle


@dataclass(frozen=True)
class SoapGenerationContext:
    """
    Minimal structured context required by the SOAP generator/renderer.

    This object defines expected context shape only. Building it from patient
    JSON belongs in soap_renderers.py.
    """

    patient_id: str
    visit_id: str
    tier: PatientTier
    soap_style: SoapStyle
    visit_role: str
    semantic_focus: str
    timeline_pattern: str
    clinical_event_type: str
    clinical_event_label: str
    clinical_event_summary: str


# ---------------------------------------------------------------------
# Template placeholders
# ---------------------------------------------------------------------

CORE_TEMPLATE_PLACEHOLDERS: Final[frozenset[str]] = frozenset(
    {
        # Identifiers
        "patient_id",
        "visit_id",

        # Patient and visit routing facts
        "tier",
        "dataset_version",
        "story_arc",
        "visit_type",
        "soap_style",
        "visit_role",
        "semantic_focus",
        "timeline_pattern",
        "visit_timeline_pattern",
        "timeline_gap_days",
        "retrieval_signature",

        # Clinical event facts from visit.clinical_event
        "clinical_event_type",
        "clinical_event_label",
        "clinical_event_summary",

        # Demographic and visit facts
        "date_of_birth",
        "visit_date",
        "sex",
        "age",

        # Rendered patient / visit facts
        "condition_text",
        "diagnosis_text",
        "lab_text",
        "medication_text",
        "allergy_text",
        "linked_documents_text",
        "prior_text",

        # Rendered / directly accessed vital components
        "bp_systolic",
        "bp_diastolic",
        "bp_text",
        "heart_rate",
        "weight_kg",
        "bmi",
    }
)


SEMANTIC_TEMPLATE_PLACEHOLDERS: Final[frozenset[str]] = frozenset(
    {
        # Deterministic semantic context generated from documented facts only.
        "condition_focus_text",
        "diagnosis_focus_text",
        "monitoring_focus_text",
        "medication_focus_text",
        "visit_context_text",
        "visit_role_text",
        "timeline_context_text",
        "clinical_event_text",
        "retrieval_focus_text",
        "retrieval_intent_tags_text",
        "primary_evidence_text",
        "lab_trend_text",
        "medication_trajectory_text",
        "allergy_context_text",
        "semantic_focus_text",
    }
)


ALLOWED_TEMPLATE_PLACEHOLDERS: Final[frozenset[str]] = (
    CORE_TEMPLATE_PLACEHOLDERS | SEMANTIC_TEMPLATE_PLACEHOLDERS
)


# ---------------------------------------------------------------------
# Required rendered facts by SOAP section
# ---------------------------------------------------------------------

REQUIRED_FACTS_BY_SECTION: Final[Mapping[SoapSection, tuple[str, ...]]] = {
    # Hard clinical facts only. Retrieval/context wording is optional because
    # diversified templates do not all render the same semantic placeholders.
    "subjective": ("condition_text",),
    "objective": ("bp_text", "lab_text"),
    "assessment": ("diagnosis_text",),
    "plan": ("medication_text",),
}


OPTIONAL_RETRIEVAL_FACTS_BY_SECTION: Final[Mapping[SoapSection, tuple[str, ...]]] = {
    "subjective": (
        "visit_context_text",
        "visit_role_text",
        "retrieval_focus_text",
    ),
    "objective": (
        "linked_documents_text",
        "monitoring_focus_text",
        "lab_trend_text",
    ),
    "assessment": (
        "condition_focus_text",
        "diagnosis_focus_text",
        "clinical_event_text",
        "primary_evidence_text",
        "semantic_focus_text",
    ),
    "plan": (
        "prior_text",
        "medication_focus_text",
        "medication_trajectory_text",
        "allergy_context_text",
    ),
}


# ---------------------------------------------------------------------
# Required input contract from patient JSON
# ---------------------------------------------------------------------

REQUIRED_PATIENT_CONTEXT_FIELDS: Final[tuple[str, ...]] = (
    "patient_id",
    "demographics",
    "conditions",
    "allergy_registry",
    "visits",
    "metadata",
)

REQUIRED_PATIENT_METADATA_FIELDS_FOR_SOAP: Final[tuple[str, ...]] = (
    "tier",
    "story_arc",
    "timeline_pattern",
    "semantic_focus",
    "retrieval_signature",
    "retrieval_intent_tags",
    "soap_style",
)

REQUIRED_VISIT_CONTEXT_FIELDS_FOR_SOAP: Final[tuple[str, ...]] = (
    "visit_id",
    "visit_date",
    "visit_type",
    "visit_role",
    "timeline_pattern",
    "timeline_gap_days",
    "clinical_event",
    "retrieval_context",
    "diagnoses",
    "vitals",
    "labs",
    "medications",
    "linked_documents",
    "prior_visit_id",
)

REQUIRED_CLINICAL_EVENT_FIELDS_FOR_SOAP: Final[tuple[str, ...]] = (
    "event_type",
    "event_label",
    "event_summary",
)

REQUIRED_RETRIEVAL_CONTEXT_FIELDS_FOR_SOAP: Final[tuple[str, ...]] = (
    "semantic_focus",
    "retrieval_intent_tags",
)


# ---------------------------------------------------------------------
# Template registry expectations
# ---------------------------------------------------------------------

EXPECTED_TEMPLATE_COUNT_PER_SECTION_BY_TIER: Final[Mapping[PatientTier, int]] = {
    "normal": 3,
    "moderate": 4,
    "chronic": 5,
}

EXPECTED_TEMPLATE_COUNT_PER_STYLE_BY_SECTION: Final[Mapping[SoapStyle, int]] = {
    "concise": 4,
    "problem_oriented": 4,
    "timeline_oriented": 4,
}

EXPECTED_TOTAL_TEMPLATE_COUNT: Final[int] = 48


# ---------------------------------------------------------------------
# Safety / output contract constants
# ---------------------------------------------------------------------

FORBIDDEN_TEMPLATE_FACT_CATEGORIES: Final[tuple[str, ...]] = (
    "hardcoded_patient_id",
    "hardcoded_medication_name",
    "hardcoded_diagnosis",
    "hardcoded_lab_value",
    "hardcoded_bp_value",
    "hardcoded_allergen",
    "hardcoded_treatment_plan",
)

SOAP_NOTE_FIELD: Final[str] = "soap_note"

EMPTY_SOAP_NOTE: Final[Mapping[SoapSection, str]] = {
    "subjective": "",
    "objective": "",
    "assessment": "",
    "plan": "",
}


__all__ = (
    # Types
    "SoapSection",
    "PatientTier",
    "SoapStyle",
    "TimelinePattern",
    "SemanticFocus",
    "VisitRole",
    "ClinicalEventType",
    # Dataclasses
    "SoapTemplate",
    "SoapTemplateKey",
    "SoapGenerationContext",
    # Core values
    "SOAP_SECTIONS",
    "PATIENT_TIERS",
    "SOAP_STYLES",
    "TIMELINE_PATTERNS",
    "SEMANTIC_FOCUS_VALUES",
    "VISIT_ROLES",
    "CLINICAL_EVENT_TYPES",
    # Placeholders
    "CORE_TEMPLATE_PLACEHOLDERS",
    "SEMANTIC_TEMPLATE_PLACEHOLDERS",
    "ALLOWED_TEMPLATE_PLACEHOLDERS",
    # Required facts / input contracts
    "REQUIRED_FACTS_BY_SECTION",
    "OPTIONAL_RETRIEVAL_FACTS_BY_SECTION",
    "REQUIRED_PATIENT_CONTEXT_FIELDS",
    "REQUIRED_PATIENT_METADATA_FIELDS_FOR_SOAP",
    "REQUIRED_VISIT_CONTEXT_FIELDS_FOR_SOAP",
    "REQUIRED_CLINICAL_EVENT_FIELDS_FOR_SOAP",
    "REQUIRED_RETRIEVAL_CONTEXT_FIELDS_FOR_SOAP",
    # Template expectations
    "EXPECTED_TEMPLATE_COUNT_PER_SECTION_BY_TIER",
    "EXPECTED_TEMPLATE_COUNT_PER_STYLE_BY_SECTION",
    "EXPECTED_TOTAL_TEMPLATE_COUNT",
    # Safety / output contract
    "FORBIDDEN_TEMPLATE_FACT_CATEGORIES",
    "SOAP_NOTE_FIELD",
    "EMPTY_SOAP_NOTE",
)
