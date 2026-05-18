"""
generators/lab_generator.py

Deterministic lab generation.

Important:
- Blood pressure is NOT a lab.
- BP must exist only inside visit["vitals"].
- This module never creates BP, systolic, diastolic, SBP, DBP, or blood_pressure labs.

Freeze decision:
Labs are condition-driven and deterministic.
Labs support retrieval-friendly longitudinal trends for the final 30-patient dataset.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from config.constants import (
    CKD_CREATININE_SERIES,
    IDA_BASELINE_PROFILES,
    LAB_REFERENCE_RANGES,
    LAB_UNITS,
    NON_CKD_CREATININE_SERIES,
    T2DM_BASELINE_PROFILES,
)


def add_labs_to_patient(patient: dict[str, Any]) -> dict[str, Any]:
    """
    Add deterministic lab results to every visit in a patient record.

    This function is imported by scripts/generate_all.py.
    """
    updated = deepcopy(patient)
    conditions = set(updated.get("conditions", []))
    patient_id = str(updated["patient_id"])

    for index, visit in enumerate(updated.get("visits", [])):
        visit["labs"] = _generate_labs_for_visit(
            patient_id=patient_id,
            conditions=conditions,
            visit_index=index,
        )

    return updated


def _generate_labs_for_visit(
    patient_id: str,
    conditions: set[str],
    visit_index: int,
) -> list[dict[str, Any]]:
    """
    Generate condition-driven labs for one visit.

    BP is intentionally excluded.
    """
    labs: list[dict[str, Any]] = []

    if not conditions:
        labs.extend(_normal_patient_labs(patient_id, visit_index))

    if "T2DM" in conditions:
        hba1c, fbg = _t2dm_labs(patient_id, visit_index)
        labs.append(_make_lab("HbA1c", hba1c))
        labs.append(_make_lab("FBG", fbg))

    if _should_generate_creatinine(conditions):
        creatinine = _creatinine_value(
            has_ckd="CKD" in conditions,
            visit_index=visit_index,
        )
        labs.append(_make_lab("Creatinine", creatinine))

    if "IDA" in conditions:
        hemoglobin, ferritin = _ida_labs(patient_id, visit_index)
        labs.append(_make_lab("Hemoglobin", hemoglobin))
        labs.append(_make_lab("Ferritin", ferritin))

    return labs


def _should_generate_creatinine(conditions: set[str]) -> bool:
    """
    Generate Creatinine only for CKD complication tracking or combined T2DM+HTN.

    This keeps Creatinine aligned with the locked project scope:
    - CKD patients always receive Creatinine tracking.
    - Non-CKD patients receive Creatinine only when both T2DM and HTN are present.
    - T2DM-only or HTN-only patients do not receive Creatinine labs.

    BP remains excluded from labs entirely.
    """
    return "CKD" in conditions or {"T2DM", "HTN"}.issubset(conditions)


def _normal_patient_labs(patient_id: str, visit_index: int) -> list[dict[str, Any]]:
    """
    Generate simple normal-range labs for normal patients.

    This supports lab retrieval examples without adding chronic diagnoses.
    """
    patient_number = _patient_number(patient_id)

    hemoglobin_base = 14.0 if patient_number % 2 == 1 else 12.8
    ferritin_base = 72 if patient_number % 2 == 1 else 62

    hemoglobin = round(hemoglobin_base + ((patient_number % 3) * 0.1), 1)
    ferritin = ferritin_base + (patient_number % 5) + min(visit_index, 2)

    return [
        _make_lab("Hemoglobin", hemoglobin),
        _make_lab("Ferritin", ferritin),
    ]


def _t2dm_labs(patient_id: str, visit_index: int) -> tuple[float, int]:
    """
    Generate HbA1c and FBG progression for T2DM patients.
    """
    patient_number = _patient_number(patient_id)
    profile = T2DM_BASELINE_PROFILES[
        (patient_number - 1) % len(T2DM_BASELINE_PROFILES)
    ]

    baseline_hba1c = float(profile["hba1c"])
    baseline_fbg = int(profile["fbg"])

    hba1c = baseline_hba1c - (0.25 * min(visit_index, 8))
    fbg = baseline_fbg - (9 * min(visit_index, 8))

    return round(max(hba1c, 6.4), 1), max(fbg, 105)


def _ida_labs(patient_id: str, visit_index: int) -> tuple[float, int]:
    """
    Generate Hemoglobin and Ferritin progression for IDA patients.
    """
    patient_number = _patient_number(patient_id)
    profile = IDA_BASELINE_PROFILES[
        (patient_number - 1) % len(IDA_BASELINE_PROFILES)
    ]

    baseline_hemoglobin = float(profile["hemoglobin"])
    baseline_ferritin = int(profile["ferritin"])

    hemoglobin = baseline_hemoglobin + (0.45 * min(visit_index, 6))
    ferritin = baseline_ferritin + (5 * min(visit_index, 6))

    return round(min(hemoglobin, 12.6), 1), min(ferritin, 45)


def _creatinine_value(has_ckd: bool, visit_index: int) -> float:
    """
    Generate Creatinine values using frozen progression series.

    CKD patients use the CKD series.
    Non-CKD T2DM/HTN patients use the non-CKD series.
    """
    series = CKD_CREATININE_SERIES if has_ckd else NON_CKD_CREATININE_SERIES
    return float(series[min(visit_index, len(series) - 1)])


def _patient_number(patient_id: str) -> int:
    return int(patient_id.split("-")[-1])


def _make_lab(lab_type: str, value: float | int) -> dict[str, Any]:
    """
    Build a schema-compatible lab object.
    """
    return {
        "lab_type": lab_type,
        "value": value,
        "unit": LAB_UNITS[lab_type],
        "reference_range": LAB_REFERENCE_RANGES[lab_type],
        "flag": _flag_for_lab(lab_type, value),
    }


def _flag_for_lab(lab_type: str, value: float | int) -> str:
    """
    Assign locked lab flags: NORMAL, HIGH, LOW.
    """
    if lab_type == "HbA1c":
        return "HIGH" if value > 5.6 else "NORMAL"

    if lab_type == "FBG":
        return "HIGH" if value > 99 else "NORMAL"

    if lab_type == "Creatinine":
        return "HIGH" if value > 1.2 else "NORMAL"

    if lab_type == "Hemoglobin":
        return "LOW" if value < 12.0 else "NORMAL"

    if lab_type == "Ferritin":
        return "LOW" if value < 30 else "NORMAL"

    raise ValueError(f"Unsupported lab_type: {lab_type}")