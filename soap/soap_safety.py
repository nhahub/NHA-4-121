"""
soap/soap_safety.py

Shared SOAP safety constants.

Purpose:
    Centralize deterministic SOAP safety wording policy and internal debug
    leakage markers used by SOAP template validation and SOAP auditing.

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

Backward compatibility:
    FORBIDDEN_CLINICAL_PHRASES remains available as the combined tuple expected
    by existing callers. New or updated auditors should prefer the separated
    FORBIDDEN_CLINICAL_SINGLE_WORDS and FORBIDDEN_CLINICAL_PHRASE_TERMS constants
    for more precise matching.
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

    # Unsupported clinical status interpretation
    "uncontrolled",
    "deteriorating",
    "worsening",
)


# Multi-word unsupported interpretation, diagnosis, status, or treatment terms.
#
# Matching guidance for callers:
#   - case-insensitive
#   - normalized-whitespace phrase matching
#   - preferably boundary-aware at the phrase edges
FORBIDDEN_CLINICAL_PHRASE_TERMS: Final[tuple[str, ...]] = (
    # Unsupported uncertainty / inference wording
    "suggestive of",
    "consistent with",
    "appears to have",
    "may indicate",
    "may suggest",
    "rule out",

    # Unsupported clinical status interpretation
    "poorly controlled",
    "well controlled",
    "improving clinically",

    # Treatment recommendation / prescriptive wording
    "requires treatment",
    "should start",
    "should continue",
    "recommend starting",
    "recommend treatment",
    "needs medication",
    "needs treatment",

    # Diagnosis assertion wording
    "diagnosed with",
)


# Backward-compatible combined constant used by existing template validation and
# SOAP auditing code. Keep this name stable to avoid breaking imports.
FORBIDDEN_CLINICAL_PHRASES: Final[tuple[str, ...]] = (
    FORBIDDEN_CLINICAL_SINGLE_WORDS + FORBIDDEN_CLINICAL_PHRASE_TERMS
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
    "medication",
    "medications",
    "drug",
    "therapy",
    "treatment",
    "plan",
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
)


__all__ = (
    "FORBIDDEN_CLINICAL_SINGLE_WORDS",
    "FORBIDDEN_CLINICAL_PHRASE_TERMS",
    "FORBIDDEN_CLINICAL_PHRASES",
    "ALLERGEN_CONTEXT_TERMS",
    "DEBUG_TEMPLATE_MARKERS",
)
