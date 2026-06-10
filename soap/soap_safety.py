"""
soap/soap_safety.py

Shared SOAP safety constants.

Purpose:
    Centralize deterministic SOAP safety wording policy, allergen context
    markers, required grounding markers, and internal debug leakage markers used
    by SOAP template validation and SOAP auditing.

This module intentionally contains constants only.

It must not contain:
    - SOAP template text
    - template registry
    - selector logic
    - rendering logic
    - fact extraction
    - lab formatting
    - medication formatting
    - audit functions
    - LLM calls
    - randomization
    - imports from other SOAP modules

Safety matching guidance:
    Callers should treat single-word forbidden terms differently from multi-word
    phrases. Single-word terms should be matched with word boundaries to avoid
    false positives such as matching "likely" inside "unlikely". Multi-word
    phrases should be matched after whitespace/case normalization.

v1.7 Lite policy:
    SOAP may describe documented structured facts, visit_role, clinical_event,
    timeline_pattern, semantic_focus, and retrieval intent tags, but it must not
    infer diagnoses, disease control, clinical deterioration, causality,
    treatment recommendations, or medication changes that are absent from the
    structured patient JSON.

Backward compatibility:
    FORBIDDEN_CLINICAL_PHRASES remains available as the combined tuple expected
    by existing callers. New or updated auditors should prefer the separated
    constants for more precise matching.
"""

from __future__ import annotations

from typing import Final


# ---------------------------------------------------------------------
# Forbidden clinical wording policy
# ---------------------------------------------------------------------

# Single-word unsupported interpretation/status terms.
#
# Matching guidance for callers:
#   - case-insensitive
#   - word-boundary based
#   - do not use plain substring matching
FORBIDDEN_CLINICAL_SINGLE_WORDS: Final[tuple[str, ...]] = (
    # Unsupported uncertainty / inference wording
    "likely",
    "suspected",
    "probably",
    "possibly",

    # Unsupported clinical status interpretation
    "uncontrolled",
    "controlled",
    "deteriorating",
    "resolved",
)


# Multi-word unsupported uncertainty, interpretation, diagnosis, status,
# causality, or treatment terms.
#
# Matching guidance for callers:
#   - case-insensitive
#   - normalized-whitespace phrase matching
#   - preferably boundary-aware at the phrase edges
FORBIDDEN_UNCERTAINTY_PHRASES: Final[tuple[str, ...]] = (
    "suggestive of",
    "consistent with",
    "appears to have",
    "may indicate",
    "may suggest",
    "rule out",
    "concern for",
    "possible diagnosis",
    "probable diagnosis",
)


FORBIDDEN_STATUS_INTERPRETATION_PHRASES: Final[tuple[str, ...]] = (
    "poorly controlled",
    "well controlled",
    "clinically improved",
    "improving clinically",
    "clinically worsening",
    "disease progression",
    "disease remission",
    "renal decline",
    "renal improvement",
    "glycemic control improved",
    "blood pressure controlled",
)


FORBIDDEN_CAUSALITY_PHRASES: Final[tuple[str, ...]] = (
    "caused by",
    "due to",
    "secondary to",
    "resulting from",
    "because of",
)


FORBIDDEN_TREATMENT_RECOMMENDATION_PHRASES: Final[tuple[str, ...]] = (
    "requires treatment",
    "should start",
    "should stop",
    "should continue",
    "should increase",
    "should decrease",
    "recommend starting",
    "recommend stopping",
    "recommend continuing",
    "recommend treatment",
    "needs medication",
    "needs treatment",
    "start treatment",
    "adjust treatment",
    "increase dose",
    "decrease dose",
)


FORBIDDEN_DIAGNOSIS_ASSERTION_PHRASES: Final[tuple[str, ...]] = (
    "diagnosed with",
    "new diagnosis of",
    "newly diagnosed",
    "meets criteria for",
)


# Backward-compatible grouped phrase constant used by existing template
# validation and SOAP auditing code. Keep this name stable to avoid breaking
# imports.
FORBIDDEN_CLINICAL_PHRASE_TERMS: Final[tuple[str, ...]] = (
    FORBIDDEN_UNCERTAINTY_PHRASES
    + FORBIDDEN_STATUS_INTERPRETATION_PHRASES
    + FORBIDDEN_CAUSALITY_PHRASES
    + FORBIDDEN_TREATMENT_RECOMMENDATION_PHRASES
    + FORBIDDEN_DIAGNOSIS_ASSERTION_PHRASES
)


# Backward-compatible combined constant used by existing callers.
FORBIDDEN_CLINICAL_PHRASES: Final[tuple[str, ...]] = (
    FORBIDDEN_CLINICAL_SINGLE_WORDS + FORBIDDEN_CLINICAL_PHRASE_TERMS
)


# ---------------------------------------------------------------------
# Allowed neutral SOAP wording hints
# ---------------------------------------------------------------------

# These terms are intentionally neutral. They help auditors/tests distinguish
# documentation wording from prescriptive clinical recommendations.
NEUTRAL_DOCUMENTATION_VERBS: Final[tuple[str, ...]] = (
    "documents",
    "documented",
    "records",
    "recorded",
    "lists",
    "listed",
    "includes",
    "reported",
    "charted",
    "noted",
)


# Phrases that are safe when they explicitly preserve structured-record
# grounding. Auditors may choose to allow these phrases even when they contain
# general clinical words such as "plan" or "medication".
SAFE_GROUNDING_PHRASES: Final[tuple[str, ...]] = (
    "as documented",
    "as recorded",
    "in the structured record",
    "in the visit record",
    "the chart documents",
    "the record documents",
    "the medication list includes",
    "the lab section records",
    "the visit diagnosis field documents",
)


# ---------------------------------------------------------------------
# v1.7 Lite grounding and retrieval-context markers
# ---------------------------------------------------------------------

# These field names are allowed to appear in fact-context dictionaries, logs, or
# test reports, but should not leak as raw placeholder names into final rendered
# SOAP text.
V17_LITE_CONTEXT_FIELD_NAMES: Final[tuple[str, ...]] = (
    "soap_style",
    "visit_role",
    "timeline_pattern",
    "timeline_gap_days",
    "clinical_event",
    "clinical_event_type",
    "clinical_event_label",
    "clinical_event_summary",
    "retrieval_context",
    "semantic_focus",
    "retrieval_intent_tags",
    "retrieval_signature",
)


# Raw placeholder markers that indicate a template formatting failure if they
# appear in final SOAP output.
PLACEHOLDER_LEAK_MARKERS: Final[tuple[str, ...]] = (
    "{patient_id}",
    "{visit_id}",
    "{condition_text}",
    "{diagnosis_text}",
    "{lab_text}",
    "{medication_text}",
    "{visit_role_text}",
    "{clinical_event_text}",
    "{timeline_context_text}",
    "{retrieval_focus_text}",
    "{lab_trend_text}",
    "{medication_trajectory_text}",
    "{allergy_context_text}",
)


# ---------------------------------------------------------------------
# Allergy prescription-context markers
# ---------------------------------------------------------------------

# Terms that indicate medication, prescription, treatment, or plan context.
# If an allergen appears near one of these terms, the auditor should flag it as
# a potential unsafe prescription-context mention.
#
# Matching guidance for callers:
#   - case-insensitive
#   - normalized text search is sufficient
ALLERGEN_CONTEXT_TERMS: Final[tuple[str, ...]] = (
    "prescribed",
    "started",
    "initiated",
    "given",
    "administered",
    "ordered",
    "continued",
    "restarted",
    "added",
    "medication",
    "medications",
    "drug",
    "therapy",
    "treatment",
    "plan",
)


# Allergy documentation terms are safe when they appear in allergy-record
# context and do not prescribe the allergen.
ALLERGY_DOCUMENTATION_TERMS: Final[tuple[str, ...]] = (
    "allergy",
    "allergen",
    "reaction",
    "allergy registry",
    "allergy record",
    "documented allergy",
    "recorded allergy",
)


# ---------------------------------------------------------------------
# Internal debug/template leakage markers
# ---------------------------------------------------------------------

# Internal selector/template/debug markers that must never leak into rendered
# SOAP note text.
DEBUG_TEMPLATE_MARKERS: Final[tuple[str, ...]] = (
    "SUBJ-",
    "OBJ-",
    "ASM-",
    "PLAN-",
    "template_id",
    "template_version",
    "seed_key",
    "template_index",
    "SoapTemplateSelection",
)


# Combined leakage markers used by auditors/tests that inspect rendered SOAP.
SOAP_OUTPUT_LEAKAGE_MARKERS: Final[tuple[str, ...]] = (
    DEBUG_TEMPLATE_MARKERS + PLACEHOLDER_LEAK_MARKERS
)


__all__ = (
    "FORBIDDEN_CLINICAL_SINGLE_WORDS",
    "FORBIDDEN_UNCERTAINTY_PHRASES",
    "FORBIDDEN_STATUS_INTERPRETATION_PHRASES",
    "FORBIDDEN_CAUSALITY_PHRASES",
    "FORBIDDEN_TREATMENT_RECOMMENDATION_PHRASES",
    "FORBIDDEN_DIAGNOSIS_ASSERTION_PHRASES",
    "FORBIDDEN_CLINICAL_PHRASE_TERMS",
    "FORBIDDEN_CLINICAL_PHRASES",
    "NEUTRAL_DOCUMENTATION_VERBS",
    "SAFE_GROUNDING_PHRASES",
    "V17_LITE_CONTEXT_FIELD_NAMES",
    "PLACEHOLDER_LEAK_MARKERS",
    "ALLERGEN_CONTEXT_TERMS",
    "ALLERGY_DOCUMENTATION_TERMS",
    "DEBUG_TEMPLATE_MARKERS",
    "SOAP_OUTPUT_LEAKAGE_MARKERS",
)
