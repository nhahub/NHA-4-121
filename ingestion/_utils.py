"""
ingestion/_utils.py

Package-private shared utilities for the ingestion layer.

Design rules
------------
* This module is PRIVATE to the ingestion package (leading-underscore convention).
* Do NOT import this module from outside the ingestion/ directory.
* Do NOT import from generators, validators, SOAP, or RAG layers.
* Do NOT add runtime side effects, API calls, or randomization.

R5 change history
-----------------
Extracted _conditions_pipe() from chunker.py (L716) and
metadata_builder.py (L524). Both copies were 100% identical; this file
is now the single source of truth.

The separator is now imported from config.constants.CONDITIONS_METADATA_SEPARATOR
rather than hardcoded as "|", ensuring that any future separator change
in constants.py is automatically reflected here.
"""

from __future__ import annotations

from config.constants import CONDITIONS_METADATA_SEPARATOR


def _conditions_pipe(patient: dict) -> str:
    """Return patient conditions as a pipe-separated string.

    Reads patient["conditions"] and joins non-blank condition strings using
    CONDITIONS_METADATA_SEPARATOR ("|") from config/constants.py.

    Returns an empty string if the patient has no conditions.

    Do NOT replace CONDITIONS_METADATA_SEPARATOR with a hardcoded "|" literal;
    constants.py is the single source of truth for the separator value.
    """
    conds = patient.get("conditions") or []
    return CONDITIONS_METADATA_SEPARATOR.join(
        str(c) for c in conds if str(c).strip()
    )


__all__ = ["_conditions_pipe"]
