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
"""

from __future__ import annotations

from typing import Final


# Clinical interpretation, unsupported diagnosis, and treatment-recommendation
# wording that must not appear in deterministic SOAP templates or generated
# SOAP output for this project.
#
# Matching is performed by callers and should be case-insensitive.
FORBIDDEN_CLINICAL_PHRASES: Final[tuple[str, ...]] = (
    # Unsupported uncertainty / inference wording
    "likely",
    "suggestive of",
    "consistent with",
    "suspected",
    "appears to have",
    "probably",
    "may indicate",
    "may suggest",
    "rule out",

    # Unsupported clinical status interpretation
    "poorly controlled",
    "well controlled",
    "uncontrolled",
    "deteriorating",
    "worsening",
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


# Terms that indicate medication, prescription, treatment, or plan context.
# If an allergen appears near one of these terms, the auditor should flag it as
# a potential unsafe prescription-context mention.
#
# Matching is performed by callers and should be case-insensitive.
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
    "FORBIDDEN_CLINICAL_PHRASES",
    "ALLERGEN_CONTEXT_TERMS",
    "DEBUG_TEMPLATE_MARKERS",
)
