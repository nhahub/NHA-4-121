"""
generators/_generator_utils.py

Package-private shared utilities for the generators layer.

Design rules
------------
* This module is PRIVATE to the generators package (leading-underscore convention).
* Do NOT import this module from outside the generators/ directory.
* Do NOT import from validators, SOAP, ingestion, or RAG layers.
* Do NOT add runtime side effects, API calls, or randomization.
* Do NOT use config.constants.CONDITION_DISPLAY_NAMES — the display labels
  here use generator-specific prose (British spellings, lowercase, short forms)
  that differ intentionally from the formal schema display names in constants.

R2 change history
-----------------
Extracted _format_conditions() from visit_generator.py (L827) and
medication_generator.py (L530). Both copies were 100% identical; this file
is now the single source of truth.
"""

from __future__ import annotations


def _format_conditions(conditions: tuple[str, ...]) -> str:
    """Join conditions into a readable string for event summaries and reason fields.

    Uses generator-specific lowercase prose labels (British spelling where
    applicable). These labels appear in clinical_event.event_summary and
    medication reason strings — they must NOT be changed without re-validating
    the full 15-patient generation output.

    Do NOT replace the display dict with config.constants.CONDITION_DISPLAY_NAMES;
    that constant uses different casing and spellings (e.g. 'Iron deficiency anemia'
    vs. 'iron deficiency anaemia' here).
    """
    display = {
        "T2DM":             "type 2 diabetes",
        "HTN":              "hypertension",
        "Asthma":           "asthma",
        "IDA":              "iron deficiency anaemia",
        "GERD":             "GERD",
        "Dyslipidemia":     "dyslipidaemia",
        "Allergic_Rhinitis":"allergic rhinitis",
        "UTI":              "urinary tract infection",
        "CKD":              "chronic kidney disease",
        "Acute_URTI":       "acute upper respiratory tract infection",
    }
    parts = [display.get(c, c) for c in conditions]
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


__all__ = ["_format_conditions"]
