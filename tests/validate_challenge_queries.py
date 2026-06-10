"""
tests/validate_challenge_queries.py

Validates the structure of retrieval_challenge_queries.json
without running any retrieval.

Run: PYTHONPATH=. python tests/validate_challenge_queries.py
"""

import json
from pathlib import Path

QUERIES_PATH = Path(__file__).resolve().parent / "retrieval_challenge_queries.json"

REQUIRED_QUERY_FIELDS = {
    "id", "difficulty", "patient_id", "query",
    "expected_source_types", "expected_chunks_contain",
    "expected_visit_roles", "top_k", "pass_rule", "semantic_note",
}

VALID_DIFFICULTIES = {"easy", "medium", "hard", "critical"}

VALID_PATIENT_IDS = {
    "PAT-NRM-001",
    "PAT-MOD-001", "PAT-MOD-002", "PAT-MOD-003", "PAT-MOD-004", "PAT-MOD-005",
    "PAT-MOD-006", "PAT-MOD-007", "PAT-MOD-008", "PAT-MOD-009",
    "PAT-CHR-001", "PAT-CHR-002", "PAT-CHR-003", "PAT-CHR-004", "PAT-CHR-005",
}

VALID_SOURCE_TYPES = {
    "doctor_note", "lab_result", "prescription",
    "allergy", "discharge_summary", "medication_reconciliation",
}

VALID_PASS_RULES = {
    "expected_source_type_in_top_k",
    "expected_keyword_in_top_result",
    "all_expected_roles_in_top_k",
    "allergy_chunk_in_top_k",
    "medication_keyword_in_top_result",
    "post_discharge_evidence_in_top_k",
    "lab_trend_chunks_in_top_k",
    "no_wrong_patient_in_results",
}


def validate_queries(data: dict) -> list[str]:
    errors: list[str] = []

    # Top-level structure
    for key in ("version", "created_by", "total_queries", "pass_criteria", "queries"):
        if key not in data:
            errors.append(f"Missing top-level key '{key}'")

    if "queries" not in data:
        return errors

    queries = data["queries"]

    # Declared total matches actual count
    if data.get("total_queries") != len(queries):
        errors.append(
            f"total_queries={data.get('total_queries')} but {len(queries)} queries present"
        )

    ids_seen: set[str] = set()

    for i, q in enumerate(queries):
        label = q.get("id", f"index_{i}")

        # Required fields present
        for field in REQUIRED_QUERY_FIELDS:
            if field not in q:
                errors.append(f"{label}: missing required field '{field}'")

        # Difficulty valid
        if q.get("difficulty") not in VALID_DIFFICULTIES:
            errors.append(f"{label}: invalid difficulty '{q.get('difficulty')}'")

        # Patient ID valid
        if q.get("patient_id") not in VALID_PATIENT_IDS:
            errors.append(f"{label}: invalid patient_id '{q.get('patient_id')}'")

        # Query text length
        if not isinstance(q.get("query", ""), str) or len(q.get("query", "")) < 10:
            errors.append(f"{label}: query text too short or not a string")

        # semantic_note present and non-trivial
        if not isinstance(q.get("semantic_note", ""), str) or len(q.get("semantic_note", "")) < 20:
            errors.append(f"{label}: semantic_note too short or missing")

        # expected_source_types is a list (may be empty for boundary tests)
        if not isinstance(q.get("expected_source_types", None), list):
            errors.append(f"{label}: expected_source_types must be a list")
        else:
            for st in q.get("expected_source_types", []):
                if st not in VALID_SOURCE_TYPES:
                    errors.append(f"{label}: invalid source_type '{st}'")

        # expected_chunks_contain is a list (may be empty for boundary tests)
        if not isinstance(q.get("expected_chunks_contain", None), list):
            errors.append(f"{label}: expected_chunks_contain must be a list")

        # expected_visit_roles is a list
        if not isinstance(q.get("expected_visit_roles", None), list):
            errors.append(f"{label}: expected_visit_roles must be a list")

        # top_k positive integer
        if not isinstance(q.get("top_k"), int) or q["top_k"] < 1:
            errors.append(f"{label}: top_k must be a positive integer")

        # pass_rule is list or string
        pr = q.get("pass_rule")
        if isinstance(pr, str):
            pr = [pr]
        if not isinstance(pr, list) or not pr:
            errors.append(f"{label}: pass_rule must be a non-empty string or list")
        else:
            for rule in pr:
                if rule not in VALID_PASS_RULES:
                    errors.append(f"{label}: unknown pass_rule '{rule}'")

        # Unique IDs
        qid = q.get("id")
        if qid in ids_seen:
            errors.append(f"{label}: duplicate query id '{qid}'")
        ids_seen.add(qid)

        # Critical queries must always include no_wrong_patient_in_results
        if q.get("difficulty") == "critical":
            rules = [q.get("pass_rule")] if isinstance(q.get("pass_rule"), str) else q.get("pass_rule", [])
            if "no_wrong_patient_in_results" not in rules:
                errors.append(
                    f"{label}: critical query must include 'no_wrong_patient_in_results' in pass_rule"
                )

    # Distribution check
    by_difficulty: dict[str, int] = {}
    for q in queries:
        d = q.get("difficulty", "unknown")
        by_difficulty[d] = by_difficulty.get(d, 0) + 1

    min_counts = {"critical": 5, "easy": 8, "medium": 10, "hard": 7}
    for diff, min_count in min_counts.items():
        actual = by_difficulty.get(diff, 0)
        if actual < min_count:
            errors.append(
                f"Too few {diff} queries: {actual} present, minimum required is {min_count}"
            )

    # All 15 patients covered
    patients_in_queries = {q.get("patient_id") for q in queries}
    missing_patients = VALID_PATIENT_IDS - patients_in_queries
    if missing_patients:
        errors.append(f"Patients with no queries: {sorted(missing_patients)}")

    # Q025 boundary test must be present (patient boundary safety test)
    q025 = next((q for q in queries if q.get("id") == "Q025"), None)
    if q025 is None:
        errors.append("Q025 (patient boundary safety test) is missing")
    elif q025.get("patient_id") != "PAT-MOD-001":
        errors.append("Q025 must target PAT-MOD-001 (the patient with no GERD/Omeprazole)")

    return errors


if __name__ == "__main__":
    with open(QUERIES_PATH, encoding="utf-8") as f:
        data = json.load(f)

    queries = data.get("queries", [])
    errors = validate_queries(data)

    print(f"Queries file:     {QUERIES_PATH.name}")
    print(f"Total queries:    {len(queries)}")

    # Distribution summary
    by_diff: dict[str, int] = {}
    for q in queries:
        d = q.get("difficulty", "unknown")
        by_diff[d] = by_diff.get(d, 0) + 1

    print(f"Distribution:     easy={by_diff.get('easy',0)}  "
          f"medium={by_diff.get('medium',0)}  "
          f"hard={by_diff.get('hard',0)}  "
          f"critical={by_diff.get('critical',0)}")

    patients_covered = len({q.get("patient_id") for q in queries})
    print(f"Patients covered: {patients_covered}/15")
    print(f"Validation errors: {len(errors)}")

    if errors:
        for e in errors:
            print(f"  ERROR: {e}")
        raise SystemExit(1)

    print("\nAll checks passed ✓")
    print("Ready for Step 17 — test_retrieval_challenge.py")
