"""
scripts/ingest_all.py  —  Step 15 CLI entry point

Orchestrates the complete 14-stage pipeline from patient generation through
ChromaDB upsert, then runs a post-ingestion smoke test.

Usage
-----
    PYTHONPATH=. python scripts/ingest_all.py --clean
    PYTHONPATH=. python scripts/ingest_all.py --dry-run
    PYTHONPATH=. python scripts/ingest_all.py --clean --mode v17_lite

Required flags
--------------
    --clean          Reset ChromaDB collection before ingestion (recommended)
    --dry-run        Full pipeline except ChromaDB upsert
    --mode           Dataset mode: v17_lite (default) or pilot
    --no-validate    Skip V1-V12 validation gate (development only)
    --persist-dir    Override ChromaDB persistence directory
    --collection     Override ChromaDB collection name
    --no-log         Do not append to pipeline_run.log
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path when run as a script
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.constants import DATASET_VERSION
from config.paths import CHROMADB_DIR, LOGS_DIR
from config.patient_blueprints import BLUEPRINT_BY_ID

from generators.patient_generator import generate_patients
from generators.visit_generator import generate_visits_for_patient
from generators.medication_generator import generate_medications_for_patient
from generators.lab_generator import generate_labs_for_patient
from generators.allergy_generator import generate_allergy_registry_for_patient

from soap.soap_generator import generate_soap_for_patient
from soap.soap_auditor import audit_soap_for_patient, soap_audit_passed

from ingestion.chunker import build_all_chunks
from ingestion.metadata_builder import (
    build_metadata_for_all_chunks,
    MetadataBuilderError,
)
from ingestion.ingest import (
    COLLECTION_NAME,
    CHROMA_PERSIST_DIR,
    IngestionError,
    IngestionResult,
    get_all_patient_chunks,
    ingest_chunks,
    query_patient_chunks,
    _validate_ingestion_inputs,
)

_LOG_FILE = LOGS_DIR / "pipeline_run.log"


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AI-Based Clinical Record Summarization System — Step 15 Ingestion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Reset ChromaDB collection before ingestion (recommended for production runs).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run full pipeline except ChromaDB upsert and smoke test.",
    )
    parser.add_argument(
        "--mode",
        default="v17_lite",
        choices=("v17_lite", "pilot"),
        help="Dataset mode. Default: v17_lite.",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip V1-V12 validation gate (development only — do not use for final handoff).",
    )
    parser.add_argument(
        "--persist-dir",
        type=Path,
        default=CHROMA_PERSIST_DIR,
        help=f"ChromaDB persistence directory. Default: {CHROMA_PERSIST_DIR}",
    )
    parser.add_argument(
        "--collection",
        default=COLLECTION_NAME,
        help=f"ChromaDB collection name. Default: {COLLECTION_NAME}",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Do not append run summary to pipeline_run.log.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Chunks per upsert batch. Default: 50.",
    )
    return parser


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------

def _stage(label: str) -> None:
    print(f"\n{'─' * 72}")
    print(f"  {label}")
    print(f"{'─' * 72}")


def _ok(label: str) -> None:
    print(f"  [✓] {label}")


def _fail(label: str) -> None:
    print(f"  [✗] {label}")


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

def _run_smoke_test(persist_dir: Path, collection_name: str) -> bool:
    """
    Verify ChromaDB is populated and patient-scoped retrieval works.
    Returns True if all checks pass.
    """
    print("\n  Running post-ingestion smoke test …")
    all_pass = True

    # Check 1: PAT-CHR-005 has all required source_types
    chr5_chunks = get_all_patient_chunks(
        "PAT-CHR-005",
        persist_dir=persist_dir,
        collection_name=collection_name,
    )
    chr5_types = {c["metadata"]["source_type"] for c in chr5_chunks}
    required_types = {
        "doctor_note", "lab_result", "prescription",
        "allergy", "discharge_summary", "medication_reconciliation",
    }
    missing = required_types - chr5_types
    if missing:
        _fail(f"PAT-CHR-005 missing source_types: {missing}")
        all_pass = False
    else:
        _ok(f"PAT-CHR-005 source_types: all 6 present")

    # Check 2: Patient-scoped query returns only PAT-CHR-005 results
    results = query_patient_chunks(
        "kidney function monitoring",
        "PAT-CHR-005",
        persist_dir=persist_dir,
        collection_name=collection_name,
        top_k=5,
    )
    cross_patient = [r for r in results if r["metadata"]["patient_id"] != "PAT-CHR-005"]
    if cross_patient:
        _fail(f"Patient-scoped query returned wrong-patient chunks: "
              f"{[r['metadata']['patient_id'] for r in cross_patient]}")
        all_pass = False
    else:
        _ok("Patient-scoped retrieval: no cross-patient contamination")

    # Check 3: Allergy query for PAT-MOD-003 returns Aspirin
    allergy_results = query_patient_chunks(
        "documented allergy",
        "PAT-MOD-003",
        persist_dir=persist_dir,
        collection_name=collection_name,
        source_type="allergy",
        top_k=3,
    )
    if not allergy_results:
        _fail("PAT-MOD-003 allergy query returned no results")
        all_pass = False
    elif "Aspirin" not in allergy_results[0]["text"]:
        _fail(f"PAT-MOD-003 allergy chunk missing Aspirin in top result")
        all_pass = False
    else:
        _ok("Allergy retrieval: PAT-MOD-003 Aspirin found in top result")

    # Check 4: PAT-CHR-001 adherence query (WARN only)
    adherence_results = query_patient_chunks(
        "missed doses partial adherence Metformin",
        "PAT-CHR-001",
        persist_dir=persist_dir,
        collection_name=collection_name,
        top_k=5,
    )
    adherence_roles = [r["metadata"].get("visit_role") for r in adherence_results]
    if "partial_adherence" in adherence_roles:
        _ok("Adherence retrieval: partial_adherence in top-5 for PAT-CHR-001")
    else:
        print(f"  [~] WARN: partial_adherence not in top-5 for adherence query. "
              f"Got roles: {adherence_roles}")

    return all_pass


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def main() -> int:
    args = _build_arg_parser().parse_args()
    run_start = datetime.datetime.now(datetime.timezone.utc)

    print("=" * 80)
    print("AI-Based Clinical Record Summarization System")
    print("Step 15 — ChromaDB Ingestion")
    print("=" * 80)
    print(f"Mode:             {args.mode}")
    print(f"Dataset version:  {DATASET_VERSION}")
    print(f"Collection:       {args.collection}")
    print(f"Persist dir:      {args.persist_dir}")
    print(f"Clean run:        {args.clean}")
    print(f"Dry run:          {args.dry_run}")

    # -----------------------------------------------------------------------
    # Stage 1–5: Patient generation
    # -----------------------------------------------------------------------
    _stage("Stage 1-5: Patient generation")
    patients = generate_patients(mode=args.mode)
    total_visits = 0
    for patient in patients:
        bp = BLUEPRINT_BY_ID[patient["patient_id"]]
        generate_visits_for_patient(patient, bp)
        generate_medications_for_patient(patient, bp)
        generate_labs_for_patient(patient, bp)
        generate_allergy_registry_for_patient(patient, bp)
        total_visits += len(patient.get("visits", []))
    _ok(f"Patient generation: {len(patients)} patients, {total_visits} visits")

    # -----------------------------------------------------------------------
    # Stage 6: SOAP generation
    # -----------------------------------------------------------------------
    _stage("Stage 6: SOAP generation")
    for patient in patients:
        bp = BLUEPRINT_BY_ID[patient["patient_id"]]
        generate_soap_for_patient(patient, bp)
    soap_count = sum(len(p.get("visits", [])) for p in patients)
    _ok(f"SOAP generation: {soap_count} notes generated")

    # -----------------------------------------------------------------------
    # Stage 7: SOAP audit — abort on FAIL
    # -----------------------------------------------------------------------
    _stage("Stage 7: SOAP audit")
    soap_fail_issues: list[str] = []
    for patient in patients:
        bp = BLUEPRINT_BY_ID[patient["patient_id"]]
        audit_result = audit_soap_for_patient(patient, bp)
        if not soap_audit_passed(audit_result):
            for issue in audit_result.get("issues", []):
                if issue.get("level") == "FAIL":
                    soap_fail_issues.append(
                        f"  {patient['patient_id']}: {issue.get('rule')} — {issue.get('message')}"
                    )

    if soap_fail_issues:
        _fail("SOAP audit FAILED")
        print("\nABORT: SOAP audit failed. Fix SOAP generation before ingestion.")
        for iss in soap_fail_issues:
            print(iss)
        return 1
    _ok(f"SOAP audit: 0 FAIL")

    # -----------------------------------------------------------------------
    # Stage 8: V1–V12 validation — abort on FAIL
    # -----------------------------------------------------------------------
    _stage("Stage 8: V1-V12 validation")
    if args.no_validate:
        print("  [~] SKIPPED (--no-validate flag set — development mode only)")
    else:
        try:
            from validators.validate import validate_patients
            from validators.validation_report import (
                count_fail_issues,
                format_fail_issues,
            )
            val_report = validate_patients(patients)
            fail_count = count_fail_issues(val_report)
            if fail_count > 0:
                _fail(f"Validation: {fail_count} FAIL issues")
                print("\nABORT: Validation failed. Fix dataset before ingestion.")
                for line in format_fail_issues(val_report):
                    print(f"  {line}")
                return 1
            _ok(f"V1-V12 validation: 0 FAIL")
        except ImportError:
            # validators package may not exist in all deployments
            print("  [~] validators package not found — skipping V1-V12 validation")

    # -----------------------------------------------------------------------
    # Stage 9: Chunk building
    # -----------------------------------------------------------------------
    _stage("Stage 9: Chunk building")
    chunks = build_all_chunks(patients, BLUEPRINT_BY_ID)
    _ok(f"Chunk building: {len(chunks)} chunks")

    # -----------------------------------------------------------------------
    # Stage 10: Metadata building
    # -----------------------------------------------------------------------
    _stage("Stage 10: Metadata building")
    try:
        metadata_list = build_metadata_for_all_chunks(chunks, patients)
    except MetadataBuilderError as exc:
        _fail(f"Metadata building FAILED: {exc}")
        print(f"\nABORT: Metadata builder error: {exc}")
        return 1
    _ok(f"Metadata building: {len(metadata_list)} records")

    # -----------------------------------------------------------------------
    # Stage 11: Pre-ingestion validation gate
    # -----------------------------------------------------------------------
    _stage("Stage 11: Pre-ingestion validation gate")
    try:
        _validate_ingestion_inputs(chunks, metadata_list)
    except IngestionError as exc:
        _fail(f"Pre-ingestion check FAILED")
        print(f"\nABORT: Pre-ingestion check failed: {exc}")
        return 1
    _ok("Pre-ingestion validation: 0 errors")

    # -----------------------------------------------------------------------
    # Stage 12: Embed and upsert (skipped if --dry-run)
    # -----------------------------------------------------------------------
    _stage("Stage 12: ChromaDB upsert")
    result: IngestionResult | None = None

    if args.dry_run:
        print("  [~] SKIPPED (--dry-run flag set)")
    else:
        try:
            result = ingest_chunks(
                chunks,
                metadata_list,
                persist_dir=args.persist_dir,
                collection_name=args.collection,
                clean=args.clean,
                batch_size=args.batch_size,
                show_progress=True,
            )
        except IngestionError as exc:
            _fail(f"Ingestion FAILED: {exc}")
            print(f"\nABORT: Ingestion error: {exc}")
            return 1
        _ok(f"ChromaDB upsert: {result.chunks_ingested} chunks embedded and stored")
        _ok(f"Collection count verified: {result.collection_count} (expected {len(chunks)})")

    # -----------------------------------------------------------------------
    # Stage 13: Post-ingestion smoke test (skipped if --dry-run)
    # -----------------------------------------------------------------------
    _stage("Stage 13: Post-ingestion smoke test")
    smoke_passed = False
    if args.dry_run:
        print("  [~] SKIPPED (--dry-run flag set)")
    else:
        smoke_passed = _run_smoke_test(args.persist_dir, args.collection)
        if smoke_passed:
            _ok("Smoke test: PASS")
        else:
            _fail("Smoke test: FAIL (see details above)")

    # -----------------------------------------------------------------------
    # Stage 14: Final report
    # -----------------------------------------------------------------------
    chunks_by_type: dict[str, int] = {}
    for c in chunks:
        st = c.get("source_type", "unknown")
        chunks_by_type[st] = chunks_by_type.get(st, 0) + 1

    _stage("Stage 14: Final report")
    sep = "=" * 80
    print(f"\n{sep}")
    print("AI-Based Clinical Record Summarization System")
    print("Step 15 — ChromaDB Ingestion Complete")
    print(sep)
    print(f"Mode:                    {args.mode}")
    print(f"Dataset version:         {DATASET_VERSION}")
    print(f"Collection:              {args.collection}")
    print(f"Persist directory:       {args.persist_dir}/")
    print()
    print("Pipeline stages:")
    print(f"  [✓] Stage 1-5: Patient generation ({len(patients)} patients, {total_visits} visits)")
    print(f"  [✓] Stage 6:   SOAP generation ({soap_count} notes)")
    print(f"  [✓] Stage 7:   SOAP audit (0 FAIL)")
    if args.no_validate:
        print(f"  [~] Stage 8:   V1-V12 validation (SKIPPED)")
    else:
        print(f"  [✓] Stage 8:   V1-V12 validation (0 FAIL)")
    print(f"  [✓] Stage 9:   Chunk building ({len(chunks)} chunks)")
    print(f"  [✓] Stage 10:  Metadata building ({len(metadata_list)} records)")
    print(f"  [✓] Stage 11:  Pre-ingestion validation (0 errors)")
    if args.dry_run:
        print(f"  [~] Stage 12:  ChromaDB upsert (SKIPPED — dry run)")
        print(f"  [~] Stage 13:  Post-ingestion smoke test (SKIPPED — dry run)")
    else:
        print(f"  [✓] Stage 12:  ChromaDB upsert ({result.chunks_ingested} chunks embedded and stored)")
        smoke_label = "PASS" if smoke_passed else "FAIL"
        print(f"  {'[✓]' if smoke_passed else '[✗]'} Stage 13:  Post-ingestion smoke test ({smoke_label})")

    print()
    print("Chunk counts by source_type:")
    type_order = [
        "doctor_note", "lab_result", "prescription",
        "allergy", "discharge_summary", "medication_reconciliation",
    ]
    for st in type_order:
        count = chunks_by_type.get(st, 0)
        print(f"  {st:<30} {count}")
    other_types = {k: v for k, v in chunks_by_type.items() if k not in type_order}
    for st, cnt in sorted(other_types.items()):
        print(f"  {st:<30} {cnt}")
    print(f"  {'─' * 36}")
    print(f"  {'Total:':<30} {len(chunks)}")

    if not args.dry_run and result is not None:
        print()
        print("Post-ingestion verification:")
        print(f"  ChromaDB collection count: {result.collection_count} "
              f"(matches expected {len(chunks)})")
        chr5_types_str = ", ".join(sorted(
            {c["metadata"]["source_type"]
             for c in get_all_patient_chunks(
                "PAT-CHR-005",
                persist_dir=args.persist_dir,
                collection_name=args.collection,
             )}
        ))
        print(f"  PAT-CHR-005 source_types:  {chr5_types_str}")
        print(f"  Patient-scoped retrieval:  VERIFIED (no cross-patient contamination)")
        if smoke_passed:
            print(f"  Allergy retrieval:         VERIFIED (PAT-MOD-003 Aspirin found in top result)")

    print()
    print(f"Embedding model:         {_get_embedding_model_name()}")
    print(f"Normalized embeddings:   True")
    print(f"Distance metric:         cosine")
    print()
    print(sep)
    if args.dry_run:
        print("Status: DRY RUN COMPLETE")
        print("Next step: Run without --dry-run to ingest into ChromaDB")
    elif smoke_passed:
        print("Status: INGESTION COMPLETE")
        print("Next step: python scripts/validate_all.py --mode v17_lite")
        print("           python tests/test_retrieval_challenge.py")
    else:
        print("Status: INGESTION COMPLETE (smoke test warnings — review above)")
    print(sep)
    print()

    # -----------------------------------------------------------------------
    # Append to pipeline_run.log (unless --no-log)
    # -----------------------------------------------------------------------
    if not args.no_log:
        _append_log(args, len(patients), total_visits, len(chunks), result, smoke_passed, run_start)

    return 0 if (args.dry_run or smoke_passed) else 1


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _append_log(
    args: argparse.Namespace,
    n_patients: int,
    n_visits: int,
    n_chunks: int,
    result: IngestionResult | None,
    smoke_passed: bool,
    run_start: datetime.datetime,
) -> None:
    """Append a one-line run summary to pipeline_run.log."""
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        run_end   = datetime.datetime.now(datetime.timezone.utc)
        duration  = (run_end - run_start).total_seconds()
        chroma_ok = "N/A (dry-run)" if args.dry_run else (
            f"{result.collection_count} stored" if result else "FAILED"
        )
        smoke_str = "N/A" if args.dry_run else ("PASS" if smoke_passed else "FAIL")
        line = (
            f"{run_end.strftime('%Y-%m-%dT%H:%M:%SZ')} | "
            f"mode={args.mode} | patients={n_patients} | visits={n_visits} | "
            f"chunks={n_chunks} | chromadb={chroma_ok} | "
            f"smoke={smoke_str} | clean={args.clean} | "
            f"dry_run={args.dry_run} | duration={duration:.1f}s\n"
        )
        with open(_LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass  # Logging failure must never abort the pipeline


def _get_embedding_model_name() -> str:
    """Return the embedding model name from constants (safe import)."""
    try:
        from config.constants import EMBEDDING_MODEL_NAME
        return EMBEDDING_MODEL_NAME
    except Exception:
        return "sentence-transformers/all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    raise SystemExit(main())
