"""
soap/soap_generator.py

Deterministic SOAP narrative generation.

Current architecture:
    Structured JSON
        ↓
    build_fact_context()
        ↓
    deterministic template selection
        ↓
    template rendering
        ↓
    SOAP note dictionary

Safety contract:
    - Deterministic only.
    - Offline only.
    - No LLM logic.
    - No randomization.
    - No Python built-in hash().
    - No medical fact generation.
    - No diagnosis inference.
    - No medication selection.
    - No lab selection.
    - No vital sign selection.
    - No schema changes.
    - No metadata changes.
    - No mutation of structured patient facts.

Architecture role:
    soap_contract.py   -> owns shared SOAP sections/types/template dataclass
    soap_renderers.py  -> owns fact extraction and exact formatting
    soap_templates.py  -> owns template registry only
    soap_selector.py   -> owns deterministic template selection only
    soap_generator.py  -> owns final SOAP assembly/rendering
    soap_auditor.py    -> owns safety checks

Important:
    The medical truth must come only from structured JSON through
    build_fact_context(). Templates may change wording, but they must never
    create or modify medical meaning.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from soap.soap_contract import SOAP_SECTIONS, SoapSection, SoapTemplate
from soap.soap_renderers import SoapFactContext, build_fact_context
from soap.soap_selector import select_templates_from_fact_context


def add_soap_notes_to_patient(patient: dict[str, Any]) -> dict[str, Any]:
    """
    Return a deep-copied patient dictionary with SOAP notes populated.

    This function preserves all structured facts and only writes the generated
    SOAP note into each visit["soap_note"] field.

    Args:
        patient: Patient JSON dictionary.

    Returns:
        Deep-copied patient dictionary with deterministic SOAP notes added.
    """
    updated_patient = deepcopy(patient)

    for visit in updated_patient.get("visits", []):
        visit["soap_note"] = generate_soap_note(
            patient=updated_patient,
            visit=visit,
        )

    return updated_patient


def generate_soap_note(
    patient: dict[str, Any],
    visit: dict[str, Any],
) -> dict[str, str]:
    """
    Generate a deterministic diversified SOAP note from structured facts.

    The function:
        1. Builds a fact context from structured patient/visit JSON.
        2. Selects one deterministic template per SOAP section.
        3. Renders templates using fact-context values only.
        4. Returns the final SOAP dictionary.

    Args:
        patient: Patient JSON dictionary.
        visit: Visit dictionary from patient["visits"].

    Returns:
        SOAP note dictionary with exactly four sections:
            - subjective
            - objective
            - assessment
            - plan
    """
    fact_context = build_fact_context(patient=patient, visit=visit)
    selected_templates = select_templates_from_fact_context(fact_context)

    return render_soap_note_from_templates(
        fact_context=fact_context,
        selected_templates=selected_templates,
    )


def render_soap_note_from_templates(
    *,
    fact_context: SoapFactContext,
    selected_templates: Mapping[SoapSection, SoapTemplate],
) -> dict[str, str]:
    """
    Render a SOAP note from selected templates and a fact context.

    This function performs placeholder replacement only. It does not select
    templates, calculate medical values, infer facts, or modify structured data.

    Args:
        fact_context: Fact context produced by build_fact_context().
        selected_templates: Mapping from SOAP section to selected template.

    Returns:
        SOAP note dictionary with exactly four rendered sections.

    Raises:
        ValueError: If a required SOAP section is missing.
        KeyError: If a template references a missing fact-context key.
    """
    _validate_selected_templates(selected_templates)

    return {
        section: _render_template(
            template=selected_templates[section],
            fact_context=fact_context,
        )
        for section in SOAP_SECTIONS
    }


def _render_template(
    *,
    template: SoapTemplate,
    fact_context: Mapping[str, Any],
) -> str:
    """
    Render a single SOAP template using fact-context values.

    Args:
        template: Selected SOAP template.
        fact_context: Fact context mapping.

    Returns:
        Rendered SOAP section text.

    Raises:
        KeyError: If a required placeholder is missing from fact_context.
    """
    try:
        rendered = template.text.format(**fact_context)
    except KeyError as exc:
        missing_key = exc.args[0]
        raise KeyError(
            f"Template {template.template_id!r} references missing "
            f"fact-context key {missing_key!r}."
        ) from exc

    return rendered


def _validate_selected_templates(
    selected_templates: Mapping[SoapSection, SoapTemplate],
) -> None:
    """
    Validate that all required SOAP sections have selected templates.

    Args:
        selected_templates: Mapping from SOAP section to selected template.

    Raises:
        ValueError: If any SOAP section is missing.
    """
    missing_sections = [
        section
        for section in SOAP_SECTIONS
        if section not in selected_templates
    ]

    if missing_sections:
        raise ValueError(
            "Missing selected SOAP templates for sections: "
            + ", ".join(missing_sections)
        )


__all__ = [
    "add_soap_notes_to_patient",
    "generate_soap_note",
    "render_soap_note_from_templates",
]
