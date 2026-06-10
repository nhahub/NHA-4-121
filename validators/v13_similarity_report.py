"""
validators/v13_similarity_report.py

V13 — Embedding Similarity Report (Step 11)

Purpose:
    Report-only audit that detects near-duplicate SOAP notes across patients
    using cosine similarity of sentence-transformer embeddings.

    V13 is NOT a hard pipeline gate in v1.7 Lite.
    V13 produces a structured report that engineers review and act on.
    Only a human decision can escalate a V13 warning into a pipeline block.

Why this runs BEFORE chunking (not after ingestion):
    Near-duplicate SOAP texts produce near-duplicate chunk embeddings in
    ChromaDB. When two patients share a condition and their SOAP notes embed
    above 0.92 cosine similarity, retrieval becomes unstable: small changes in
    query phrasing cause the retriever to return the wrong patient's evidence.
    Fixing critical violations after ingestion requires resetting ChromaDB,
    regenerating chunks, and re-ingesting. Fixing at blueprint level costs
    one blueprint edit.

same_patient vs cross-patient pairs:
    - Cross-patient critical pairs (different patients, similarity ≥ 0.92)
      set report.passed = False. These are retrieval hazards.
    - Same-patient critical pairs (two visits from the same patient)
      are demoted to WARN, because patient-scoped filtering already
      separates them during retrieval.

Model:   sentence-transformers/all-MiniLM-L6-v2
Metric:  cosine similarity via normalized dot product (normalize_embeddings=True)
Thresholds (from config.constants):
    V13_SIMILARITY_WARN_THRESHOLD     = 0.87
    V13_SIMILARITY_CRITICAL_THRESHOLD = 0.92

Architecture rules:
    - No LLM calls.
    - No ChromaDB writes.
    - No generator / validator / SOAP file modifications.
    - Runnable independently as a standalone report tool.
    - Simple enough to be reviewed and maintained by a small team.
"""

from __future__ import annotations

import itertools
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Path bootstrap — allows both `python validators/v13_similarity_report.py`
# and `python -m validators.v13_similarity_report`
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.constants import (  # noqa: E402
    EMBEDDING_MODEL_NAME,
    JSON_ENCODING,
    JSON_INDENT,
    V13_SIMILARITY_CRITICAL_THRESHOLD,
    V13_SIMILARITY_WARN_THRESHOLD,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class V13Error(ValueError):
    """Raised when V13 cannot run safely due to a precondition failure."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class V13SimilarityRecord:
    """One pairwise similarity comparison between two SOAP texts."""

    similarity: float
    chunk_a_id: str          # "{patient_id}::{visit_id}"
    chunk_b_id: str
    patient_a: str
    patient_b: str
    visit_role_a: str
    visit_role_b: str
    same_patient: bool
    shared_conditions: list[str]
    level: Literal["critical", "warn", "ok"]

    def as_dict(self) -> dict:
        return {
            "similarity": round(self.similarity, 6),
            "chunk_a_id": self.chunk_a_id,
            "chunk_b_id": self.chunk_b_id,
            "patient_a": self.patient_a,
            "patient_b": self.patient_b,
            "visit_role_a": self.visit_role_a,
            "visit_role_b": self.visit_role_b,
            "same_patient": self.same_patient,
            "shared_conditions": self.shared_conditions,
            "level": self.level,
        }


@dataclass
class V13Report:
    """Complete V13 similarity audit report."""

    model_name: str
    chunks_checked: int
    critical_count: int
    warn_count: int
    critical_pairs: list[V13SimilarityRecord]
    warn_pairs: list[V13SimilarityRecord]
    passed: bool           # True iff zero critical cross-patient pairs
    run_timestamp_utc: str

    def as_dict(self) -> dict:
        cross_patient_critical = sum(
            1 for p in self.critical_pairs if not p.same_patient
        )
        same_patient_critical = sum(
            1 for p in self.critical_pairs if p.same_patient
        )
        return {
            "model_name": self.model_name,
            "chunks_checked": self.chunks_checked,
            "critical_count": self.critical_count,
            "warn_count": self.warn_count,
            "cross_patient_critical": cross_patient_critical,
            "same_patient_critical": same_patient_critical,
            "passed": self.passed,
            "run_timestamp_utc": self.run_timestamp_utc,
            "critical_pairs": [p.as_dict() for p in self.critical_pairs],
            "warn_pairs": [p.as_dict() for p in self.warn_pairs],
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_soap_text(visit: dict) -> str:
    """Concatenate all four SOAP sections into one string for embedding."""
    soap = visit.get("soap_note") or {}
    return " ".join([
        soap.get("subjective", ""),
        soap.get("objective", ""),
        soap.get("assessment", ""),
        soap.get("plan", ""),
    ]).strip()


def _build_auditable_chunks(patients: list[dict]) -> list[dict]:
    """
    Build a flat list of auditable chunk dicts from all patients.

    Each chunk has:
        text          — concatenated SOAP text
        chunk_id      — "{patient_id}::{visit_id}"
        patient_id    — str
        visit_id      — str
        visit_role    — str
        conditions    — list[str]
        same_patient  — used later for pair comparison
    """
    chunks: list[dict] = []
    for patient in patients:
        patient_id = str(patient.get("patient_id", "UNKNOWN"))
        conditions = list(patient.get("conditions") or [])
        for visit in patient.get("visits", []):
            visit_id = str(visit.get("visit_id", "UNKNOWN"))
            text = _build_soap_text(visit)
            if not text:
                logger.warning(
                    "V13: Skipping visit '%s' for patient '%s' — "
                    "SOAP text is empty (pre-generation visit?).",
                    visit_id,
                    patient_id,
                )
                continue
            chunks.append({
                "text": text,
                "chunk_id": f"{patient_id}::{visit_id}",
                "patient_id": patient_id,
                "visit_id": visit_id,
                "visit_role": str(visit.get("visit_role", "")),
                "conditions": conditions,
            })
    return chunks


def _determine_level(
    similarity: float,
    warn_threshold: float,
    critical_threshold: float,
) -> Literal["critical", "warn", "ok"]:
    if similarity >= critical_threshold:
        return "critical"
    if similarity >= warn_threshold:
        return "warn"
    return "ok"


# ---------------------------------------------------------------------------
# Precondition checks
# ---------------------------------------------------------------------------


def _validate_preconditions(
    patients: list[dict],
    warn_threshold: float,
    critical_threshold: float,
) -> None:
    """Raise V13Error if any precondition is violated."""
    if not patients:
        raise V13Error("V13: patients list is empty. Cannot run similarity report.")

    if warn_threshold >= critical_threshold:
        raise V13Error(
            f"V13: warn_threshold ({warn_threshold}) must be strictly less than "
            f"critical_threshold ({critical_threshold})."
        )

    for patient in patients:
        patient_id = str(patient.get("patient_id", "UNKNOWN"))
        visits = patient.get("visits")
        if not visits:
            raise V13Error(
                f"V13: Patient '{patient_id}' has no visits. "
                "Run the visit generator before V13."
            )

        for visit in visits:
            visit_id = str(visit.get("visit_id", "UNKNOWN"))
            soap = visit.get("soap_note") or {}
            subjective = str(soap.get("subjective", "")).strip()
            objective  = str(soap.get("objective", "")).strip()
            assessment = str(soap.get("assessment", "")).strip()
            plan       = str(soap.get("plan", "")).strip()

            if not any([subjective, objective, assessment, plan]):
                raise V13Error(
                    f"V13: Visit '{visit_id}' for patient '{patient_id}' has an "
                    "all-empty soap_note. The SOAP auditor should have caught this. "
                    "Run soap_generator and soap_auditor before V13."
                )


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def _embed_chunks(texts: list[str], model_name: str) -> "np.ndarray":  # type: ignore[name-defined]
    """Embed texts using sentence-transformers with normalized embeddings."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import]
    except ImportError as exc:
        raise V13Error(
            "sentence-transformers is not installed. "
            "Install it with: pip install sentence-transformers"
        ) from exc

    model = SentenceTransformer(model_name)
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return embeddings


def _compute_pairs(
    chunks: list[dict],
    embeddings,           # np.ndarray, shape (N, D)
    warn_threshold: float,
    critical_threshold: float,
) -> tuple[list[V13SimilarityRecord], list[V13SimilarityRecord]]:
    """
    Compute pairwise cosine similarity for all unique chunk pairs.

    Returns:
        (critical_pairs, warn_pairs) — sorted by descending similarity.
    """
    critical_pairs: list[V13SimilarityRecord] = []
    warn_pairs: list[V13SimilarityRecord] = []

    n = len(chunks)
    for i, j in itertools.combinations(range(n), 2):
        chunk_a = chunks[i]
        chunk_b = chunks[j]

        # Skip if same visit (defensive — combinations already skips i==j)
        if chunk_a["visit_id"] == chunk_b["visit_id"]:
            continue

        similarity = float(embeddings[i] @ embeddings[j])
        level = _determine_level(similarity, warn_threshold, critical_threshold)

        if level == "ok":
            continue

        same_patient = chunk_a["patient_id"] == chunk_b["patient_id"]
        shared_conditions = sorted(
            set(chunk_a["conditions"]) & set(chunk_b["conditions"])
        )

        # Same-patient critical pairs are demoted to warn in reporting
        # (patient-scoped retrieval already separates them).
        effective_level: Literal["critical", "warn"] = level
        if level == "critical" and same_patient:
            effective_level = "warn"

        record = V13SimilarityRecord(
            similarity=similarity,
            chunk_a_id=chunk_a["chunk_id"],
            chunk_b_id=chunk_b["chunk_id"],
            patient_a=chunk_a["patient_id"],
            patient_b=chunk_b["patient_id"],
            visit_role_a=chunk_a["visit_role"],
            visit_role_b=chunk_b["visit_role"],
            same_patient=same_patient,
            shared_conditions=shared_conditions,
            level=effective_level,
        )

        if effective_level == "critical":
            critical_pairs.append(record)
        else:
            warn_pairs.append(record)

    critical_pairs.sort(key=lambda r: r.similarity, reverse=True)
    warn_pairs.sort(key=lambda r: r.similarity, reverse=True)

    return critical_pairs, warn_pairs


# ---------------------------------------------------------------------------
# Public API — console printer
# ---------------------------------------------------------------------------


def print_v13_report(report: V13Report) -> None:
    """Print the V13 report in the required human-readable format."""
    cross_patient_critical = sum(
        1 for p in report.critical_pairs if not p.same_patient
    )
    same_patient_critical = sum(
        1 for p in report.critical_pairs if p.same_patient
    )

    print("=== V13 EMBEDDING SIMILARITY REPORT ===")
    print(f"Model:              {report.model_name}")
    print(f"Chunks checked:     {report.chunks_checked}")
    print(
        f"Critical pairs:     {report.critical_count}"
        f"   (cross-patient: {cross_patient_critical},"
        f" same-patient: {same_patient_critical})"
    )
    print(f"Warn pairs:         {report.warn_count}")
    print(f"Passed:             {report.passed}")
    print(f"Timestamp:          {report.run_timestamp_utc}")
    print()

    if not report.critical_pairs and not report.warn_pairs:
        print(
            "No near-duplicate SOAP texts detected. "
            "Dataset is ready for chunking."
        )
        print("=== END V13 REPORT ===")
        return

    if report.critical_pairs:
        print("CRITICAL PAIRS:")
        for pair in report.critical_pairs:
            print(f"  {pair.chunk_a_id} vs {pair.chunk_b_id}")
            print(f"  Similarity: {pair.similarity:.4f}")
            print(f"  Shared conditions: {pair.shared_conditions}")
            print(f"  Visit roles: {pair.visit_role_a} vs {pair.visit_role_b}")
            print(
                "  Action: Review blueprint story_arc or soap_style "
                "for these two patients."
            )
            print()

    if report.warn_pairs:
        shown = report.warn_pairs[:10]
        print("WARN PAIRS (first 10):")
        for pair in shown:
            print(f"  {pair.chunk_a_id} vs {pair.chunk_b_id}")
            print(f"  Similarity: {pair.similarity:.4f}")
            print(f"  Shared conditions: {pair.shared_conditions}")
            print(
                "  Action: Review if further story diversity is needed."
            )
            print()
        if len(report.warn_pairs) > 10:
            print(
                f"  ... {len(report.warn_pairs) - 10} more warn pairs. "
                "See JSON report for full list."
            )

    print("=== END V13 REPORT ===")


# ---------------------------------------------------------------------------
# Public API — report writer
# ---------------------------------------------------------------------------


def write_v13_report(
    report: V13Report,
    output_path: Path,
) -> None:
    """Write the V13 report as a JSON file to output_path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding=JSON_ENCODING) as fh:
        json.dump(report.as_dict(), fh, indent=JSON_INDENT, ensure_ascii=False)
        fh.write("\n")

    logger.info("V13 report written to: %s", output_path)


# ---------------------------------------------------------------------------
# Public API — primary entry point
# ---------------------------------------------------------------------------


def run_v13_similarity_report(
    patients: list[dict],
    *,
    model_name: str = EMBEDDING_MODEL_NAME,
    warn_threshold: float = V13_SIMILARITY_WARN_THRESHOLD,
    critical_threshold: float = V13_SIMILARITY_CRITICAL_THRESHOLD,
    print_report: bool = True,
) -> V13Report:
    """
    Build auditable chunks from all patients, embed them, compute pairwise
    similarity, build and optionally print the V13 report.

    Args:
        patients:           List of fully-generated patient dicts (post-SOAP).
        model_name:         Sentence-transformer model to use for embedding.
        warn_threshold:     Cosine similarity >= this → WARN.
        critical_threshold: Cosine similarity >= this → CRITICAL.
        print_report:       Whether to print the report to stdout.

    Returns:
        V13Report with all pair records and pass/fail status.

    Raises:
        V13Error: If preconditions are not met (empty patients, no visits,
                  empty SOAP, or invalid thresholds).
    """
    _validate_preconditions(patients, warn_threshold, critical_threshold)

    # Step 1 — Build auditable chunks
    chunks = _build_auditable_chunks(patients)

    if len(chunks) < 2:
        logger.warning(
            "V13: Only %d auditable chunk(s) found. Report will be trivially empty. "
            "Ensure all patients have fully generated SOAP notes.",
            len(chunks),
        )

    timestamp = datetime.now(timezone.utc).isoformat()

    # Trivial case: nothing to compare
    if len(chunks) < 2:
        report = V13Report(
            model_name=model_name,
            chunks_checked=len(chunks),
            critical_count=0,
            warn_count=0,
            critical_pairs=[],
            warn_pairs=[],
            passed=True,
            run_timestamp_utc=timestamp,
        )
        if print_report:
            print_v13_report(report)
        return report

    # Step 2 — Embed all texts
    texts = [chunk["text"] for chunk in chunks]
    embeddings = _embed_chunks(texts, model_name)

    # Step 3 — Compute pairwise similarity
    critical_pairs, warn_pairs = _compute_pairs(
        chunks, embeddings, warn_threshold, critical_threshold
    )

    # Step 4 — Determine pass/fail
    # passed = True iff zero critical cross-patient pairs
    cross_patient_critical = [p for p in critical_pairs if not p.same_patient]
    passed = len(cross_patient_critical) == 0

    report = V13Report(
        model_name=model_name,
        chunks_checked=len(chunks),
        critical_count=len(critical_pairs),
        warn_count=len(warn_pairs),
        critical_pairs=critical_pairs,
        warn_pairs=warn_pairs,
        passed=passed,
        run_timestamp_utc=timestamp,
    )

    if print_report:
        print_v13_report(report)

    return report


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    "V13Error",
    "V13SimilarityRecord",
    "V13Report",
    "run_v13_similarity_report",
    "write_v13_report",
    "print_v13_report",
]
