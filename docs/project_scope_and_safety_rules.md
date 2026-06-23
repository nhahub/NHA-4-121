# Project Scope and Safety Rules

**Document Path:** `docs/project_scope_and_safety_rules.md`  
**Project:** AI-Based Clinical Record Summarization System  
**Document Type:** Official Scope and Safety Contract  
**Audience:** Full engineering team, DEPI evaluators, GitHub reviewers, and LLM tools used by team members  
**Status:** Final handoff reference

---

# 1. Purpose of This Document

This document defines the official scope and safety boundaries for the **AI-Based Clinical Record Summarization System**.

It exists to prevent scope creep, unsafe medical claims, unsupported AI behavior, and unnecessary engineering complexity.

Every team member must follow this document when working on:

- synthetic patient data,
- validation rules,
- SOAP generation,
- retrieval enrichment,
- chunking and metadata,
- RAG retrieval,
- answer generation,
- backend APIs,
- frontend display,
- demo scripts,
- documentation,
- and any LLM-assisted development workflow.

This file is also intended to be pasted into external LLM tools such as ChatGPT, Claude, Gemini, or Copilot before asking them to help with the project.

---

# 2. Project Identity

## 2.1 Project Name

```text
AI-Based Clinical Record Summarization System
```

## 2.2 Project Type

```text
Academic Retrieval-Augmented Generation (RAG) AI engineering project
```

## 2.3 Project Context

This system is built for the **Digital Egypt Pioneers Initiative (DEPI)** graduation project.

It is an academic demo system that retrieves, summarizes, and cites **synthetic clinical records**.

It is not a hospital product, not a clinical decision-support system, and not a replacement for medical professionals.

---

# 3. Core Project Goal

The system answers questions about synthetic patient records using Retrieval-Augmented Generation.

Its goal is to:

```text
Retrieve documented synthetic clinical information,
summarize it safely,
and show source citations for every generated answer.
```

The project demonstrates:

- structured synthetic data generation,
- validation-first data engineering,
- deterministic SOAP note generation,
- retrieval enrichment,
- ChromaDB ingestion,
- patient-scoped retrieval,
- grounded LLM answer generation,
- citation formatting,
- FastAPI backend integration,
- Streamlit frontend demo,
- and safe AI engineering practices.

---

# 4. What the System Is Allowed to Do

The system may:

- retrieve documented patient facts from synthetic records,
- summarize retrieved records,
- answer questions using retrieved evidence only,
- generate citations pointing to retrieved chunks,
- display patient timelines from existing visit data,
- display documented allergy history,
- display documented medications,
- display documented labs,
- display documented vitals inside narrative text,
- generate deterministic SOAP notes from structured JSON,
- enrich retrieval text deterministically for better semantic matching,
- reject unsafe or unsupported outputs,
- refuse to answer when records do not contain enough evidence.

Allowed phrasing:

```text
The system retrieves documented records.
The system summarizes documented patient history.
The answer is based on retrieved synthetic records.
The available record shows...
The retrieved visit note documents...
The retrieved lab result includes...
The retrieved prescription record lists...
No documented evidence was found in the available records.
```

---

# 5. What the System Must Not Do

The system must never:

- diagnose a patient,
- recommend treatment,
- prescribe medication,
- change medication,
- suggest clinical management,
- predict diseases,
- infer undocumented conditions,
- infer undocumented allergies,
- infer undocumented improvement or deterioration,
- make unsupported medical conclusions,
- replace clinician judgment,
- use real patient data,
- connect to real hospital infrastructure,
- store real medical records,
- provide emergency medical advice,
- present itself as clinically validated.

Forbidden phrasing:

```text
The patient has uncontrolled diabetes.
The patient should start medication.
The patient needs treatment.
The system detects allergies.
The system predicts CKD.
The system diagnoses hypertension.
The system recommends therapy.
The system confirms disease progression.
This is clinically safe for real use.
```

Correct replacement phrasing:

```text
The available synthetic record documents T2DM.
The retrieved prescription record lists Metformin.
The retrieved allergy registry documents a recorded allergy.
The available records do not contain enough evidence to answer that.
This academic system retrieves and summarizes documented synthetic records only.
```

---

# 6. Medical Safety Boundary

This project must be described as:

```text
A safe academic RAG demo that retrieves and summarizes synthetic records.
```

It must not be described as:

```text
A diagnostic AI system.
A medical decision-support system.
A treatment recommendation engine.
A disease prediction model.
A real hospital-ready system.
```

All medical-sounding outputs must be grounded in retrieved evidence.

If retrieved evidence is insufficient, the system must say so instead of guessing.

---

# 7. Synthetic Data Rule

All patient records in this project are synthetic.

The dataset must not contain:

- real patient names,
- real medical record numbers,
- real addresses,
- real phone numbers,
- real national IDs,
- real hospital identifiers,
- real lab reports,
- real prescriptions,
- any protected health information.

Synthetic data may contain realistic-looking values for academic demonstration, but those values must not belong to real people.

---

# 8. Validation as a Hard Gate

Validation is mandatory before SOAP generation and ingestion.

The project uses V1–V13 validation rules.

Validation must run before:

- SOAP generation,
- retrieval enrichment,
- chunking,
- ChromaDB ingestion,
- RAG testing,
- backend demo,
- frontend demo.

No patient file with `FAIL` validation issues may be ingested into ChromaDB.

Recommended command:

```bash
python scripts/validate_all.py --mode full
```

The expected result before ingestion is:

```text
FAIL violations = 0
Dataset-level checks = PASS
```

Warnings should be reviewed before demo day.

---

# 9. Validation Rule Summary

The official validation rule set is V1–V13.

| Rule | Purpose | Severity |
|---|---|---|
| V1 | Chronological visit order | FAIL |
| V2 | Allergy contradiction check | FAIL |
| V3 | Impossible vitals and age bounds | FAIL |
| V4 | Required fields and forbidden demographic `age` | WARN/FAIL |
| V5 | Prior visit reference integrity | WARN |
| V6 | Duplicate visit IDs | FAIL |
| V7 | Invalid enums and CKD co-occurrence rule | FAIL |
| V8 | Date format validation | FAIL |
| V9 | BP forbidden in labs | FAIL |
| V10 | `timeline_events` forbidden in patient JSON | FAIL |
| V11 | Medication whitelist, frequency, and route validation | FAIL |
| V12 | Dataset diversity fingerprint and retrieval signature validation | FAIL/WARN |
| V13 | Embedding similarity report helper | REPORT |

Dataset-level checks also verify:

- expected patient count,
- expected tier distribution,
- unique `patient_id` values across files,
- CKD patient count not exceeding the locked scope.

These dataset-level checks do not replace V1–V13. They complement them.

---

# 10. Blood Pressure Rule

Blood pressure is a vital sign, not a lab value.

Authoritative location:

```json
"vitals": {
  "bp_systolic": 120,
  "bp_diastolic": 80
}
```

BP must never appear in:

```text
visit.labs[]
lab_type enum
ChromaDB metadata
standalone duplicate patient fields
timeline_events
```

RAG implication:

```text
BP values may appear in doctor_note chunk text through the SOAP Objective section.
BP values must not be stored as ChromaDB metadata fields.
Queries about BP should retrieve doctor_note chunks, not lab_result metadata.
```

---

# 11. CKD Rule

CKD is not a standalone condition in this project.

CKD is allowed only as a complication in limited chronic-tier patients.

Official CKD rule:

```text
If CKD appears in patient["conditions"], then:
- T2DM must also be present.
- HTN must also be present.
- patient.metadata.tier must be chronic.
- CKD patient count must not exceed the locked dataset scope.
```

Forbidden CKD usage:

```text
CKD alone
CKD in normal tier
CKD in moderate tier
CKD without T2DM
CKD without HTN
CKD as a general prediction or inferred disease
```

Allowed phrasing:

```text
The synthetic record documents CKD in a chronic-tier patient who also has T2DM and HTN.
```

Forbidden phrasing:

```text
The system predicts CKD.
The patient likely has CKD.
The model detects kidney disease.
```

---

# 12. Medication Safety Rule

Medication records must come from the locked whitelist in `config/constants.py`.

The system must not invent medications.

The system must not recommend medications.

Medication generation is deterministic and condition-driven.

Medication `start_date` should represent the first documented start date of that medication, not necessarily the current visit date.

Medication `stop_date` should be `null` unless a medication is documented as stopped.

The RAG system may summarize documented medications, but it must not advise medication changes.

Allowed phrasing:

```text
The retrieved prescription record lists Metformin 500 mg twice daily via oral route.
The available record documents Amlodipine as an added medication from a later visit.
```

Forbidden phrasing:

```text
The patient should take Metformin.
The dose should be increased.
Amlodipine is recommended.
Treatment should continue.
```

---

# 13. Allergy Safety Rule

The system retrieves documented allergy history only.

It does not detect allergies.

It does not infer allergies.

It does not predict allergy risk.

Allergy information comes from:

```text
patient["allergy_registry"]
retrieved allergy chunks
retrieved visit notes that document allergy context
```

Allowed phrasing:

```text
The retrieved allergy registry documents an allergy to Penicillin.
The available records do not document any allergy.
```

Forbidden phrasing:

```text
The system detected an allergy.
The patient may be allergic.
The model predicts allergy risk.
This medication is unsafe for the patient.
```

If an allergen appears near medication/prescription context in generated text, it must be audited and treated as a safety risk.

---

# 14. Lab Safety Rule

Labs must use locked lab types only.

Official lab types:

```text
HbA1c
FBG
Creatinine
Hemoglobin
Ferritin
LDL
```

BP is not a lab type.

Creatinine generation scope:

```text
Creatinine is generated for CKD patients or patients with combined T2DM + HTN context.
T2DM-only or HTN-only patients are not required to have Creatinine labs.
```

The system may summarize documented lab values.

It must not infer clinical improvement, deterioration, control status, diagnosis, or treatment success unless such wording is explicitly documented in retrieved records.

Allowed phrasing:

```text
The retrieved lab result lists HbA1c 7.8%.
The retrieved visit includes Creatinine as a documented lab entry.
```

Forbidden phrasing:

```text
The patient is improving.
The disease is uncontrolled.
The medication worked.
Kidney function is worsening.
```

---

# 15. SOAP Generation Rule

SOAP notes in the current implementation are generated deterministically from structured JSON using approved templates.

SOAP generation must be:

- deterministic,
- template-based,
- grounded in structured patient JSON,
- free from LLM calls,
- free from randomization,
- free from unsupported clinical interpretation.

SOAP generation must not:

- modify structured data,
- invent medications,
- invent diagnoses,
- invent lab values,
- invent vital signs,
- add unsupported treatment recommendations,
- add unsupported disease status interpretations.

SOAP text is used as narrative evidence for doctor note chunks, but structured JSON remains the source of truth.

---

# 16. Retrieval Enrichment Rule

Retrieval enrichment is deterministic support text created to improve semantic retrieval quality.

Relevant files:

```text
ingestion/retrieval_enricher.py
ingestion/retrieval_enrichment_auditor.py
```

Retrieval enrichment text is not an independent medical source.

It must be derived only from:

- structured patient JSON,
- visit facts,
- SOAP note text,
- documented labs,
- documented medications,
- documented allergy registry.

It must not:

- invent clinical facts,
- add diagnosis claims,
- add treatment recommendations,
- add undocumented status interpretations,
- store BP in metadata,
- bypass validation.

Retrieval enrichment must be audited before being used in chunking or ingestion.

---

# 17. Chunking and Metadata Safety Rules

Chunking converts validated patient records into ChromaDB-ready evidence units.

Allowed source types:

```text
doctor_note
lab_result
prescription
allergy
discharge_summary
medication_reconciliation
```

Expected chunk behavior:

- doctor note chunks contain SOAP narrative text,
- lab result chunks contain documented lab records,
- prescription chunks contain documented medication records,
- allergy chunks contain allergy registry information,
- discharge summary chunks contain hospitalization narratives and discharge timelines,
- medication reconciliation chunks contain post-hospitalization medication reviews and continuity checks.

Metadata may include:

```text
patient_id
visit_id
visit_date
source_type
visit_type
conditions
chunk_id
document_id
```

Metadata must not include:

```text
bp_systolic
bp_diastolic
blood_pressure
raw clinical free text
unsupported diagnosis labels
LLM-generated medical conclusions
```

The chunker must not run before validation passes.

---

# 18. RAG Answer Generation Rule

The LLM is used only in the RAG answer generation layer.

The LLM may:

- summarize retrieved chunks,
- answer questions using retrieved evidence,
- cite sources,
- state that evidence is missing.

The LLM must not:

- answer without retrieved evidence,
- use outside medical knowledge to complete missing facts,
- diagnose,
- prescribe,
- recommend treatment,
- predict conditions,
- infer undocumented claims,
- override structured data,
- ignore citations.

Core grounding rule:

```text
No retrieved evidence = no generated medical answer.
```

If retrieved chunks do not support the user query, the answer should be:

```text
The available synthetic records do not contain enough documented evidence to answer this question.
```

---

# 19. Citation Rule

Every generated answer must include citations.

Citations should identify the source of evidence using available metadata such as:

```text
patient_id
visit_id
visit_date
source_type
chunk_id
document_id
```

Answers without citations should be treated as incomplete or unsafe.

The frontend must show citations clearly enough for evaluators to understand where the answer came from.

---

# 20. Backend Safety Rule

The backend should orchestrate the system.

It should not contain:

- validation rules,
- data generation logic,
- chunking logic,
- ChromaDB ingestion logic,
- frontend display logic

The backend should call the appropriate service modules and return structured responses.

Required backend endpoints:

```text
POST /query
GET /timeline/{patient_id}
GET /summary/{patient_id}
GET /health
```

All answer endpoints must preserve grounding and citations.

---

# 21. Frontend Safety Rule

The frontend is a display layer.

It should not:

- call ChromaDB directly,
- call Groq directly,
- run validators,
- generate data,
- modify patient JSON,
- bypass backend APIs.

The frontend should:

- send requests to backend endpoints,
- display grounded answers,
- display citations,
- display patient timeline,
- display documented allergy history,
- avoid clinical claims in UI labels.

Preferred UI phrasing:

```text
Documented Allergy History
Retrieved Evidence
Source Citations
Available Record Summary
Synthetic Patient Timeline
```

Avoid UI phrasing:

```text
Diagnosis
Clinical Decision
Treatment Recommendation
Disease Prediction
Allergy Detection
```

---

# 22. Engineering Scope Boundaries

The project must remain simple, local-first, and academic.

Allowed architecture:

```text
FastAPI
Streamlit
ChromaDB local persistent storage
Local JSON patient records
Groq API for grounded RAG answer generation
Docker Compose for local reproducibility
```

Forbidden additions before the demo:

```text
Kubernetes
Microservices
PostgreSQL primary database
Redis
Celery
LangGraph
Agent orchestration
FHIR/HL7 integration
Real hospital systems
Clinical NLP pipelines
Medical ontologies
Advanced dashboards
Disease prediction
Treatment recommendation
Diagnosis support
```

Do not add enterprise complexity unless the team explicitly changes the project scope.

---

# 23. Team Ownership Safety Rules

## Ahmed Hesham Kamel

Owns:

- data engineering,
- synthetic patient JSON,
- patient schema,
- validation rules,
- constants,
- deterministic SOAP generation,
- SOAP safety,
- documentation,
- showcase patient configuration,
- data quality before ingestion.

Ahmed controls schema changes.

## Gamal Mohamed Gad

Owns:

- ingestion,
- chunking,
- metadata construction,
- embeddings,
- ChromaDB ingestion,
- retrieval,
- grounding,
- citations,
- RAG answer generation.

Gamal must not ingest invalid patient records.

## Youssef Yassin Ibrahim

Owns:

* FastAPI backend,
* backend orchestration,
* API routes,
* API schemas,
* API testing,
* Streamlit frontend,
* frontend API client,
* demo UI behavior,
* frontend-backend integration.

Backend must call RAG modules instead of duplicating RAG logic.

Frontend must not bypass backend APIs.

## Mahmoud Mohamed El Faham

Owns:

* deployment,
* Docker,
* scripts coordination,
* tests,
* logs,
* demo smoke checks,
* reproducible local execution.

Deployment must remain simple and local-first.

---

# 24. LLM Tool Usage Rules for the Team

When any team member uses an external LLM tool, they should provide this file as context.

The LLM must be instructed to follow these rules:

```text
Do not redesign the architecture.
Do not add enterprise infrastructure.
Do not suggest real clinical use.
Do not add diagnosis or treatment recommendation features.
Do not change schema rules casually.
Do not change validation rules without warning.
Do not move BP outside visit.vitals.
Do not store BP in labs or metadata.
Do not treat enrichment text as source truth.
Do not make SOAP LLM-based unless the team explicitly changes the implementation.
Do not modify files outside the requested ownership scope.
```

Recommended LLM prompt prefix:

```text
You are helping with an academic RAG project using synthetic clinical records only.
Follow the project_scope_and_safety_rules.md file strictly.
Do not suggest diagnosis, treatment recommendation, prediction, real hospital integration, or enterprise infrastructure.
Work only on the files I provide.
```

---

# 25. Demo Safety Script

During the demo, the team should describe the system using safe language.

Recommended demo wording:

```text
This is an academic RAG system for synthetic clinical records.
It retrieves documented records, summarizes them, and shows citations.
It does not diagnose or recommend treatment.
All outputs are grounded in retrieved evidence.
If the evidence is missing, the system should not invent an answer.
```

Avoid saying:

```text
The system detects diseases.
The system recommends medications.
The system predicts patient risk.
The system is clinically ready.
The system replaces doctors.
```

---

# 26. Final Safety Checklist

Before demo or final handoff, verify:

```text
[ ] All patient records are synthetic.
[ ] Validation V1–V13 passes with zero FAIL issues.
[ ] Dataset-level checks pass.
[ ] BP exists only in visit.vitals.
[ ] BP is not in labs.
[ ] BP is not in metadata.
[ ] CKD appears only with T2DM + HTN + chronic tier.
[ ] Medications come only from the whitelist.
[ ] SOAP generation is deterministic and audited.
[ ] Retrieval enrichment is audited.
[ ] Chunks use allowed source_type values only.
[ ] Invalid records are not ingested.
[ ] RAG answers include citations.
[ ] No retrieved evidence results in no generated medical answer.
[ ] Frontend avoids unsafe clinical terminology.
[ ] Demo uses showcase patients only.
```

---

# 27. Final Scope Statement

The **AI-Based Clinical Record Summarization System** is a safe academic engineering demo that retrieves, summarizes, and cites synthetic clinical records using RAG.

Its core promise is:

```text
Documented evidence in.
Grounded answer out.
No evidence, no medical claim.
```

The project succeeds when it demonstrates reliable retrieval, clear citations, validation-first data quality, and safe AI behavior without unnecessary complexity or unsupported clinical claims.
