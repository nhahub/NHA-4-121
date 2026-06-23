# Architectural Review — Data Generation Layer
## AI-Based Clinical Record Summarization System · v1.7 Lite Dataset

**Review Date:** 2026-06-17  
**Reviewer Role:** Senior Data Engineering & Code Review Architect  
**Scope:** `generators/`, `validators/`, `soap/`, `ingestion/`, `config/`, `scripts/`

---

## Executive Summary

The data generation pipeline is **structurally sound and ready for final execution**. The Single Source of Truth (SSoT) principle is well-enforced through `config/constants.py` and `config/patient_blueprints.py`. However, this review surfaces **three concrete duplicate-logic risks**, **two latent boundary violations**, and **one missing guard** that should be addressed before the ChromaDB ingestion step (Step 15) is finalized.

---

## 1 — Architecture Map

```
config/constants.py          ← Authoritative: all enums, limits, regex, contract fields
config/patient_blueprints.py ← Authoritative: 15-patient dataset design intent
         │
         ▼
generators/patient_generator.py   ─ builds patient shell (demographics, metadata)
generators/visit_generator.py     ─ builds visits, vitals, SOAP stub, clinical events
generators/medication_generator.py─ populates visit["medications"] in-place
generators/lab_generator.py       ─ populates visit["labs"] in-place
generators/allergy_generator.py   ─ populates patient["allergy_registry"] in-place
         │
         ▼
soap/soap_generator.py            ─ writes visit["soap_note"] in-place (fact-only)
         │
         ▼
validators/rules.py               ─ V1–V13 quality gate (read-only, no mutation)
         │
         ▼
ingestion/chunker.py              ─ builds chunk dicts per source_type
ingestion/retrieval_enricher.py   ─ builds retrieval enrichment text (read-only)
ingestion/metadata_builder.py     ─ normalizes & validates ChromaDB metadata
         │
         ▼
scripts/test_step14.py            ─ integration + scenario + negative test harness
scripts/test_step15.py            ─ ChromaDB ingestion readiness gate
```

**Pipeline execution order (confirmed):**
1. `patient_generator` → patient shell
2. `visit_generator` → visits + vitals + SOAP stubs
3. `medication_generator` → medication records
4. `lab_generator` → lab records
5. `allergy_generator` → allergy registry
6. `soap_generator` → SOAP prose (fact-context only)
7. `soap_auditor` → safety check
8. `validators/rules.py` → V1–V12 quality gate
9. `chunker` → chunk dicts
10. `retrieval_enricher` → enrichment text (embedded inside chunker)
11. `metadata_builder` → ChromaDB-ready metadata (V13 audit)
12. ChromaDB ingest (Step 15)

---

## 2 — Rule Consistency Review

### 2.1 BP (Blood Pressure) Prohibition — ✅ CONSISTENT

The rule "BP must never appear outside `vitals`" is enforced at **five independent layers**, all referencing `BP_FORBIDDEN_LAB_TERMS` from `constants.py`:

| Layer | Enforcement point |
|---|---|
| `lab_generator._validate_lab_type()` | Blocks any BP term from entering `lab_focus` |
| `visit_generator._validate_visit_shape()` | Blocks BP keys in `retrieval_context` and `clinical_event` |
| `medication_generator._validate_medication_record()` | Blocks BP keys in any medication record |
| `ingestion/chunker.validate_chunk()` | Blocks BP keys in chunk metadata via `FORBIDDEN_CHROMA_METADATA_FIELDS_V17_LITE` |
| `ingestion/metadata_builder.validate_metadata()` | Blocks BP keys in ChromaDB metadata via `_FORBIDDEN_METADATA_KEYS` |

**Risk:** LOW — Defense-in-depth is correct. No gaps detected.

---

### 2.2 Medication Whitelist — ✅ CONSISTENT

`MEDICATION_WHITELIST` from `constants.py` is the sole truth for all medication profiles (dose, frequency, route, class). Both `medication_generator.medication_profile()` and `_validate_medication_record()` reject any unlisted medication with a hard error.

**Risk:** LOW.

---

### 2.3 Conditions Enum — ✅ CONSISTENT

`CONDITIONS` from `constants.py` is used in:
- `patient_generator._validate_blueprint_fields()` — rejects invalid conditions
- `patient_blueprints._verify_blueprints()` — self-validates at import time
- `validators/rules.py` (V4) — validates conditions in generated JSON

**Risk:** LOW.

---

### 2.4 CKD Lab Logic — ⚠️ LATENT INCONSISTENCY (RISK: MEDIUM)

Two separate CKD-specific Creatinine fallback sequences are defined **in two different files**:

**`lab_generator._generic_lab_value()` (line 369):**
```python
ckd_fallback = (1.4, 1.5, 1.6, 1.5, 1.4)
```

**`lab_generator._PATIENT_LAB_SERIES` (line 281 — PAT-CHR-002):**
```python
"Creatinine": (1.4, 1.5, 1.6, 1.5, 1.4),  # identical
```
**`lab_generator._PATIENT_LAB_SERIES` (line 297 — PAT-CHR-005):**
```python
"Creatinine": (1.5, 1.6, 1.7, 1.8, 1.6),  # different (hospitalization arc)
```

**Finding:** The generic CKD fallback at line 369 is dead code for the 15-patient dataset — all CKD patients (`PAT-CHR-002`, `PAT-CHR-005`) have explicit series in `_PATIENT_LAB_SERIES` that take priority. The fallback is only exercised by hypothetical new CKD patients without explicit series.

**Risk:** MEDIUM — Dead code risk. If a new CKD blueprint is added and the developer forgets to add an explicit series, the generic fallback silently produces clinically inconsistent values that may not match the story arc.

**Recommendation:** Add a `_PATIENT_LAB_SERIES` entry guard: if a blueprint has `CKD` in conditions and no explicit series for `Creatinine`, raise a `LabGenerationError` during `_validate_lab_focus()` rather than falling through to the generic formula.

---

### 2.5 `_format_conditions()` Duplication — ⚠️ DUPLICATE LOGIC (RISK: MEDIUM)

An identical private `_format_conditions()` function with the same `display` dictionary is implemented in **two different generators**:

- `generators/visit_generator.py` lines 827–844
- `generators/medication_generator.py` lines 530–547

Both map the same 10 condition keys to the same human-readable strings. The only structural difference is that the two functions live in different modules.

**Risk:** MEDIUM — If a new condition is added to `constants.CONDITIONS`, a developer must update **both** functions to avoid missing labels. This is a hidden maintenance surface.

**Recommendation:** Extract to a shared utility in `config/constants.py` as `CONDITION_DISPLAY_NAMES: dict[str, str]` (already partially present in `retrieval_enricher._CONDITION_LABELS`), then import from there. Alternatively, move it to a new `generators/_utils.py` shared module.

---

### 2.6 `_conditions_pipe()` Duplication — ⚠️ DUPLICATE LOGIC (RISK: LOW-MEDIUM)

The helper function `_conditions_pipe(patient)` is implemented identically in:

- `ingestion/chunker.py` (line 705)
- `ingestion/metadata_builder.py` (line 475)

Both produce `"|".join(str(c) for c in conds if str(c).strip())`.

**Risk:** LOW-MEDIUM — Currently identical and unlikely to drift. But since both modules are in the same `ingestion/` package, this should be a single shared import from a `_utils.py` file to prevent future silent divergence.

---

### 2.7 Boolean Enrichment Logic Duplication — ⚠️ BOUNDARY CONCERN (RISK: MEDIUM)

The boolean enrichment fields (`has_medication_change`, `has_hospitalization`, `has_lab_trend`) are computed **twice** in the ingestion pipeline:

**In `chunker._make_chunk()` (lines 638–645):**
```python
has_medication_change = any(
    m.get("medication_status") in MEDICATION_CHANGE_STATUSES for m in medications
)
has_hospitalization = (visit_type == "hospitalization" or visit_role == "hospitalization")
has_lab_trend = bool(labs)
```

**In `metadata_builder.build_metadata()` (lines 171–180):**
```python
has_medication_change = bool(any(
    m.get("medication_status") in MEDICATION_CHANGE_STATUSES for m in medications
))
has_hospitalization = bool(visit_type == "hospitalization" or visit_role == "hospitalization")
has_lab_trend = bool(labs)
```

**Finding:** The logic is currently identical. Both reference `MEDICATION_CHANGE_STATUSES` from `constants.py`. However, this creates a risk: the chunker writes booleans into `chunk["metadata"]`, then `metadata_builder.build_metadata()` **ignores** the chunk's pre-computed booleans and **recomputes** them from the `visit` dict. If the chunker and the metadata builder were to diverge in their computation of these fields, the final ChromaDB metadata (built by `metadata_builder`) would silently override the chunker's values.

**Risk:** MEDIUM — Not a current bug. But the contract is implicit. The design intent (chunker writes metadata, metadata_builder overwrites it) is not documented anywhere.

**Recommendation:** Add a module docstring note in `metadata_builder.py` stating explicitly: _"Boolean enrichment fields are always recomputed from the visit dict. The chunk's pre-computed metadata booleans are NOT trusted and NOT read by this module."_ This prevents future confusion about which module owns the final boolean value.

---

### 2.8 `has_lab_trend` Semantic Gap — ⚠️ MISSING GUARD (RISK: MEDIUM)

**`metadata_builder.build_metadata()` line 180:**
```python
has_lab_trend = bool(labs)
```

This sets `has_lab_trend = True` for any visit that has **any** lab record, regardless of whether the lab is a trend-oriented lab type. The `lab_generator.lab_has_trend()` function exists and correctly limits trend-detection to the six trend labs (`HbA1c`, `FBG`, `Creatinine`, `Hemoglobin`, `Ferritin`, `LDL`).

**Finding:** The metadata builder does not call `lab_has_trend()`. For the current 15-patient dataset, all generated lab types are in the trend-lab set, so no false positives occur. However, if a future blueprint adds a non-trend lab type (e.g., a culture result), `has_lab_trend` would be incorrectly set to `True`.

**Recommendation:** Replace `has_lab_trend = bool(labs)` with a call to `lab_generator.lab_has_trend(labs)` or inline the same frozenset check. Import the frozenset constant from `constants.py` (currently not exported; add `TREND_LAB_TYPES` to `constants.py`).

---

## 3 — Single Source of Truth (SSoT) Compliance

| Domain | SSoT Location | Status |
|---|---|---|
| Clinical enums | `config/constants.py` | ✅ Used universally |
| Patient blueprints | `config/patient_blueprints.py` | ✅ Used universally |
| BP forbidden terms | `BP_FORBIDDEN_LAB_TERMS` | ✅ 5-layer enforcement |
| Medication whitelist | `MEDICATION_WHITELIST` | ✅ Hard-gated |
| Schema contracts | `REQUIRED_*_FIELDS` constants | ✅ All generators validate |
| Visit role vocabulary | `soap/soap_semantics.py` | ⚠️ Duplicated in `retrieval_enricher._VISIT_ROLE_PHRASES` — documented, acceptable |
| Condition display names | **No single location** | ⚠️ Duplicated in `visit_generator`, `medication_generator`, `retrieval_enricher` |
| `_conditions_pipe()` | **No single location** | ⚠️ Duplicated in `chunker` + `metadata_builder` |

---

## 4 — Validation Rule Coverage (V1–V13)

| Rule | Description | Enforced In |
|---|---|---|
| V1 | Required top-level fields | `patient_generator` + `validators/rules.py` |
| V2 | Schema version matches contract | `patient_generator._validate_patient_shell()` |
| V3 | Age within AGE_LIMITS | `patient_generator` + `validators/rules.py` |
| V4 | Conditions in CONDITIONS enum | `patient_generator` + `validators/rules.py` |
| V5 | Visit fields complete and typed | `visit_generator._validate_visit_shape()` |
| V6 | Vital limits within VITAL_LIMITS | `visit_generator._validate_vital_limits()` |
| V7 | Medication whitelist compliance | `medication_generator._validate_medication_record()` |
| V8 | Lab focus matches conditions | `lab_generator._validate_lab_focus()` |
| V9 | Allergy contradiction safety | `allergy_generator.find_allergen_medication_contradiction()` |
| V10 | BP never in labs/metadata/meds | 5-layer enforcement (see §2.1) |
| V11 | Chunk ID format | `chunker.validate_chunk()` |
| V12 | Retrieval anchor present | `chunker.validate_chunk()` (Check 5) |
| V13 | Embedding similarity audit | `scripts/run_step11_v13.py` (report-only) |

**Finding:** V1–V12 are enforced with hard errors at generation time. V13 is a post-hoc reporting audit only.

---

## 5 — Dependency Graph (Import Safety)

```
config/constants.py        ← imported by ALL modules (no circular risk)
config/patient_blueprints.py ← imported by generators + chunker (no circular risk)
generators/*               ← import config only (no cross-generator imports)
soap/*                     ← imports config only + soap sub-modules
validators/rules.py        ← imports config only (no generator imports — CORRECT)
ingestion/retrieval_enricher.py ← imports config + patient_blueprints
ingestion/chunker.py       ← imports config + patient_blueprints + retrieval_enricher
ingestion/metadata_builder.py  ← imports config ONLY (no chunker dependency — CORRECT)
```

**Finding:** No circular dependencies detected. The metadata_builder correctly **does not** import the chunker, preserving clean layer separation. The SOAP layer does not import any generator — correct.

---

## 6 — SOAP Layer Boundary Check

**`soap_generator.render_soap_note_from_templates()`** applies three post-processing steps (lines 323–364):

1. Style-aware opener injection (from `soap_semantics.SOAP_STYLE_OPENERS`)
2. Visit-role vocabulary injection (from `soap_semantics.VISIT_ROLE_VOCABULARY`)
3. `clinical_event.event_summary` injection into Assessment

**Finding:** These are all fact-sourced operations that only reformat/reorganize documented facts — no medical fact generation. The boundary is respected.

**Observation:** The `VISIT_ROLE_VOCABULARY` dictionary from `soap_semantics.py` is intentionally replicated in `retrieval_enricher._VISIT_ROLE_PHRASES` to avoid a runtime dependency of the ingestion layer on the SOAP layer. This is a deliberate, documented architectural decision — **not a bug**.

---

## 7 — `test_step14.py` Integration Test Coverage

The test harness covers:

| Check | Coverage |
|---|---|
| Full 15-patient pipeline end-to-end | ✅ All patients |
| Metadata record count == chunk count | ✅ |
| All 12 metadata fields present and typed | ✅ |
| BP key rejection | ✅ Negative test |
| None value rejection | ✅ Negative test |
| List value rejection | ✅ Negative test |
| Boolean-as-string rejection | ✅ Negative test |
| `has_medication_change` correctness (PAT-CHR-001 v4) | ✅ |
| `has_hospitalization` correctness (PAT-CHR-005) | ✅ |
| `has_lab_trend` correctness (PAT-CHR-002) | ✅ |
| Allergy chunks use `""` not `None` | ✅ All 15 |
| Pipe-separated conditions | ✅ Including multi-condition check |

**Missing test:** No negative test for `has_lab_trend` false positive (a visit with labs that are not trend-oriented lab types). This relates to the gap in §2.8.

---

## 8 — Risk-Ranked Findings

| # | Finding | Risk | Action Required |
|---|---|---|---|
| R1 | `has_lab_trend` computed as `bool(labs)` not `lab_has_trend(labs)` | MEDIUM | Add `TREND_LAB_TYPES` to constants; fix metadata_builder |
| R2 | `_format_conditions()` duplicated in visit_generator + medication_generator | MEDIUM | Extract to `config/constants.py` or `generators/_utils.py` |
| R3 | Boolean enrichment recomputed silently in metadata_builder (overwrites chunker values) | MEDIUM | Document the contract explicitly |
| R4 | Generic CKD Creatinine fallback is dead code for the 15-patient dataset | MEDIUM | Guard with `LabGenerationError` if new CKD blueprint has no explicit series |
| R5 | `_conditions_pipe()` duplicated in chunker + metadata_builder | LOW-MEDIUM | Move to `ingestion/_utils.py` shared import |
| R6 | `_VISIT_ROLE_PHRASES` in retrieval_enricher is a manual mirror of soap_semantics | LOW | Acceptable by design; add a comment saying "keep in sync with soap_semantics.py" |

---

## 9 — Recommended Actions Before Step 15

### Must-Do (Blocking)
- None — the pipeline is **functionally correct** for the current 15-patient dataset.

### Should-Do (Pre-ingestion)
1. **Document the boolean override contract** in `metadata_builder.py` (fix for R3).
2. **Run `scripts/test_step14.py`** and confirm all 13 assertions pass with the current patient dataset.
3. **Run `scripts/test_step15.py`** to confirm ChromaDB ingestion contract compliance.

### Nice-to-Have (Post-delivery refactors)
4. Extract `_format_conditions()` to `config/constants.py` as `CONDITION_DISPLAY_NAMES` (fix R2).
5. Extract `_conditions_pipe()` to `ingestion/_utils.py` (fix R5).
6. Replace `has_lab_trend = bool(labs)` with a proper `lab_has_trend()` check (fix R1).

---

## 10 — Final Verdict

> **Architecture status: STABLE — APPROVED FOR STEP 15 INGESTION**

The data generation pipeline is architecturally sound. SSoT is enforced, circular dependencies are absent, and BP safety is properly guarded at five independent checkpoints. The identified issues are maintenance risks for future extension — none of them affect current pipeline correctness for the 15-patient v1.7 Lite dataset.

The most actionable pre-delivery item is ensuring `test_step14.py` and `test_step15.py` both pass cleanly on the generated dataset before ChromaDB ingestion is finalized.
