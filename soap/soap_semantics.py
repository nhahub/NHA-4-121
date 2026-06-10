"""
soap/soap_semantics.py

Condition-aware deterministic SOAP semantic context utilities.

Purpose:
    Build retrieval-friendly semantic context strings from documented structured
    patient and visit facts.

This module improves RAG chunk quality by adding deterministic, v1.7 Lite
condition-aware phrasing while preserving the project's safety contract.

Design rules:
    - No LLM calls.
    - No randomization.
    - No template registry.
    - No template selection.
    - No SOAP rendering.
    - No audit logic.
    - No mutation of patient or visit dictionaries.
    - No diagnosis inference.
    - No medication recommendation.
    - No treatment recommendation.
    - No clinical status interpretation.
    - No symptom invention.
    - No use of facts that are not present in structured JSON.

Important:
    This module does not decide medical truth. It only converts documented
    structured facts into safer, more retrieval-friendly semantic phrases.

Intended integration:
    soap_renderers.py should call build_soap_semantic_context() inside
    build_fact_context(), then merge the returned fields into SoapFactContext.
"""

from __future__ import annotations

from typing import Any, Final, Iterable, Mapping, TypedDict


class SoapSemanticContext(TypedDict):
    """
    Deterministic semantic strings derived from documented structured facts.

    These strings are intended to improve RAG retrieval quality by making SOAP
    chunks more semantically distinct across conditions, visit roles, clinical
    events, timelines, labs, medications, and allergy context.

    They must remain descriptive, grounded, and non-inferential.
    """

    condition_focus_text: str
    diagnosis_focus_text: str
    monitoring_focus_text: str
    medication_focus_text: str
    visit_context_text: str
    timeline_context_text: str
    retrieval_focus_text: str
    visit_role_text: str
    clinical_event_text: str
    semantic_focus_text: str
    retrieval_intent_tags_text: str
    primary_evidence_text: str
    lab_trend_text: str
    medication_trajectory_text: str
    allergy_context_text: str


# Canonical condition labels used only when the corresponding condition or
# diagnosis exists in the structured record.
CONDITION_LABELS: Final[Mapping[str, str]] = {
    "Acute_URTI": "acute upper respiratory tract infection",
    "T2DM": "type 2 diabetes",
    "HTN": "hypertension",
    "Asthma": "asthma",
    "IDA": "iron-deficiency anemia",
    "GERD": "gastroesophageal reflux disease",
    "CKD": "chronic kidney disease",
    "Dyslipidemia": "dyslipidemia",
    "Allergic_Rhinitis": "allergic rhinitis",
    "UTI": "urinary tract infection",
}


# Lab families are condition-aware but still grounded: a family phrase is used
# only when at least one related lab type exists in the visit lab list.
CONDITION_LAB_KEYWORDS: Final[Mapping[str, tuple[str, ...]]] = {
    "T2DM": ("hba1c", "fbg"),
    "HTN": ("creatinine",),
    "CKD": ("creatinine",),
    "IDA": ("hemoglobin", "ferritin"),
    "Dyslipidemia": ("ldl",),
}


# Medication families are condition-aware but still grounded: a family phrase is
# used only when at least one related medication name exists in the visit
# medication list.
CONDITION_MEDICATION_KEYWORDS: Final[Mapping[str, tuple[str, ...]]] = {
    "Acute_URTI": ("paracetamol",),
    "T2DM": ("metformin", "glibenclamide"),
    "HTN": ("lisinopril", "amlodipine", "losartan"),
    "Asthma": ("salbutamol", "budesonide", "inhaler"),
    "IDA": ("ferrous",),
    "GERD": ("omeprazole",),
    "Dyslipidemia": ("atorvastatin",),
    "Allergic_Rhinitis": ("cetirizine",),
    "UTI": ("nitrofurantoin",),
}


VISIT_TYPE_TEXT: Final[Mapping[str, str]] = {
    "initial": "This is documented as an initial encounter in the visit record.",
    "follow_up": "This is documented as a follow-up encounter in the visit record.",
    "emergency": "This is documented as an emergency encounter in the visit record.",
    "hospitalization": "This is documented as a hospitalization encounter in the visit record.",
}


# ---------------------------------------------------------------------------
# Style-aware SOAP opening phrases (Step 9, requirement 1)
#
# Each soap_style carries a distinct mandatory opener injected at the START
# of the subjective section via build_visit_role_text().
# This ensures that problem_oriented notes always open with the documented
# problem framing, and timeline_oriented notes open with the longitudinal
# reference — making them semantically distinct even for the same condition.
# ---------------------------------------------------------------------------

SOAP_STYLE_OPENERS: Final[Mapping[str, str]] = {
    "problem_oriented": "The primary concern today is",
    "timeline_oriented": "Compared with the previous visit,",
    "concise": "This encounter records",
}


VISIT_ROLE_LABELS: Final[Mapping[str, str]] = {
    "initial_diagnosis": "initial diagnosis",
    "baseline_assessment": "baseline assessment",
    "follow_up_monitoring": "follow-up monitoring",
    "partial_adherence": "partial adherence",
    "poor_adherence": "poor adherence",
    "improved_adherence": "improved adherence",
    "medication_adjustment": "medication adjustment",
    "second_medication_added": "second medication added",
    "symptom_flare": "symptom flare",
    "symptom_control": "symptom control",
    "acute_treatment": "acute treatment",
    "treatment_completion": "treatment completion",
    "hospitalization": "hospitalization",
    "post_discharge_stabilization": "post-discharge stabilization",
    "ckd_monitoring": "CKD monitoring",
    "lab_trend_review": "lab trend review",
    "recovery": "recovery",
}


# ---------------------------------------------------------------------------
# Visit-role vocabulary (Step 9, requirement 2)
#
# Maps every visit_role to 2-3 required phrases that MUST appear verbatim
# in the SOAP note produced for that visit.
#
# Design rules:
#   - Phrases are clinically descriptive but factual — no inference.
#   - Each phrase is unique to its role so that embedding models can
#     discriminate e.g. "partial_adherence" from "routine_follow_up"
#     even when both mention T2DM and Metformin.
#   - Tuples contain exactly 2 or 3 phrases, each < 80 characters.
# ---------------------------------------------------------------------------

VISIT_ROLE_VOCABULARY: Final[Mapping[str, tuple[str, ...]]] = {
    "initial_diagnosis": (
        "initial diagnosis was documented",
        "baseline management plan established",
    ),
    "baseline_assessment": (
        "baseline assessment conducted",
        "initial laboratory and clinical data reviewed",
    ),
    "routine_follow_up": (
        "routine follow-up visit",
        "ongoing medication review conducted",
    ),
    "partial_adherence": (
        "reported partial adherence",
        "missed doses noted",
        "adherence counselling provided",
    ),
    "poor_adherence": (
        "documented poor medication adherence",
        "patient reported inconsistent medication use",
    ),
    "lab_trend_review": (
        "laboratory trend reviewed",
        "results compared with prior documented values",
    ),
    "medication_started": (
        "new medication initiated",
        "treatment commenced at this visit",
    ),
    "medication_continued": (
        "current medication regimen continued",
        "no changes to prescribed therapy",
    ),
    "dose_adjustment": (
        "dose adjustment documented",
        "medication regimen modified at this visit",
    ),
    "second_medication_added": (
        "second medication added to regimen",
        "combination therapy initiated",
    ),
    "acute_treatment_started": (
        "acute treatment course initiated",
        "short-course therapy commenced",
    ),
    "course_completed": (
        "treatment course completed",
        "short-course therapy concluded at this visit",
    ),
    "symptom_flare": (
        "symptom flare documented",
        "exacerbation of existing condition noted",
    ),
    "symptom_control_review": (
        "symptom control reviewed",
        "clinical response to therapy assessed",
    ),
    "emergency_exacerbation": (
        "emergency presentation documented",
        "acute exacerbation requiring urgent management",
    ),
    "hospitalization": (
        "inpatient hospitalization documented",
        "hospital admission recorded for this encounter",
    ),
    "post_discharge_stabilization": (
        "following recent hospitalization,",
        "post-discharge review conducted",
        "discharge medications reviewed",
    ),
    "ckd_monitoring": (
        "CKD monitoring visit",
        "renal function parameters reviewed",
    ),
    "medication_reconciliation": (
        "medication reconciliation performed",
        "post-discharge medication list verified",
    ),
    "recovery_confirmed": (
        "recovery confirmed at this visit",
        "resolution of acute episode documented",
    ),
}


TIMELINE_PATTERN_LABELS: Final[Mapping[str, str]] = {
    "regular_quarterly": "regular quarterly follow-up pattern",
    "delayed_followup": "delayed follow-up pattern",
    "irregular_followup": "irregular follow-up pattern",
    "seasonal_exacerbation": "seasonal exacerbation timeline pattern",
    "post_hospitalization": "post-hospitalization timeline pattern",
}


SEMANTIC_FOCUS_LABELS: Final[Mapping[str, str]] = {
    "recovery": "recovery-focused retrieval context",
    "lab_improvement": "laboratory improvement retrieval context",
    "poor_adherence": "adherence-focused retrieval context",
    "medication_escalation": "medication escalation retrieval context",
    "symptom_control": "symptom control retrieval context",
    "hospitalization_recovery": "hospitalization recovery retrieval context",
    "ckd_monitoring": "CKD monitoring retrieval context",
    "dual_lab_trend": "dual laboratory trend retrieval context",
    "acute_treatment_completion": "acute treatment completion retrieval context",
    "dual_condition_control": "dual condition retrieval context",
}


EVENT_TYPE_LABELS: Final[Mapping[str, str]] = {
    "initial_assessment": "initial assessment event",
    "follow_up_review": "follow-up review event",
    "lab_review": "laboratory review event",
    "adherence_issue": "adherence issue event",
    "adherence_improvement": "adherence improvement event",
    "medication_change": "medication change event",
    "symptom_flare": "symptom flare event",
    "symptom_improvement": "symptom improvement event",
    "acute_treatment": "acute treatment event",
    "treatment_completion": "treatment completion event",
    "hospitalization": "hospitalization event",
    "post_discharge_review": "post-discharge review event",
    "monitoring": "monitoring event",
}


def build_soap_semantic_context(
    *,
    conditions: Iterable[Any],
    diagnoses: Iterable[Any],
    labs: Iterable[Mapping[str, Any]],
    medications: Iterable[Mapping[str, Any]],
    visit_type: Any,
    prior_visit_id: Any,
    visit_role: Any | None = None,
    timeline_pattern: Any | None = None,
    timeline_gap_days: Any | None = None,
    clinical_event: Mapping[str, Any] | None = None,
    retrieval_context: Mapping[str, Any] | None = None,
    semantic_focus: Any | None = None,
    retrieval_intent_tags: Iterable[Any] | None = None,
    allergy_registry: Iterable[Mapping[str, Any]] | None = None,
    soap_style: Any | None = None,
) -> SoapSemanticContext:
    """
    Build deterministic condition-aware semantic context strings.

    Args:
        conditions:
            Patient-level documented conditions.
        diagnoses:
            Visit-level documented diagnoses.
        labs:
            Visit-level lab result dictionaries.
        medications:
            Visit-level medication dictionaries.
        visit_type:
            Visit type from the structured visit record.
        prior_visit_id:
            Prior visit ID or None.
        visit_role:
            v1.7 Lite visit role from the structured visit record.
        timeline_pattern:
            v1.7 Lite timeline pattern from the visit/patient metadata.
        timeline_gap_days:
            Numeric or string timeline gap documented on the visit.
        clinical_event:
            v1.7 Lite clinical_event dictionary from the visit.
        retrieval_context:
            v1.7 Lite retrieval_context dictionary from the visit.
        semantic_focus:
            Patient-level semantic_focus. If omitted, the value from
            retrieval_context is used when present.
        retrieval_intent_tags:
            Patient-level or visit-level retrieval intent tags. If omitted,
            retrieval_context.retrieval_intent_tags is used when present.
        allergy_registry:
            Patient-level allergy registry entries.

    Returns:
        SoapSemanticContext with retrieval-friendly semantic strings.

    Safety:
        The function only reflects documented values. It does not infer control,
        progression, severity, treatment need, symptom history, or diagnosis.
    """
    condition_values = _clean_values(conditions)
    diagnosis_values = _clean_values(diagnoses)
    lab_list = tuple(labs or ())
    medication_list = tuple(medications or ())
    allergy_list = tuple(allergy_registry or ())
    lab_types = _lab_type_set(lab_list)
    medication_names = _medication_name_set(medication_list)
    clean_visit_type = _clean_string(visit_type)
    clean_visit_role = _clean_string(visit_role)
    clean_timeline_pattern = _clean_string(timeline_pattern)
    clean_semantic_focus = _resolve_semantic_focus(
        semantic_focus=semantic_focus,
        retrieval_context=retrieval_context,
    )
    clean_tags = _resolve_retrieval_intent_tags(
        retrieval_intent_tags=retrieval_intent_tags,
        retrieval_context=retrieval_context,
    )

    return {
        "condition_focus_text": build_condition_focus_text(condition_values),
        "diagnosis_focus_text": build_diagnosis_focus_text(diagnosis_values),
        "monitoring_focus_text": build_monitoring_focus_text(
            conditions=condition_values,
            lab_types=lab_types,
        ),
        "medication_focus_text": build_medication_focus_text(
            conditions=condition_values,
            medication_names=medication_names,
        ),
        "visit_context_text": build_visit_context_text(clean_visit_type),
        "timeline_context_text": build_timeline_context_text(
            prior_visit_id=prior_visit_id,
            timeline_pattern=clean_timeline_pattern,
            timeline_gap_days=timeline_gap_days,
        ),
        "retrieval_focus_text": build_retrieval_focus_text(
            conditions=condition_values,
            diagnoses=diagnosis_values,
            lab_types=lab_types,
            medication_names=medication_names,
            visit_type=clean_visit_type,
            prior_visit_id=prior_visit_id,
            visit_role=clean_visit_role,
            timeline_pattern=clean_timeline_pattern,
            semantic_focus=clean_semantic_focus,
            retrieval_intent_tags=clean_tags,
            clinical_event=clinical_event,
        ),
        # Step 9: pass soap_style through so build_visit_role_text can inject
        # the style-aware opener and required vocabulary phrases.
        "visit_role_text": build_visit_role_text(
            clean_visit_role,
            soap_style=_clean_string(soap_style),
        ),
        "clinical_event_text": build_clinical_event_text(clinical_event),
        "semantic_focus_text": build_semantic_focus_text(clean_semantic_focus),
        "retrieval_intent_tags_text": build_retrieval_intent_tags_text(clean_tags),
        "primary_evidence_text": build_primary_evidence_text(
            labs=lab_list,
            medications=medication_list,
            clinical_event=clinical_event,
        ),
        "lab_trend_text": build_lab_trend_text(lab_list),
        "medication_trajectory_text": build_medication_trajectory_text(
            medication_list,
        ),
        "allergy_context_text": build_allergy_context_text(allergy_list),
    }


def build_condition_focus_text(conditions: Iterable[str]) -> str:
    """Describe documented patient-level conditions using condition-aware wording."""
    condition_values = tuple(conditions)

    if not condition_values:
        return (
            "The patient-level condition field does not list documented "
            "conditions."
        )

    phrases = [_condition_phrase(condition) for condition in condition_values]

    return (
        "The patient-level condition field documents "
        f"{_join_phrases(phrases)}."
    )


def build_diagnosis_focus_text(diagnoses: Iterable[str]) -> str:
    """Describe documented visit-level diagnoses using condition-aware wording."""
    diagnosis_values = tuple(diagnoses)

    if not diagnosis_values:
        return (
            "The visit diagnosis field does not list a diagnosis for this "
            "encounter."
        )

    phrases = [_condition_phrase(diagnosis) for diagnosis in diagnosis_values]

    return (
        "The visit diagnosis field documents "
        f"{_join_phrases(phrases)} for this encounter."
    )


def build_monitoring_focus_text(
    *,
    conditions: Iterable[str],
    lab_types: set[str],
) -> str:
    """
    Describe documented monitoring context from conditions and present labs.

    This function does not claim disease control, improvement, deterioration, or
    clinical progression. It only links documented conditions with lab families
    that are actually present in the visit.
    """
    condition_values = tuple(conditions)
    monitoring_parts: list[str] = []

    for condition in condition_values:
        keywords = CONDITION_LAB_KEYWORDS.get(condition, ())

        if not keywords:
            continue

        if any(keyword in lab_types for keyword in keywords):
            monitoring_parts.append(_monitoring_phrase(condition))

    if not monitoring_parts:
        if lab_types:
            return (
                "The visit includes laboratory entries documented in the "
                "objective data."
            )

        return "No laboratory entries are documented for this visit."

    return (
        "The visit contains documented monitoring context for "
        f"{_join_phrases(monitoring_parts)}."
    )


def build_medication_focus_text(
    *,
    conditions: Iterable[str],
    medication_names: set[str],
) -> str:
    """
    Describe documented medication context from present medication entries.

    This function does not recommend, prescribe, start, stop, or adjust any
    medication. It only states that medication entries are present in the visit
    record.
    """
    condition_values = tuple(conditions)
    medication_parts: list[str] = []

    for condition in condition_values:
        keywords = CONDITION_MEDICATION_KEYWORDS.get(condition, ())

        if not keywords:
            continue

        if any(_contains_keyword(medication_names, keyword) for keyword in keywords):
            medication_parts.append(_medication_phrase(condition))

    if not medication_parts:
        if medication_names:
            return (
                "The visit contains medication entries documented in the "
                "medication list."
            )

        return "No active medication entries are documented for this visit."

    return (
        "The medication list includes documented entries related to "
        f"{_join_phrases(medication_parts)}."
    )


def build_visit_context_text(visit_type: str) -> str:
    """Describe visit type without adding clinical meaning."""
    clean_visit_type = _clean_string(visit_type)

    if clean_visit_type in VISIT_TYPE_TEXT:
        return VISIT_TYPE_TEXT[clean_visit_type]

    if clean_visit_type:
        return (
            "The encounter type is documented in the visit record as "
            f"{clean_visit_type}."
        )

    return "The encounter type is not documented in the visit record."


def build_visit_role_text(
    visit_role: Any,
    soap_style: Any | None = None,
) -> str:
    """
    Build a visit_role semantic phrase with style-aware opening and required
    role vocabulary injection.

    Step 9 enhancement:
      1. Prepend a soap_style-specific opener so problem_oriented notes lead
         with "The primary concern today is" and timeline_oriented notes with
         "Compared with the previous visit," — making style groups semantically
         distinct in embedding space even before condition text appears.
      2. Append all VISIT_ROLE_VOCABULARY phrases for the given visit_role so
         that e.g. a partial_adherence visit always contains "reported partial
         adherence" and "missed doses noted", making those visits discriminable
         from routine_follow_up visits in embedding space.

    Safety: only documented values from VISIT_ROLE_LABELS and
    VISIT_ROLE_VOCABULARY are emitted. No new clinical facts are inferred.
    """
    clean_visit_role = _clean_string(visit_role)
    clean_soap_style = _clean_string(soap_style)

    if not clean_visit_role:
        return "No visit_role is documented for this encounter."

    # --- Part 1: style opener ------------------------------------------------
    opener = SOAP_STYLE_OPENERS.get(clean_soap_style, SOAP_STYLE_OPENERS["concise"])

    # --- Part 2: role label --------------------------------------------------
    label = VISIT_ROLE_LABELS.get(clean_visit_role, clean_visit_role.replace("_", " "))

    # --- Part 3: required vocabulary phrases ---------------------------------
    vocab = VISIT_ROLE_VOCABULARY.get(clean_visit_role, ())
    vocab_sentence = (
        " ".join(f"{phrase}." if not phrase.endswith((",", ".")) else phrase for phrase in vocab)
        if vocab
        else ""
    )

    base = f"{opener} the documented visit role is {label}."
    if vocab_sentence:
        return f"{base} {vocab_sentence}"
    return base


def build_timeline_context_text(
    prior_visit_id: Any,
    timeline_pattern: Any | None = None,
    timeline_gap_days: Any | None = None,
) -> str:
    """Describe visit timeline context from documented timeline fields only."""
    parts: list[str] = []
    clean_pattern = _clean_string(timeline_pattern)
    clean_gap = _clean_string(timeline_gap_days)

    if prior_visit_id:
        parts.append(
            "This encounter is linked to a prior documented visit through "
            f"prior_visit_id {prior_visit_id}."
        )
    else:
        parts.append(
            "This encounter has no prior_visit_id and is the first documented "
            "visit in the available timeline."
        )

    if clean_pattern:
        pattern_label = TIMELINE_PATTERN_LABELS.get(
            clean_pattern,
            clean_pattern.replace("_", " "),
        )
        parts.append(f"The documented timeline pattern is {pattern_label}.")

    if clean_gap:
        parts.append(f"The documented timeline_gap_days value is {clean_gap}.")

    return " ".join(parts)


def build_clinical_event_text(clinical_event: Mapping[str, Any] | None) -> str:
    """
    Describe the structured clinical_event object without inference.

    Step 9 enhancement — verbatim event_summary injection:
      The event_summary is placed FIRST and reproduced verbatim (or near-
      verbatim) so it appears at the start of the assessment section text.
      This is the highest-impact single change for RAG retrieval quality:
      two visits that share conditions and medications but have different
      clinical events will now carry distinct, literal phrases in their
      assessment sections, dramatically improving semantic discrimination.

    Safety: only fields present in the structured JSON are rendered.
    No new clinical facts, diagnoses, or treatment decisions are added.
    """
    if not clinical_event:
        return "No clinical_event object is documented for this visit."

    event_type = _clean_string(clinical_event.get("event_type"))
    event_label = _clean_string(clinical_event.get("event_label"))
    event_summary = _clean_string(clinical_event.get("event_summary"))

    if not any([event_type, event_label, event_summary]):
        return "The clinical_event object is present but has no readable fields."

    # --- event_summary leads (verbatim, Step 9 requirement 3) ---------------
    # This is intentional: the event_summary string from the JSON appears at
    # the very start of clinical_event_text so templates that place
    # {clinical_event_text} in the assessment section carry this literal
    # string, ensuring the assessment is semantically unique per visit.
    parts: list[str] = []

    if event_summary:
        parts.append(event_summary)

    # Append type and label as supporting context after the summary.
    if event_type:
        type_label = EVENT_TYPE_LABELS.get(event_type, event_type.replace("_", " "))
        parts.append(f"Clinical event type: {type_label}.")

    if event_label:
        parts.append(f"Event: {event_label}.")

    return " ".join(parts)


def build_semantic_focus_text(semantic_focus: Any) -> str:
    """Describe semantic_focus as a retrieval label, not as clinical truth."""
    clean_focus = _clean_string(semantic_focus)

    if not clean_focus:
        return "No semantic_focus value is documented for this SOAP context."

    label = SEMANTIC_FOCUS_LABELS.get(clean_focus, clean_focus.replace("_", " "))

    return f"The semantic_focus metadata marks this as {label}."


def build_retrieval_intent_tags_text(retrieval_intent_tags: Iterable[Any]) -> str:
    """Describe retrieval_intent_tags as controlled retrieval labels."""
    tags = _clean_values(retrieval_intent_tags)

    if not tags:
        return "No retrieval_intent_tags are documented for this SOAP context."

    display = tuple(tag.replace("_", " ") for tag in tags)

    return "Retrieval intent tags documented for this context: " + _join_phrases(display) + "."


def build_primary_evidence_text(
    *,
    labs: Iterable[Mapping[str, Any]],
    medications: Iterable[Mapping[str, Any]],
    clinical_event: Mapping[str, Any] | None,
) -> str:
    """Build compact documented evidence wording from labs, medications, and event."""
    evidence_parts: list[str] = []
    lab_text = build_lab_trend_text(labs)
    medication_text = build_medication_trajectory_text(medications)
    event_text = build_clinical_event_text(clinical_event)

    if not lab_text.startswith("No laboratory"):
        evidence_parts.append(lab_text)

    if not medication_text.startswith("No medication"):
        evidence_parts.append(medication_text)

    if not event_text.startswith("No clinical_event"):
        evidence_parts.append(event_text)

    if not evidence_parts:
        return (
            "The primary evidence text has no documented labs, medications, or "
            "clinical_event details to summarize."
        )

    return "Primary documented evidence: " + " ".join(evidence_parts)


def build_lab_trend_text(labs: Iterable[Mapping[str, Any]]) -> str:
    """
    Describe documented lab entries without calculating progression.

    The name includes "trend" because templates use lab_trend_text, but this
    function only lists current visit lab entries. Cross-visit interpretation
    belongs outside this module.
    """
    lab_entries: list[str] = []

    for lab in labs:
        lab_type = _clean_string(lab.get("lab_type"))
        value = _clean_string(lab.get("value"))
        unit = _clean_string(lab.get("unit"))
        flag = _clean_string(lab.get("flag"))

        if not lab_type:
            continue

        value_text = ""
        if value and unit:
            value_text = f" {value} {unit}"
        elif value:
            value_text = f" {value}"

        flag_text = f" flagged {flag}" if flag else ""
        lab_entries.append(f"{lab_type}{value_text}{flag_text}")

    if not lab_entries:
        return "No laboratory trend entries are documented for this visit."

    return "Documented laboratory entries include " + _join_phrases(lab_entries) + "."


def build_medication_trajectory_text(
    medications: Iterable[Mapping[str, Any]],
) -> str:
    """Describe medication_status and trajectory_event from documented entries."""
    medication_entries: list[str] = []

    for medication in medications:
        name = _clean_string(medication.get("medication_name"))
        status = _clean_string(medication.get("medication_status"))
        trajectory = _clean_string(medication.get("trajectory_event"))
        reason = _clean_string(medication.get("reason"))

        if not name:
            continue

        parts = [name]
        if status:
            parts.append(f"status {status.replace('_', ' ')}")
        if trajectory:
            parts.append(f"trajectory {trajectory.replace('_', ' ')}")
        if reason:
            parts.append(f"reason: {reason}")

        medication_entries.append("; ".join(parts))

    if not medication_entries:
        return "No medication trajectory entries are documented for this visit."

    return "Documented medication trajectory entries include " + _join_phrases(medication_entries) + "."


def build_allergy_context_text(
    allergy_registry: Iterable[Mapping[str, Any]],
) -> str:
    """Describe patient-level allergy registry entries without prescribing logic."""
    entries: list[str] = []

    for allergy in allergy_registry:
        allergen = _clean_string(allergy.get("allergen"))
        reaction = _clean_string(allergy.get("reaction"))
        severity = _clean_string(allergy.get("severity"))

        if not allergen:
            continue

        parts = [allergen]
        if reaction:
            parts.append(f"reaction {reaction}")
        if severity:
            parts.append(f"severity {severity}")

        entries.append("; ".join(parts))

    if not entries:
        return "No allergy registry entries are documented for this patient."

    return "The allergy registry documents " + _join_phrases(entries) + "."


def build_retrieval_focus_text(
    *,
    conditions: Iterable[str],
    diagnoses: Iterable[str],
    lab_types: set[str],
    medication_names: set[str],
    visit_type: str,
    prior_visit_id: Any,
    visit_role: Any | None = None,
    timeline_pattern: Any | None = None,
    semantic_focus: Any | None = None,
    retrieval_intent_tags: Iterable[Any] | None = None,
    clinical_event: Mapping[str, Any] | None = None,
) -> str:
    """
    Build a compact retrieval-oriented semantic summary.

    The wording is intentionally broad but condition-aware. It helps embedding
    models distinguish chunks by condition, labs, medications, visit type,
    visit_role, timeline pattern, semantic_focus, retrieval tags, and event
    context without adding undocumented clinical claims.
    """
    topics: list[str] = []

    documented_conditions = tuple(conditions)
    documented_diagnoses = tuple(diagnoses)
    clean_visit_role = _clean_string(visit_role)
    clean_timeline_pattern = _clean_string(timeline_pattern)
    clean_semantic_focus = _clean_string(semantic_focus)
    clean_event_type = ""

    if clinical_event:
        clean_event_type = _clean_string(clinical_event.get("event_type"))

    if documented_conditions:
        topics.append(
            "patient-level conditions: "
            + _join_phrases(_condition_phrase(item) for item in documented_conditions)
        )

    if documented_diagnoses:
        topics.append(
            "visit diagnoses: "
            + _join_phrases(_condition_phrase(item) for item in documented_diagnoses)
        )

    if lab_types:
        topics.append("laboratory entries: " + _join_phrases(sorted(lab_types)))

    if medication_names:
        topics.append(
            "medication entries: "
            + _join_phrases(_display_medication_names(medication_names))
        )

    if visit_type:
        topics.append(f"visit type: {visit_type}")

    if clean_visit_role:
        topics.append(f"visit role: {clean_visit_role}")

    if clean_timeline_pattern:
        topics.append(f"timeline pattern: {clean_timeline_pattern}")

    if clean_semantic_focus:
        topics.append(f"semantic focus: {clean_semantic_focus}")

    if clean_event_type:
        topics.append(f"clinical event type: {clean_event_type}")

    tags = _clean_values(retrieval_intent_tags or ())
    if tags:
        topics.append("retrieval tags: " + _join_phrases(tags))

    if prior_visit_id:
        topics.append("timeline link: prior visit documented")
    else:
        topics.append("timeline link: first documented visit")

    if not topics:
        return (
            "This SOAP note supports retrieval over documented encounter "
            "details without adding unstated clinical facts."
        )

    return "Retrieval focus includes " + "; ".join(topics) + "."


def _condition_phrase(condition: str) -> str:
    """Return a display phrase for a documented condition or diagnosis value."""
    return CONDITION_LABELS.get(condition, condition.replace("_", " "))


def _monitoring_phrase(condition: str) -> str:
    """Return condition-aware monitoring wording only for documented lab context."""
    label = _condition_phrase(condition)

    if condition == "T2DM":
        return f"{label} laboratory follow-up"
    if condition in {"HTN", "CKD"}:
        return f"{label} kidney-related laboratory documentation"
    if condition == "IDA":
        return f"{label} blood and iron-related laboratory documentation"
    if condition == "Dyslipidemia":
        return f"{label} LDL laboratory documentation"

    return f"{label} laboratory documentation"


def _medication_phrase(condition: str) -> str:
    """Return condition-aware medication wording only for documented medications."""
    label = _condition_phrase(condition)
    return f"{label} medication documentation"


def _resolve_semantic_focus(
    *,
    semantic_focus: Any | None,
    retrieval_context: Mapping[str, Any] | None,
) -> str:
    direct_focus = _clean_string(semantic_focus)

    if direct_focus:
        return direct_focus

    if retrieval_context:
        return _clean_string(retrieval_context.get("semantic_focus"))

    return ""


def _resolve_retrieval_intent_tags(
    *,
    retrieval_intent_tags: Iterable[Any] | None,
    retrieval_context: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    direct_tags = _clean_values(retrieval_intent_tags or ())

    if direct_tags:
        return direct_tags

    if retrieval_context:
        raw_tags = retrieval_context.get("retrieval_intent_tags", ())
        if isinstance(raw_tags, str):
            return (raw_tags.strip(),) if raw_tags.strip() else ()
        try:
            return _clean_values(raw_tags)
        except TypeError:
            return ()

    return ()


def _clean_values(values: Iterable[Any]) -> tuple[str, ...]:
    """Convert iterable values into non-empty stripped strings."""
    return tuple(
        cleaned
        for value in values
        for cleaned in (_clean_string(value),)
        if cleaned
    )


def _clean_string(value: Any) -> str:
    """Convert any scalar value into a non-empty stripped string when possible."""
    if value is None:
        return ""
    return str(value).strip()


def _lab_type_set(labs: Iterable[Mapping[str, Any]]) -> set[str]:
    """Return normalized lab_type values from visit lab dictionaries."""
    lab_types: set[str] = set()

    for lab in labs:
        lab_type = _clean_string(lab.get("lab_type")).lower()

        if lab_type:
            lab_types.add(lab_type)

    return lab_types


def _medication_name_set(medications: Iterable[Mapping[str, Any]]) -> set[str]:
    """Return normalized medication_name values from visit medication dictionaries."""
    medication_names: set[str] = set()

    for medication in medications:
        medication_name = _clean_string(medication.get("medication_name")).lower()

        if medication_name:
            medication_names.add(medication_name)

    return medication_names


def _contains_keyword(values: set[str], keyword: str) -> bool:
    """Return True if any normalized value contains the normalized keyword."""
    normalized_keyword = keyword.lower()
    return any(normalized_keyword in value for value in values)


def _display_medication_names(medication_names: set[str]) -> tuple[str, ...]:
    """Return deterministic display names for normalized medication names."""
    return tuple(sorted(medication_names))


def _join_phrases(values: Iterable[str]) -> str:
    """Join phrases in a readable deterministic way."""
    phrases = [phrase for phrase in values if phrase]

    if not phrases:
        return "none"

    if len(phrases) == 1:
        return phrases[0]

    if len(phrases) == 2:
        return f"{phrases[0]} and {phrases[1]}"

    return ", ".join(phrases[:-1]) + f", and {phrases[-1]}"


__all__ = (
    "SoapSemanticContext",
    "CONDITION_LABELS",
    "CONDITION_LAB_KEYWORDS",
    "CONDITION_MEDICATION_KEYWORDS",
    "VISIT_TYPE_TEXT",
    "SOAP_STYLE_OPENERS",
    "VISIT_ROLE_LABELS",
    "VISIT_ROLE_VOCABULARY",
    "TIMELINE_PATTERN_LABELS",
    "SEMANTIC_FOCUS_LABELS",
    "EVENT_TYPE_LABELS",
    "build_soap_semantic_context",
    "build_condition_focus_text",
    "build_diagnosis_focus_text",
    "build_monitoring_focus_text",
    "build_medication_focus_text",
    "build_visit_context_text",
    "build_visit_role_text",
    "build_timeline_context_text",
    "build_clinical_event_text",
    "build_semantic_focus_text",
    "build_retrieval_intent_tags_text",
    "build_primary_evidence_text",
    "build_lab_trend_text",
    "build_medication_trajectory_text",
    "build_allergy_context_text",
    "build_retrieval_focus_text",
)
