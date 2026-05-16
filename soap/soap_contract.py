"""
soap/soap_contract.py

Shared SOAP contract definitions.

Purpose:
    Define the stable SOAP-local contract used by the deterministic SOAP
    template registry, selector, generator, auditor, and SOAP tests.

This module intentionally contains only shared structure, types, and constants.

It must not contain:
    - SOAP template text
    - template selection logic
    - SHA-256 logic
    - rendering logic
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


SoapSection = Literal["subjective", "objective", "assessment", "plan"]
PatientTier = Literal["normal", "moderate", "chronic"]


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

    Safety rule:
        Template text must never contain hardcoded medical facts such as
        medication names, lab values, BP values, diagnoses, or patient-specific
        identifiers. These must always come from build_fact_context().
    """

    template_id: str
    section: SoapSection
    tier: PatientTier
    text: str


ALLOWED_TEMPLATE_PLACEHOLDERS: Final[frozenset[str]] = frozenset(
    {
        # Identifiers
        "patient_id",
        "visit_id",

        # Visit routing / selection facts
        "tier",
        "visit_type",

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


REQUIRED_FACTS_BY_SECTION: Final[Mapping[SoapSection, tuple[str, ...]]] = {
    "subjective": ("condition_text",),
    "objective": ("bp_text", "lab_text", "linked_documents_text"),
    "assessment": ("diagnosis_text",),
    "plan": ("medication_text", "prior_text"),
}


EXPECTED_TEMPLATE_COUNTS: Final[Mapping[PatientTier, int]] = {
    "normal": 3,
    "moderate": 4,
    "chronic": 5,
}


EXPECTED_TOTAL_TEMPLATE_COUNT: Final[int] = 48


__all__ = (
    "SoapSection",
    "PatientTier",
    "SoapTemplate",
    "SOAP_SECTIONS",
    "PATIENT_TIERS",
    "ALLOWED_TEMPLATE_PLACEHOLDERS",
    "REQUIRED_FACTS_BY_SECTION",
    "EXPECTED_TEMPLATE_COUNTS",
    "EXPECTED_TOTAL_TEMPLATE_COUNT",
)
