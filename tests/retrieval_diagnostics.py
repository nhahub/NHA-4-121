"""
tests/retrieval_diagnostics.py  —  Step 17 diagnostic helper

Provides focused debugging tools for individual failed queries.
Use interactively after reviewing the test report.

Usage examples:
    PYTHONPATH=. clinical-rag-env/bin/python3 -c "
    from tests.retrieval_diagnostics import diagnose_query
    diagnose_query('Q009')
    "

    PYTHONPATH=. clinical-rag-env/bin/python3 -c "
    from tests.retrieval_diagnostics import check_visit_role_vocabulary
    check_visit_role_vocabulary('PAT-CHR-001', 'partial_adherence')
    "

    PYTHONPATH=. clinical-rag-env/bin/python3 -c "
    from tests.retrieval_diagnostics import compute_patient_chunk_similarity
    compute_patient_chunk_similarity('PAT-CHR-001', 'doctor_note')
    "

    PYTHONPATH=. clinical-rag-env/bin/python3 -c "
    from tests.retrieval_diagnostics import debug_without_patient_filter
    debug_without_patient_filter('trouble taking medication consistently')
    "
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.paths import CHROMADB_DIR

QUERIES_PATH     = Path(__file__).resolve().parent / "retrieval_challenge_queries.json"
COLLECTION_NAME  = "clinical_records_v17_lite"
CHROMA_PERSIST_DIR = CHROMADB_DIR
MODEL_NAME       = "sentence-transformers/all-MiniLM-L6-v2"

_SIM_CRITICAL = 0.92
_SIM_WARN     = 0.87

_FAILURE_ROOT_CAUSES = {
    "wrong_source_type":    "Correct patient but wrong source_type ranked first. Check enrichment text specificity.",
    "missing_vocabulary":   "Expected keyword not in any chunk. Check SOAP vocabulary for visit_role.",
    "wrong_visit":          "Correct source_type but from wrong visit_role. Check _VISIT_ROLE_PHRASES.",
    "missing_role":         "Expected visit_role not in top_k. SOAP for that role may lack distinctive phrases.",
    "lab_trend_insufficient": "Fewer than 2 lab_result chunks from different visits. Strengthen trend vocabulary.",
    "post_discharge_missing": "No post-discharge evidence in top_k. Check discharge_summary/post_discharge chunk construction.",
    "wrong_patient":        "CRITICAL: patient_id filter failed. Check ChromaDB where clause.",
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _get_collection(persist_dir: Path, collection_name: str):
    import chromadb
    client = chromadb.PersistentClient(path=str(persist_dir))
    return client.get_collection(name=collection_name)


def _get_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def _load_query(query_id: str) -> dict:
    with open(QUERIES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    for q in data["queries"]:
        if q["id"] == query_id:
            return q
    raise ValueError(f"Query {query_id!r} not found in {QUERIES_PATH.name}")


def _embed(model, text: str):
    return model.encode(text, normalize_embeddings=True)


def _query_collection(
    collection,
    embedding,
    n_results: int,
    where: dict | None = None,
) -> list[dict]:
    total = collection.count()
    n = min(n_results, max(total, 1))
    raw = collection.query(
        query_embeddings=[embedding.tolist()],
        n_results=n,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    return [
        {
            "chunk_id": raw["ids"][0][i],
            "text":     raw["documents"][0][i],
            "metadata": raw["metadatas"][0][i],
            "distance": raw["distances"][0][i],
        }
        for i in range(len(raw["ids"][0]))
    ]


# ---------------------------------------------------------------------------
# 1. Diagnose one query in detail
# ---------------------------------------------------------------------------

def diagnose_query(
    query_id: str,
    queries_path: Path = QUERIES_PATH,
    persist_dir: Path = CHROMA_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
) -> None:
    """
    Print a full diagnostic for one query, showing top-10 results,
    pass/fail status per rule, root cause, and suggested fix.
    """
    from tests.test_retrieval_challenge import evaluate_pass_rule, _classify_root_cause

    q          = _load_query(query_id)
    model      = _get_model()
    collection = _get_collection(persist_dir, collection_name)

    where  = {"patient_id": {"$eq": q["patient_id"]}}
    emb    = _embed(model, q["query"])
    results = _query_collection(collection, emb, n_results=10, where=where)

    sep = "=" * 78
    hr  = "─" * 78
    print(f"\n{sep}")
    print(f"DIAGNOSTIC: {query_id}  |  {q['difficulty']}  |  {q['patient_id']}")
    print(sep)
    print(f"Query:    {q['query']}")
    print(f"Expected source_types:  {q.get('expected_source_types', [])}")
    print(f"Expected keywords:      {q.get('expected_chunks_contain', [])}")
    print(f"Expected visit_roles:   {q.get('expected_visit_roles', [])}")
    print(f"Pass rules:             {q['pass_rule']}")
    print(f"Semantic note:          {q.get('semantic_note', '')}")

    print(f"\n{hr}")
    print(f"TOP-10 RETRIEVED RESULTS (patient-scoped):")
    print(hr)
    for i, r in enumerate(results):
        meta = r["metadata"]
        print(f"\n  [{i+1}] chunk_id={r['chunk_id']}")
        print(f"       source_type={meta.get('source_type')}  "
              f"visit_role={meta.get('visit_role')}  "
              f"distance={r['distance']:.4f}")
        print(f"       visit_id={meta.get('visit_id')}  "
              f"visit_date={meta.get('visit_date')}")
        print(f"       Text (first 300 chars):")
        print(f"       {r['text'][:300]!r}")

    # Evaluate pass rules individually
    print(f"\n{hr}")
    print("PASS RULE EVALUATION:")
    print(hr)
    rules = q["pass_rule"] if isinstance(q["pass_rule"], list) else [q["pass_rule"]]
    for rule in rules:
        q_single = dict(q, pass_rule=rule)
        passed, reason = evaluate_pass_rule(q_single, results[:q["top_k"]])
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}  [{rule}]")
        if reason:
            print(f"         {reason}")

    # Overall
    passed_overall, failure_reason = evaluate_pass_rule(q, results[:q["top_k"]])
    print(f"\nOverall: {'PASS ✓' if passed_overall else 'FAIL ✗'}")

    if not passed_overall and failure_reason:
        rc = _classify_root_cause(q, results[:q["top_k"]], failure_reason)
        desc = _FAILURE_ROOT_CAUSES.get(rc, "Unknown root cause.")
        print(f"\nRoot cause:    [{rc}]")
        print(f"Description:   {desc}")
        print(f"\nSuggested fix:")
        print(f"  1. Run: check_visit_role_vocabulary('{q['patient_id']}', '<visit_role>')")
        print(f"  2. Run: compute_patient_chunk_similarity('{q['patient_id']}', 'doctor_note')")
        print(f"  3. Run: debug_without_patient_filter(\"{q['query']}\")")
        print(f"  4. If keyword missing: add phrase to SOAP assessment for visit_role.")
        print(f"  5. Re-ingest: PYTHONPATH=. python scripts/ingest_all.py --clean --mode v17_lite")

    print(sep)


# ---------------------------------------------------------------------------
# 2. Check chunk vocabulary for a patient + visit_role
# ---------------------------------------------------------------------------

def check_visit_role_vocabulary(
    patient_id: str,
    visit_role: str,
    persist_dir: Path = CHROMA_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
) -> None:
    """
    Retrieve all chunks for the given patient and visit_role and print
    their full text. Use to verify visit_role phrase injection is present.
    """
    import chromadb
    client     = chromadb.PersistentClient(path=str(persist_dir))
    collection = client.get_collection(name=collection_name)

    raw = collection.get(
        where={"$and": [
            {"patient_id": {"$eq": patient_id}},
            {"visit_role":  {"$eq": visit_role}},
        ]},
        include=["documents", "metadatas"],
    )

    sep = "=" * 78
    hr  = "─" * 78
    print(f"\n{sep}")
    print(f"VOCABULARY CHECK: {patient_id}  |  visit_role={visit_role}")
    print(sep)
    print(f"Chunks found: {len(raw['ids'])}")

    for i, (chunk_id, doc, meta) in enumerate(
        zip(raw["ids"], raw["documents"], raw["metadatas"])
    ):
        print(f"\n{hr}")
        print(f"[{i+1}] {chunk_id}")
        print(f"  source_type={meta.get('source_type')}  "
              f"visit_id={meta.get('visit_id')}  "
              f"visit_date={meta.get('visit_date')}")
        print(f"\nFULL TEXT:")
        print(doc)

    if not raw["ids"]:
        print(f"\nNo chunks found for patient={patient_id}, visit_role={visit_role}.")
        print("Check that the visit_role label matches exactly (case-sensitive).")
    print(sep)


# ---------------------------------------------------------------------------
# 3. Compute inter-chunk similarity for a patient
# ---------------------------------------------------------------------------

def compute_patient_chunk_similarity(
    patient_id: str,
    source_type: str = "doctor_note",
    persist_dir: Path = CHROMA_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
) -> None:
    """
    Retrieve all chunks of source_type for the patient, compute pairwise
    cosine similarity from stored embeddings, and print a similarity matrix.

    Note: ChromaDB does not expose stored embeddings via .get() in all versions.
    We re-encode the chunk texts to approximate the stored embeddings.
    """
    import chromadb
    import numpy as np

    client     = chromadb.PersistentClient(path=str(persist_dir))
    collection = client.get_collection(name=collection_name)

    raw = collection.get(
        where={"$and": [
            {"patient_id":  {"$eq": patient_id}},
            {"source_type": {"$eq": source_type}},
        ]},
        include=["documents", "metadatas"],
    )

    sep = "=" * 78
    hr  = "─" * 78
    print(f"\n{sep}")
    print(f"INTER-CHUNK SIMILARITY: {patient_id}  |  source_type={source_type}")
    print(sep)

    if len(raw["ids"]) < 2:
        print(f"Only {len(raw['ids'])} chunk(s) found — need ≥2 for similarity matrix.")
        print(sep)
        return

    model = _get_model()
    texts = raw["documents"]
    ids   = raw["ids"]
    roles = [m.get("visit_role", "?") for m in raw["metadatas"]]

    print(f"Re-encoding {len(texts)} chunks with {MODEL_NAME} …")
    embs = model.encode(texts, normalize_embeddings=True)

    # Pairwise cosine similarity (dot product after normalization)
    sim_matrix = embs @ embs.T

    print(f"\nSimilarity matrix (higher = more similar):")
    print(f"{'':30}", end="")
    for cid in ids:
        print(f"  {cid[-20:]:>20}", end="")
    print()

    issues: list[tuple[str, str, float, str]] = []
    for i in range(len(ids)):
        print(f"{ids[i][-30:]:30}", end="")
        for j in range(len(ids)):
            sim = sim_matrix[i, j]
            print(f"  {sim:>20.4f}", end="")
            if i < j:
                if sim >= _SIM_CRITICAL:
                    issues.append((ids[i], ids[j], sim, "CRITICAL"))
                elif sim >= _SIM_WARN:
                    issues.append((ids[i], ids[j], sim, "WARN"))
        print()

    print(f"\nThresholds:")
    print(f"  >= {_SIM_CRITICAL}  CRITICAL: near-duplicate embedding — distinct vocabulary urgently needed")
    print(f"  >= {_SIM_WARN}  WARN:     review vocabulary diversity between these visits")
    print(f"  <  {_SIM_WARN}  OK")

    if issues:
        print(f"\nIssues found ({len(issues)}):")
        print(hr)
        for a, b, sim, level in issues:
            ra = roles[ids.index(a)]
            rb = roles[ids.index(b)]
            print(f"  [{level}] sim={sim:.4f}  {a} ({ra})  <->  {b} ({rb})")
            if level == "CRITICAL":
                print(f"    Fix: Add more temporally-specific vocabulary to SOAP for one of these visit_roles.")
    else:
        print("\nAll pairs within acceptable similarity range. ✓")
    print(sep)


# ---------------------------------------------------------------------------
# 4. Debug without patient filter
# ---------------------------------------------------------------------------

def debug_without_patient_filter(
    query_text: str,
    top_k: int = 10,
    persist_dir: Path = CHROMA_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
) -> None:
    """
    Run query_text against the full collection without patient_id filter.
    Shows what raw embedding space returns — useful for confirming vocabulary exists.
    """
    model      = _get_model()
    collection = _get_collection(persist_dir, collection_name)

    emb     = _embed(model, query_text)
    results = _query_collection(collection, emb, n_results=top_k, where=None)

    sep = "=" * 78
    hr  = "─" * 78
    print(f"\n{sep}")
    print(f"RAW RETRIEVAL (no patient filter) — top {top_k}")
    print(f"Query: {query_text!r}")
    print(sep)

    if not results:
        print("No results returned from collection.")
    else:
        for i, r in enumerate(results):
            meta = r["metadata"]
            print(f"\n[{i+1}] {r['chunk_id']}")
            print(f"  patient_id={meta.get('patient_id')}  "
                  f"source_type={meta.get('source_type')}  "
                  f"visit_role={meta.get('visit_role')}  "
                  f"distance={r['distance']:.4f}")
            print(f"  {r['text'][:200]!r}")

    patient_ids = [r["metadata"].get("patient_id") for r in results]
    from collections import Counter
    dist = Counter(patient_ids)
    print(f"\n{hr}")
    print(f"Patient distribution in top-{top_k}: {dict(dist)}")
    print(f"\nInterpretation:")
    print(f"  If expected vocabulary exists in the collection but not in patient scope,")
    print(f"  the query vocabulary is semantically correct — the issue is anchor strength.")
    print(f"  If expected vocabulary is absent from ALL results, the SOAP/enrichment")
    print(f"  injection for that concept is missing entirely.")
    print(sep)
