"""
soap/soap_selector.py

Deterministic v1.7 Lite SOAP template selection utilities.

Purpose:
    Select SOAP templates from soap_templates.py in a fully deterministic,
    reproducible, auditable way.

v1.7 Lite alignment:
    The selector now routes by the controlled SOAP style stored in patient
    metadata while still using stable patient/visit fields for reproducible
    variation. It may include visit_role, semantic_focus, and clinical event
    type in the deterministic seed, but it never interprets those fields as
    medical facts.

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
    1. Validate section, tier, and soap_style.
    2. Read the template group for section/tier.
    3. Filter templates to the requested soap_style.
    4. Use SHA-256 over stable input fields to select one template from the
       style-filtered group.

The field order in build_template_seed_key() is part of the deterministic
selector contract and should only change with an intentional selector version.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, cast

from soap.soap_contract import (
    PATIENT_TIERS,
    SOAP_SECTIONS,
    SOAP_STYLES,
    PatientTier,
    SoapSection,
    SoapStyle,
    SoapTemplate,
)
from soap.soap_templates import SOAP_TEMPLATES, TEMPLATE_VERSION


DEFAULT_SOAP_STYLE: SoapStyle = "concise"


@dataclass(frozen=True)
class SoapTemplateSelection:
    """
    Immutable record describing one deterministic template selection.

    Attributes:
        section:
            SOAP section for which the template was selected.
        tier:
            Patient tier used for routing.
        soap_style:
            v1.7 Lite style used to filter templates.
        visit_type:
            Visit type included in the deterministic seed.
        visit_role:
            Visit role included in the deterministic seed when available.
        semantic_focus:
            Patient/visit semantic focus included in the deterministic seed
            when available.
        clinical_event_type:
            Clinical event type included in the deterministic seed when
            available.
        template:
            Selected SOAP template.
        seed_key:
            Full deterministic seed string used before SHA-256 hashing.
        template_index:
            Zero-based selected template index within the style-filtered group.
        candidate_count:
            Number of templates available after section/tier/style filtering.
        template_version:
            Template registry version included in selection seed.
    """

    section: SoapSection
    tier: PatientTier
    soap_style: SoapStyle
    visit_type: str
    visit_role: str
    semantic_focus: str
    clinical_event_type: str
    template: SoapTemplate
    seed_key: str
    template_index: int
    candidate_count: int
    template_version: str


def select_template(
    *,
    patient_id: str,
    visit_id: str,
    section: str,
    tier: str,
    visit_type: str,
    soap_style: str = DEFAULT_SOAP_STYLE,
    visit_role: str = "",
    semantic_focus: str = "",
    clinical_event_type: str = "",
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
        soap_style: v1.7 Lite style used to filter candidate templates.
        visit_role: Optional visit role used only for deterministic variation.
        semantic_focus: Optional semantic focus used only for deterministic
            variation.
        clinical_event_type: Optional event type used only for deterministic
            variation.
        template_version: Template registry version.

    Returns:
        The selected SoapTemplate.

    Raises:
        ValueError: If section, tier, style, identifiers, visit_type, or
            template version are invalid.
    """
    selection = select_template_with_metadata(
        patient_id=patient_id,
        visit_id=visit_id,
        section=section,
        tier=tier,
        visit_type=visit_type,
        soap_style=soap_style,
        visit_role=visit_role,
        semantic_focus=semantic_focus,
        clinical_event_type=clinical_event_type,
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
    soap_style: str = DEFAULT_SOAP_STYLE,
    visit_role: str = "",
    semantic_focus: str = "",
    clinical_event_type: str = "",
    template_version: str = TEMPLATE_VERSION,
) -> SoapTemplateSelection:
    """
    Select one SOAP template and return deterministic selection metadata.

    This function is useful for debugging, tests, and audit logging. It does
    not render text and does not inspect medical facts.
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
    clean_soap_style = _validate_soap_style(soap_style)
    clean_visit_role = _clean_optional_seed_string(visit_role, "visit_role")
    clean_semantic_focus = _clean_optional_seed_string(
        semantic_focus,
        "semantic_focus",
    )
    clean_clinical_event_type = _clean_optional_seed_string(
        clinical_event_type,
        "clinical_event_type",
    )

    template_group = get_template_group(
        section=clean_section,
        tier=clean_tier,
        soap_style=clean_soap_style,
    )

    seed_key = build_template_seed_key(
        template_version=clean_template_version,
        patient_id=clean_patient_id,
        visit_id=clean_visit_id,
        section=clean_section,
        tier=clean_tier,
        visit_type=clean_visit_type,
        soap_style=clean_soap_style,
        visit_role=clean_visit_role,
        semantic_focus=clean_semantic_focus,
        clinical_event_type=clean_clinical_event_type,
    )

    index = stable_index(seed_key=seed_key, size=len(template_group))
    template = template_group[index]

    return SoapTemplateSelection(
        section=clean_section,
        tier=clean_tier,
        soap_style=clean_soap_style,
        visit_type=clean_visit_type,
        visit_role=clean_visit_role,
        semantic_focus=clean_semantic_focus,
        clinical_event_type=clean_clinical_event_type,
        template=template,
        seed_key=seed_key,
        template_index=index,
        candidate_count=len(template_group),
        template_version=clean_template_version,
    )


def select_templates_for_visit(
    *,
    patient_id: str,
    visit_id: str,
    tier: str,
    visit_type: str,
    soap_style: str = DEFAULT_SOAP_STYLE,
    visit_role: str = "",
    semantic_focus: str = "",
    clinical_event_type: str = "",
    template_version: str = TEMPLATE_VERSION,
) -> dict[SoapSection, SoapTemplate]:
    """
    Select one deterministic template for each SOAP section.
    """
    return {
        section: select_template(
            patient_id=patient_id,
            visit_id=visit_id,
            section=section,
            tier=tier,
            visit_type=visit_type,
            soap_style=soap_style,
            visit_role=visit_role,
            semantic_focus=semantic_focus,
            clinical_event_type=clinical_event_type,
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
    soap_style: str = DEFAULT_SOAP_STYLE,
    visit_role: str = "",
    semantic_focus: str = "",
    clinical_event_type: str = "",
    template_version: str = TEMPLATE_VERSION,
) -> dict[SoapSection, SoapTemplateSelection]:
    """
    Select one deterministic template for each SOAP section with metadata.
    """
    return {
        section: select_template_with_metadata(
            patient_id=patient_id,
            visit_id=visit_id,
            section=section,
            tier=tier,
            visit_type=visit_type,
            soap_style=soap_style,
            visit_role=visit_role,
            semantic_focus=semantic_focus,
            clinical_event_type=clinical_event_type,
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

    Optional v1.7 Lite keys:
        - soap_style
        - visit_role
        - semantic_focus
        - clinical_event_type
        - clinical_event["event_type"]
    """
    selection_inputs = _selection_inputs_from_fact_context(fact_context)
    return select_templates_for_visit(
        **selection_inputs,
        template_version=template_version,
    )


def select_templates_from_fact_context_with_metadata(
    fact_context: Mapping[str, Any],
    *,
    template_version: str = TEMPLATE_VERSION,
) -> dict[SoapSection, SoapTemplateSelection]:
    """
    Select SOAP templates from fact context and return selection metadata.
    """
    selection_inputs = _selection_inputs_from_fact_context(fact_context)
    return select_templates_for_visit_with_metadata(
        **selection_inputs,
        template_version=template_version,
    )


def get_template_group(
    *,
    section: str,
    tier: str,
    soap_style: str | None = None,
) -> tuple[SoapTemplate, ...]:
    """
    Return the template group for a SOAP section and patient tier.

    If soap_style is provided, the returned tuple is filtered to templates with
    that style. If soap_style is omitted, all templates for section/tier are
    returned for compatibility with older tests.
    """
    clean_section = _validate_section(section)
    clean_tier = _validate_tier(tier)

    group = SOAP_TEMPLATES[clean_section][clean_tier]

    if soap_style is not None:
        clean_soap_style = _validate_soap_style(soap_style)
        group = tuple(
            template for template in group if template.style == clean_soap_style
        )

    if not group:
        style_suffix = "" if soap_style is None else f", soap_style={soap_style!r}"
        raise ValueError(
            f"No SOAP templates registered for section={clean_section!r}, "
            f"tier={clean_tier!r}{style_suffix}."
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
    soap_style: str = DEFAULT_SOAP_STYLE,
    visit_role: str = "",
    semantic_focus: str = "",
    clinical_event_type: str = "",
) -> str:
    """
    Build the stable seed key used for deterministic template selection.

    The order of fields in this string is part of the deterministic selection
    contract. Do not change it unless intentionally versioning the selector.
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
    clean_soap_style = _validate_soap_style(soap_style)
    clean_visit_role = _clean_optional_seed_string(visit_role, "visit_role")
    clean_semantic_focus = _clean_optional_seed_string(
        semantic_focus,
        "semantic_focus",
    )
    clean_clinical_event_type = _clean_optional_seed_string(
        clinical_event_type,
        "clinical_event_type",
    )

    return (
        f"{clean_template_version}|"
        f"{clean_patient_id}|"
        f"{clean_visit_id}|"
        f"{clean_section}|"
        f"{clean_tier}|"
        f"{clean_visit_type}|"
        f"{clean_soap_style}|"
        f"{clean_visit_role}|"
        f"{clean_semantic_focus}|"
        f"{clean_clinical_event_type}"
    )


def stable_index(
    *,
    seed_key: str,
    size: int,
) -> int:
    """
    Convert a seed key into a deterministic index using SHA-256.
    """
    clean_seed_key = _require_non_empty_string(seed_key, "seed_key")

    if size <= 0:
        raise ValueError("Cannot select from an empty template group.")

    digest = hashlib.sha256(clean_seed_key.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % size


def _selection_inputs_from_fact_context(
    fact_context: Mapping[str, Any],
) -> dict[str, str]:
    """Extract selector inputs from rendered fact context."""
    return {
        "patient_id": _get_required_context_string(fact_context, "patient_id"),
        "visit_id": _get_required_context_string(fact_context, "visit_id"),
        "tier": _get_required_context_string(fact_context, "tier"),
        "visit_type": _get_required_context_string(fact_context, "visit_type"),
        "soap_style": _get_optional_context_string(
            fact_context,
            "soap_style",
            default=DEFAULT_SOAP_STYLE,
        ),
        "visit_role": _get_optional_context_string(
            fact_context,
            "visit_role",
            default="",
        ),
        "semantic_focus": _get_optional_context_string(
            fact_context,
            "semantic_focus",
            default="",
        ),
        "clinical_event_type": _get_clinical_event_type_from_context(
            fact_context,
        ),
    }


def _get_clinical_event_type_from_context(fact_context: Mapping[str, Any]) -> str:
    """
    Read clinical event type from flat or nested fact context.

    The selector uses this only as deterministic seed material. It does not
    infer or validate medical meaning from the event.
    """
    direct = fact_context.get("clinical_event_type")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    clinical_event = fact_context.get("clinical_event")
    if isinstance(clinical_event, Mapping):
        nested = clinical_event.get("event_type")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()

    return ""


def _validate_section(section: str) -> SoapSection:
    """Validate and cast a SOAP section string."""
    clean_section = _require_non_empty_string(section, "section")

    if clean_section not in SOAP_SECTIONS:
        raise ValueError(
            f"Invalid SOAP section {clean_section!r}. "
            f"Expected one of: {', '.join(SOAP_SECTIONS)}."
        )

    return cast(SoapSection, clean_section)


def _validate_tier(tier: str) -> PatientTier:
    """Validate and cast a patient tier string."""
    clean_tier = _require_non_empty_string(tier, "tier")

    if clean_tier not in PATIENT_TIERS:
        raise ValueError(
            f"Invalid patient tier {clean_tier!r}. "
            f"Expected one of: {', '.join(PATIENT_TIERS)}."
        )

    return cast(PatientTier, clean_tier)


def _validate_soap_style(soap_style: str) -> SoapStyle:
    """Validate and cast a SOAP style string."""
    clean_soap_style = _require_non_empty_string(soap_style, "soap_style")

    if clean_soap_style not in SOAP_STYLES:
        raise ValueError(
            f"Invalid SOAP style {clean_soap_style!r}. "
            f"Expected one of: {', '.join(SOAP_STYLES)}."
        )

    return cast(SoapStyle, clean_soap_style)


def _get_required_context_string(
    fact_context: Mapping[str, Any],
    key: str,
) -> str:
    """Read and validate a required string value from fact context."""
    if key not in fact_context:
        raise ValueError(f"Missing required fact context key: {key!r}.")

    value = fact_context[key]

    if not isinstance(value, str):
        raise ValueError(
            f"Fact context key {key!r} must be a string, "
            f"got {type(value).__name__}."
        )

    return _require_non_empty_string(value, key)


def _get_optional_context_string(
    fact_context: Mapping[str, Any],
    key: str,
    *,
    default: str,
) -> str:
    """Read an optional string value from fact context."""
    value = fact_context.get(key, default)

    if value is None:
        return default

    if not isinstance(value, str):
        raise ValueError(
            f"Fact context key {key!r} must be a string when provided, "
            f"got {type(value).__name__}."
        )

    cleaned = value.strip()
    return cleaned if cleaned else default


def _clean_optional_seed_string(value: str, field_name: str) -> str:
    """Normalize optional seed fields without requiring them to be present."""
    if value is None:
        return ""

    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} must be a string, got {type(value).__name__}."
        )

    return value.strip()


def _require_non_empty_string(value: str, field_name: str) -> str:
    """Validate that a value is a non-empty string after trimming whitespace."""
    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} must be a string, got {type(value).__name__}."
        )

    cleaned = value.strip()

    if not cleaned:
        raise ValueError(f"{field_name} must be a non-empty string.")

    return cleaned


__all__ = [
    "DEFAULT_SOAP_STYLE",
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
