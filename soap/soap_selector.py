"""
soap/soap_selector.py

Deterministic SOAP template selection utilities.

Purpose:
    Select SOAP templates from soap_templates.py in a fully deterministic,
    reproducible, auditable way.

Safety contract:
    - No randomization.
    - No Python built-in hash().
    - No LLM calls.
    - No rendering of SOAP text.
    - No medical fact calculation.
    - No mutation of patient or visit data.
    - No inference of diagnoses, medications, labs, vitals, or conditions.

Architecture role:
    soap_contract.py   -> owns shared SOAP sections/types/template dataclass
    soap_templates.py  -> owns template registry only
    soap_renderers.py  -> owns fact extraction and exact formatting
    soap_selector.py   -> owns deterministic template selection only
    soap_generator.py  -> owns final SOAP assembly/rendering
    soap_auditor.py    -> owns safety checks

Selection strategy:
    The selector uses SHA-256 over stable input fields:

        template_version
        patient_id
        visit_id
        section
        tier
        visit_type

    This guarantees that the same patient, visit, section, tier, and template
    version always produce the same selected template across runs and machines.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, cast

from soap.soap_contract import (
    PATIENT_TIERS,
    SOAP_SECTIONS,
    PatientTier,
    SoapSection,
    SoapTemplate,
)
from soap.soap_templates import SOAP_TEMPLATES, TEMPLATE_VERSION


@dataclass(frozen=True)
class SoapTemplateSelection:
    """
    Immutable record describing one deterministic template selection.

    Attributes:
        section:
            SOAP section for which the template was selected.
        tier:
            Patient tier used for routing.
        visit_type:
            Visit type included in the deterministic seed.
        template:
            Selected SOAP template.
        seed_key:
            Full deterministic seed string used before SHA-256 hashing.
        template_index:
            Zero-based selected template index within the section/tier group.
        template_version:
            Template registry version included in selection seed.
    """

    section: SoapSection
    tier: PatientTier
    visit_type: str
    template: SoapTemplate
    seed_key: str
    template_index: int
    template_version: str


def select_template(
    *,
    patient_id: str,
    visit_id: str,
    section: str,
    tier: str,
    visit_type: str,
    template_version: str = TEMPLATE_VERSION,
) -> SoapTemplate:
    """
    Select one SOAP template deterministically.

    This is the main public function used when only the selected template is
    needed.

    Args:
        patient_id: Stable patient identifier, e.g. PAT-MOD-003.
        visit_id: Stable visit identifier, e.g. VST-MOD-003-004.
        section: SOAP section name.
        tier: Patient tier: normal, moderate, or chronic.
        visit_type: Visit type included in deterministic seed.
        template_version: Template registry version.

    Returns:
        The selected SoapTemplate.

    Raises:
        ValueError: If section, tier, identifiers, visit_type, or template
            version are invalid.
    """
    selection = select_template_with_metadata(
        patient_id=patient_id,
        visit_id=visit_id,
        section=section,
        tier=tier,
        visit_type=visit_type,
        template_version=template_version,
    )
    return selection.template


def select_template_with_metadata(
    *,
    patient_id: str,
    visit_id: str,
    section: str,
    tier: str,
    visit_type: str,
    template_version: str = TEMPLATE_VERSION,
) -> SoapTemplateSelection:
    """
    Select one SOAP template and return deterministic selection metadata.

    This function is useful for debugging, tests, and future audit logging.

    Args:
        patient_id: Stable patient identifier.
        visit_id: Stable visit identifier.
        section: SOAP section name.
        tier: Patient tier.
        visit_type: Visit type included in deterministic seed.
        template_version: Template registry version.

    Returns:
        SoapTemplateSelection with the selected template and selection metadata.

    Raises:
        ValueError: If any routing or seed input is invalid.
    """
    clean_patient_id = _require_non_empty_string(patient_id, "patient_id")
    clean_visit_id = _require_non_empty_string(visit_id, "visit_id")
    clean_visit_type = _require_non_empty_string(visit_type, "visit_type")
    clean_template_version = _require_non_empty_string(
        template_version,
        "template_version",
    )

    clean_section = _validate_section(section)
    clean_tier = _validate_tier(tier)

    template_group = get_template_group(
        section=clean_section,
        tier=clean_tier,
    )

    seed_key = build_template_seed_key(
        template_version=clean_template_version,
        patient_id=clean_patient_id,
        visit_id=clean_visit_id,
        section=clean_section,
        tier=clean_tier,
        visit_type=clean_visit_type,
    )

    index = stable_index(seed_key=seed_key, size=len(template_group))
    template = template_group[index]

    return SoapTemplateSelection(
        section=clean_section,
        tier=clean_tier,
        visit_type=clean_visit_type,
        template=template,
        seed_key=seed_key,
        template_index=index,
        template_version=clean_template_version,
    )


def select_templates_for_visit(
    *,
    patient_id: str,
    visit_id: str,
    tier: str,
    visit_type: str,
    template_version: str = TEMPLATE_VERSION,
) -> dict[SoapSection, SoapTemplate]:
    """
    Select one deterministic template for each SOAP section.

    Args:
        patient_id: Stable patient identifier.
        visit_id: Stable visit identifier.
        tier: Patient tier used for template routing.
        visit_type: Visit type included in deterministic seed.
        template_version: Template registry version.

    Returns:
        Dictionary mapping each SOAP section to its selected SoapTemplate.
    """
    return {
        section: select_template(
            patient_id=patient_id,
            visit_id=visit_id,
            section=section,
            tier=tier,
            visit_type=visit_type,
            template_version=template_version,
        )
        for section in SOAP_SECTIONS
    }


def select_templates_for_visit_with_metadata(
    *,
    patient_id: str,
    visit_id: str,
    tier: str,
    visit_type: str,
    template_version: str = TEMPLATE_VERSION,
) -> dict[SoapSection, SoapTemplateSelection]:
    """
    Select one deterministic template for each SOAP section with metadata.

    Args:
        patient_id: Stable patient identifier.
        visit_id: Stable visit identifier.
        tier: Patient tier used for template routing.
        visit_type: Visit type included in deterministic seed.
        template_version: Template registry version.

    Returns:
        Dictionary mapping each SOAP section to SoapTemplateSelection.
    """
    return {
        section: select_template_with_metadata(
            patient_id=patient_id,
            visit_id=visit_id,
            section=section,
            tier=tier,
            visit_type=visit_type,
            template_version=template_version,
        )
        for section in SOAP_SECTIONS
    }


def select_templates_from_fact_context(
    fact_context: Mapping[str, Any],
    *,
    template_version: str = TEMPLATE_VERSION,
) -> dict[SoapSection, SoapTemplate]:
    """
    Select one deterministic template for each SOAP section from fact context.

    Expected fact_context keys:
        - patient_id
        - visit_id
        - tier
        - visit_type

    Args:
        fact_context: Fact context produced by build_fact_context().
        template_version: Template registry version.

    Returns:
        Dictionary mapping each SOAP section to its selected SoapTemplate.

    Raises:
        ValueError: If required keys are missing or invalid.
    """
    patient_id = _get_required_context_string(fact_context, "patient_id")
    visit_id = _get_required_context_string(fact_context, "visit_id")
    tier = _get_required_context_string(fact_context, "tier")
    visit_type = _get_required_context_string(fact_context, "visit_type")

    return select_templates_for_visit(
        patient_id=patient_id,
        visit_id=visit_id,
        tier=tier,
        visit_type=visit_type,
        template_version=template_version,
    )


def select_templates_from_fact_context_with_metadata(
    fact_context: Mapping[str, Any],
    *,
    template_version: str = TEMPLATE_VERSION,
) -> dict[SoapSection, SoapTemplateSelection]:
    """
    Select SOAP templates from fact context and return selection metadata.

    Expected fact_context keys:
        - patient_id
        - visit_id
        - tier
        - visit_type

    Args:
        fact_context: Fact context produced by build_fact_context().
        template_version: Template registry version.

    Returns:
        Dictionary mapping each SOAP section to SoapTemplateSelection.
    """
    patient_id = _get_required_context_string(fact_context, "patient_id")
    visit_id = _get_required_context_string(fact_context, "visit_id")
    tier = _get_required_context_string(fact_context, "tier")
    visit_type = _get_required_context_string(fact_context, "visit_type")

    return select_templates_for_visit_with_metadata(
        patient_id=patient_id,
        visit_id=visit_id,
        tier=tier,
        visit_type=visit_type,
        template_version=template_version,
    )


def get_template_group(
    *,
    section: str,
    tier: str,
) -> tuple[SoapTemplate, ...]:
    """
    Return the template group for a SOAP section and patient tier.

    Args:
        section: SOAP section name.
        tier: Patient tier.

    Returns:
        Tuple of SoapTemplate entries.

    Raises:
        ValueError: If section or tier is invalid or the group is empty.
    """
    clean_section = _validate_section(section)
    clean_tier = _validate_tier(tier)

    group = SOAP_TEMPLATES[clean_section][clean_tier]

    if not group:
        raise ValueError(
            f"No SOAP templates registered for section={clean_section!r}, "
            f"tier={clean_tier!r}."
        )

    return group


def build_template_seed_key(
    *,
    template_version: str,
    patient_id: str,
    visit_id: str,
    section: str,
    tier: str,
    visit_type: str,
) -> str:
    """
    Build the stable seed key used for deterministic template selection.

    The order of fields in this string is part of the deterministic selection
    contract. Do not change it unless intentionally versioning the selector.

    Args:
        template_version: Template registry version.
        patient_id: Stable patient identifier.
        visit_id: Stable visit identifier.
        section: SOAP section name.
        tier: Patient tier.
        visit_type: Visit type.

    Returns:
        Stable pipe-delimited seed key.
    """
    clean_template_version = _require_non_empty_string(
        template_version,
        "template_version",
    )
    clean_patient_id = _require_non_empty_string(patient_id, "patient_id")
    clean_visit_id = _require_non_empty_string(visit_id, "visit_id")
    clean_section = _validate_section(section)
    clean_tier = _validate_tier(tier)
    clean_visit_type = _require_non_empty_string(visit_type, "visit_type")

    return (
        f"{clean_template_version}|"
        f"{clean_patient_id}|"
        f"{clean_visit_id}|"
        f"{clean_section}|"
        f"{clean_tier}|"
        f"{clean_visit_type}"
    )


def stable_index(
    *,
    seed_key: str,
    size: int,
) -> int:
    """
    Convert a seed key into a deterministic index using SHA-256.

    Args:
        seed_key: Stable seed string.
        size: Number of available templates.

    Returns:
        Integer index in range [0, size).

    Raises:
        ValueError: If seed_key is empty or size is not positive.
    """
    clean_seed_key = _require_non_empty_string(seed_key, "seed_key")

    if size <= 0:
        raise ValueError("Cannot select from an empty template group.")

    digest = hashlib.sha256(clean_seed_key.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % size


def _validate_section(section: str) -> SoapSection:
    """
    Validate and cast a SOAP section string.

    Args:
        section: Candidate SOAP section name.

    Returns:
        Validated SoapSection.

    Raises:
        ValueError: If section is invalid.
    """
    clean_section = _require_non_empty_string(section, "section")

    if clean_section not in SOAP_SECTIONS:
        raise ValueError(
            f"Invalid SOAP section {clean_section!r}. "
            f"Expected one of: {', '.join(SOAP_SECTIONS)}."
        )

    return cast(SoapSection, clean_section)


def _validate_tier(tier: str) -> PatientTier:
    """
    Validate and cast a patient tier string.

    Args:
        tier: Candidate patient tier.

    Returns:
        Validated PatientTier.

    Raises:
        ValueError: If tier is invalid.
    """
    clean_tier = _require_non_empty_string(tier, "tier")

    if clean_tier not in PATIENT_TIERS:
        raise ValueError(
            f"Invalid patient tier {clean_tier!r}. "
            f"Expected one of: {', '.join(PATIENT_TIERS)}."
        )

    return cast(PatientTier, clean_tier)


def _get_required_context_string(
    fact_context: Mapping[str, Any],
    key: str,
) -> str:
    """
    Read and validate a required string value from fact context.

    Args:
        fact_context: Fact context mapping.
        key: Required key name.

    Returns:
        Non-empty string value.

    Raises:
        ValueError: If the key is missing or value is empty.
    """
    if key not in fact_context:
        raise ValueError(f"Missing required fact context key: {key!r}.")

    value = fact_context[key]

    if not isinstance(value, str):
        raise ValueError(
            f"Fact context key {key!r} must be a string, "
            f"got {type(value).__name__}."
        )

    return _require_non_empty_string(value, key)


def _require_non_empty_string(value: str, field_name: str) -> str:
    """
    Validate that a value is a non-empty string after trimming edge whitespace.

    Args:
        value: Candidate string.
        field_name: Field name used in error messages.

    Returns:
        Trimmed non-empty string.

    Raises:
        ValueError: If value is not a string or is empty.
    """
    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} must be a string, got {type(value).__name__}."
        )

    cleaned = value.strip()

    if not cleaned:
        raise ValueError(f"{field_name} must be a non-empty string.")

    return cleaned


__all__ = [
    "SoapTemplateSelection",
    "build_template_seed_key",
    "get_template_group",
    "select_template",
    "select_template_with_metadata",
    "select_templates_for_visit",
    "select_templates_for_visit_with_metadata",
    "select_templates_from_fact_context",
    "select_templates_from_fact_context_with_metadata",
    "stable_index",
]
