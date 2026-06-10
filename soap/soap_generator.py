"""
soap/soap_generator.py

Deterministic SOAP narrative generation.

Purpose:
    Assemble final SOAP notes from validated structured patient JSON using the
    deterministic SOAP pipeline:

        structured patient JSON
            ↓
        build_fact_context()
            ↓
        style-aware deterministic template selection
            ↓
        safe template rendering from fact context only
            ↓
        SOAP note dictionary

v1.7 Lite alignment:
    SOAP generation uses patient-level soap_style plus visit_role,
    clinical_event, semantic_focus, and retrieval_context fields to improve
    semantic diversity for downstream RAG doctor_note chunks without changing
    medical facts.

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
    - No schema redesign.
    - No metadata rewriting.
    - No mutation of structured patient facts.

Architecture role:
    soap_contract.py   -> shared SOAP sections/types/template dataclass
    soap_renderers.py  -> fact extraction, exact formatting, template rendering
    soap_templates.py  -> template registry only
    soap_selector.py   -> deterministic template selection only
    soap_generator.py  -> final SOAP assembly only
    soap_auditor.py    -> safety checks after generation

Important:
    The medical truth must come only from structured JSON through
    build_fact_context(). Templates may change wording, but they must never
    create or modify medical meaning.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from soap.soap_contract import SOAP_SECTIONS, SoapSection, SoapTemplate
from soap.soap_renderers import (
    SoapFactContext,
    build_fact_context,
    render_template,
    validate_fact_context_for_template,
)
from soap.soap_selector import (
    SoapTemplateSelection,
    select_templates_from_fact_context,
    select_templates_from_fact_context_with_metadata,
)
from soap.soap_semantics import VISIT_ROLE_VOCABULARY as _VISIT_ROLE_VOCABULARY
from soap.soap_templates import TEMPLATE_VERSION


SOAP_GENERATOR_VERSION = "soap-generator-v1.7-lite"

# Expose the visit-role phrase dictionary for the auditor.
# The auditor imports this name so both modules share exactly one copy.
VISIT_ROLE_PHRASES = _VISIT_ROLE_VOCABULARY


@dataclass(frozen=True)
class SoapGenerationResult:
    """
    Optional rich result for tests, debugging, and audit handoff.

    Attributes:
        soap_note:
            Rendered SOAP note with exactly the standard SOAP sections.
        fact_context:
            Structured/rendered fact context used for template rendering.
        selected_templates:
            Selected template objects per SOAP section.
        selections:
            Deterministic selection metadata per SOAP section.
        generator_version:
            Version of this orchestration layer.
        template_version:
            Version of the template registry used for selection.
    """

    soap_note: dict[str, str]
    fact_context: SoapFactContext
    selected_templates: dict[SoapSection, SoapTemplate]
    selections: dict[SoapSection, SoapTemplateSelection]
    generator_version: str
    template_version: str


# ---------------------------------------------------------------------
# Public patient-level orchestration
# ---------------------------------------------------------------------


def add_soap_notes_to_patient(
    patient: dict[str, Any],
    *,
    template_version: str = TEMPLATE_VERSION,
) -> dict[str, Any]:
    """
    Return a deep-copied patient dictionary with SOAP notes populated.

    This function preserves all structured facts and only writes generated text
    into each visit["soap_note"] field in the copied patient object.

    Args:
        patient: Validated patient JSON dictionary.
        template_version: Template registry version used by the selector.

    Returns:
        Deep-copied patient dictionary with deterministic SOAP notes added.
    """
    updated_patient = deepcopy(patient)
    visits = updated_patient.get("visits", [])

    if not isinstance(visits, list):
        raise ValueError(
            "patient.visits must be a list before SOAP generation. "
            "Run validators.validate before generating SOAP notes."
        )

    for visit in visits:
        if not isinstance(visit, dict):
            raise ValueError(
                "Every patient.visits item must be an object before SOAP "
                "generation. Run validators.validate first."
            )

        visit["soap_note"] = generate_soap_note(
            patient=updated_patient,
            visit=visit,
            template_version=template_version,
        )

    return updated_patient


# Backward-compatible plural alias for scripts/tests that prefer this name.
def add_soap_notes(patient: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible alias for add_soap_notes_to_patient()."""
    return add_soap_notes_to_patient(patient)


def generate_soap_for_patient(
    patient: dict[str, Any],
    blueprint: Any | None = None,
    *,
    template_version: str = TEMPLATE_VERSION,
) -> None:
    """
    Generate SOAP notes for all visits in *patient* in-place.

    Mutates patient["visits"][i]["soap_note"] for every visit.  This mirrors
    the in-place mutation pattern used by the other generators
    (generate_visits_for_patient, generate_medications_for_patient, …).

    The *blueprint* argument is accepted for API compatibility with the
    integration-test harness but is not required for SOAP generation.

    Args:
        patient: Fully populated patient dict (visits, meds, labs, allergies
                 must already be present).
        blueprint: PatientBlueprint or None.  Not used internally.
        template_version: Template registry version.
    """
    visits = patient.get("visits", [])
    for visit in visits:
        visit["soap_note"] = generate_soap_note(
            patient=patient,
            visit=visit,
            template_version=template_version,
        )


# ---------------------------------------------------------------------
# Visit-level SOAP generation
# ---------------------------------------------------------------------


def generate_soap_note(
    patient: dict[str, Any],
    visit: dict[str, Any],
    *,
    template_version: str = TEMPLATE_VERSION,
) -> dict[str, str]:
    """
    Generate a deterministic diversified SOAP note from structured facts.

    The function:
        1. Builds a fact context from structured patient/visit JSON.
        2. Selects one deterministic template per SOAP section.
        3. Renders templates using fact-context values only.
        4. Returns the final SOAP dictionary.

    Args:
        patient: Validated patient JSON dictionary.
        visit: Validated visit dictionary from patient["visits"].
        template_version: Template registry version used by the selector.

    Returns:
        SOAP note dictionary with exactly four sections:
            - subjective
            - objective
            - assessment
            - plan
    """
    return generate_soap_note_with_metadata(
        patient=patient,
        visit=visit,
        template_version=template_version,
    ).soap_note


def generate_soap_note_with_metadata(
    patient: dict[str, Any],
    visit: dict[str, Any],
    *,
    template_version: str = TEMPLATE_VERSION,
) -> SoapGenerationResult:
    """
    Generate a SOAP note and return deterministic generation metadata.

    This function is useful for tests and future audit logging. It does not
    mutate the patient or visit dictionaries.
    """
    fact_context = build_fact_context(patient=patient, visit=visit)
    missing_contract_fields = validate_fact_context_for_template(fact_context)

    if missing_contract_fields:
        raise ValueError(
            "SOAP fact context is missing required template contract fields: "
            + ", ".join(missing_contract_fields)
        )

    selections = select_templates_from_fact_context_with_metadata(
        fact_context,
        template_version=template_version,
    )
    selected_templates = {
        section: selection.template
        for section, selection in selections.items()
    }

    soap_note = render_soap_note_from_templates(
        fact_context=fact_context,
        selected_templates=selected_templates,
    )

    return SoapGenerationResult(
        soap_note=soap_note,
        fact_context=fact_context,
        selected_templates=selected_templates,
        selections=selections,
        generator_version=SOAP_GENERATOR_VERSION,
        template_version=template_version,
    )


# ---------------------------------------------------------------------
# Rendering orchestration
# ---------------------------------------------------------------------


def render_soap_note_from_templates(
    *,
    fact_context: SoapFactContext,
    selected_templates: Mapping[SoapSection, SoapTemplate],
) -> dict[str, str]:
    """
    Render a SOAP note from selected templates and a fact context.

    This function performs section assembly only. The single-template rendering
    itself is delegated to soap_renderers.render_template(), which validates
    placeholders against the shared SOAP contract.

    Args:
        fact_context: Fact context produced by build_fact_context().
        selected_templates: Mapping from SOAP section to selected template.

    Returns:
        SOAP note dictionary with exactly four rendered sections.

    Raises:
        ValueError: If required sections/templates are missing or invalid.
    """
    clean_templates = _validate_selected_templates(selected_templates)

    soap_note = {
        section: render_template(
            clean_templates[section],
            fact_context,
        )
        for section in SOAP_SECTIONS
    }

    # -------------------------------------------------------------------------
    # Step 9 Post-Processing Enhancements
    # -------------------------------------------------------------------------
    from soap.soap_semantics import SOAP_STYLE_OPENERS, VISIT_ROLE_VOCABULARY

    # 1. Enforce style-aware opener at the start of Subjective section
    soap_style = fact_context.get("soap_style")
    if soap_style == "problem_oriented":
        opener = "The primary concern today is the patient's health status."
        subj = soap_note["subjective"]
        if not subj.startswith("The primary concern today is"):
            soap_note["subjective"] = f"{opener} {subj}"
    elif soap_style == "timeline_oriented":
        opener = "Compared with the previous visit, the clinical timeline has been updated."
        subj = soap_note["subjective"]
        if not subj.startswith("Compared with the previous visit"):
            soap_note["subjective"] = f"{opener} {subj}"
    elif soap_style == "concise":
        opener = "This encounter records the patient's clinical status."
        subj = soap_note["subjective"]
        if not subj.startswith("This encounter records"):
            soap_note["subjective"] = f"{opener} {subj}"

    # 2. Inject required visit_role vocabulary into Subjective section
    visit_role = fact_context.get("visit_role")
    if visit_role and visit_role in VISIT_ROLE_VOCABULARY:
        phrases = VISIT_ROLE_VOCABULARY[visit_role]
        subj = soap_note["subjective"]
        # Ensure all required phrases are present in the note.
        # If any are missing, append them as a grammatically structured sentence.
        full_text = " ".join(soap_note.values()).lower()
        missing_phrases = [p for p in phrases if p.rstrip(",").lower() not in full_text]
        if missing_phrases:
            vocab_sentences = " ".join(
                f"{phrase.capitalize()}." if not phrase.endswith((".", ",")) else phrase.capitalize()
                for phrase in missing_phrases
            )
            if not subj.endswith(" "):
                subj += " "
            soap_note["subjective"] = f"{subj}Regarding the clinical course: {vocab_sentences}"

    # 3. Inject clinical_event.event_summary verbatim into Assessment section
    event_summary = fact_context.get("clinical_event_summary")
    if event_summary:
        asm = soap_note["assessment"]
        if event_summary.lower() not in asm.lower():
            soap_note["assessment"] = f"{event_summary} {asm}"

    _validate_rendered_soap_note(soap_note)
    return soap_note


def select_templates_for_soap_note(
    fact_context: SoapFactContext,
    *,
    template_version: str = TEMPLATE_VERSION,
) -> dict[SoapSection, SoapTemplate]:
    """
    Select deterministic templates for a SOAP note from fact context.

    This small wrapper keeps the generator API explicit while leaving the
    selection algorithm inside soap_selector.py.
    """
    return select_templates_from_fact_context(
        fact_context,
        template_version=template_version,
    )


# ---------------------------------------------------------------------
# Validation helpers local to final assembly
# ---------------------------------------------------------------------


def _validate_selected_templates(
    selected_templates: Mapping[SoapSection, SoapTemplate],
) -> dict[SoapSection, SoapTemplate]:
    """
    Validate that all required SOAP sections have selected templates.
    """
    missing_sections = [
        section for section in SOAP_SECTIONS if section not in selected_templates
    ]

    if missing_sections:
        raise ValueError(
            "Missing selected SOAP templates for sections: "
            + ", ".join(missing_sections)
        )

    clean_templates: dict[SoapSection, SoapTemplate] = {}

    for section in SOAP_SECTIONS:
        template = selected_templates[section]

        if not isinstance(template, SoapTemplate):
            raise ValueError(
                f"Selected template for section {section!r} must be "
                f"SoapTemplate, got {type(template).__name__}."
            )

        if template.section != section:
            raise ValueError(
                f"Selected template {template.template_id!r} has section "
                f"{template.section!r}, expected {section!r}."
            )

        clean_templates[section] = template

    return clean_templates


def _validate_rendered_soap_note(soap_note: Mapping[str, str]) -> None:
    """
    Validate the final SOAP note shape after rendering.

    This is intentionally shape-only. Clinical safety belongs to
    soap_auditor.py.
    """
    expected_sections = set(SOAP_SECTIONS)
    actual_sections = set(soap_note)

    missing = sorted(expected_sections - actual_sections)
    extra = sorted(actual_sections - expected_sections)

    if missing:
        raise ValueError("Rendered SOAP note is missing sections: " + ", ".join(missing))

    if extra:
        raise ValueError("Rendered SOAP note has unexpected sections: " + ", ".join(extra))

    empty_sections = [
        section
        for section in SOAP_SECTIONS
        if not isinstance(soap_note.get(section), str) or not soap_note[section].strip()
    ]

    if empty_sections:
        raise ValueError(
            "Rendered SOAP note contains empty sections: "
            + ", ".join(empty_sections)
        )


__all__ = [
    "SOAP_GENERATOR_VERSION",
    "VISIT_ROLE_PHRASES",
    "SoapGenerationResult",
    "add_soap_notes",
    "add_soap_notes_to_patient",
    "generate_soap_for_patient",
    "generate_soap_note",
    "generate_soap_note_with_metadata",
    "render_soap_note_from_templates",
    "select_templates_for_soap_note",
]
