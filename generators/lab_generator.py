"""
generators/lab_generator.py

Deterministic lab generation.

Important:
- Blood pressure is NOT a lab.
- BP must exist only inside visit["vitals"].
- This module never creates BP, systolic, diastolic, SBP, DBP, or blood_pressure labs.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from config.constants import LAB_REFERENCE_RANGES, LAB_UNITS


def add_labs_to_patient(patient: dict[str, Any]) -> dict[str, Any]:
    """
    Add deterministic lab results to every visit in a patient record.

    This function is imported by scripts/generate_all.py.
    """
    updated = deepcopy(patient)
    conditions = set(updated.get("conditions", []))

    for index, visit in enumerate(updated.get("visits", [])):
        visit["labs"] = _generate_labs_for_visit(
            patient_id=updated["patient_id"],
            conditions=conditions,
            visit_index=index,
        )

    return updated


def _generate_labs_for_visit(
    patient_id: str,
    conditions: set[str],
    visit_index: int,
) -> list[dict[str, Any]]:
    labs: list[dict[str, Any]] = []

    if not conditions:
        labs.extend(_normal_patient_labs(patient_id, visit_index))

    if "T2DM" in conditions:
        labs.append(_make_lab("HbA1c", _series_value(_hba1c_series(patient_id), visit_index)))
        labs.append(_make_lab("FBG", _series_value(_fbg_series(patient_id), visit_index)))

    if {"T2DM", "HTN"}.issubset(conditions):
        labs.append(
            _make_lab(
                "Creatinine",
                _series_value(
                    _creatinine_series(has_ckd="CKD" in conditions),
                    visit_index,
                ),
            )
        )

    if "IDA" in conditions:
        labs.append(_make_lab("Hemoglobin", _series_value(_hemoglobin_series(), visit_index)))
        labs.append(_make_lab("Ferritin", _series_value(_ferritin_series(), visit_index)))

    return labs


def _normal_patient_labs(patient_id: str, visit_index: int) -> list[dict[str, Any]]:
    if patient_id == "PAT-NRM-001":
        hemoglobin_values = [14.2, 14.1]
        ferritin_values = [76, 78]
    else:
        hemoglobin_values = [12.8, 13.0]
        ferritin_values = [64, 67]

    return [
        _make_lab("Hemoglobin", _series_value(hemoglobin_values, visit_index)),
        _make_lab("Ferritin", _series_value(ferritin_values, visit_index)),
    ]


def _hba1c_series(patient_id: str) -> list[float]:
    if patient_id == "PAT-CHR-001":
        return [9.2, 8.8, 8.3, 8.0, 7.6, 7.3]

    return [8.1, 7.7, 7.2, 6.9]


def _fbg_series(patient_id: str) -> list[int]:
    if patient_id == "PAT-CHR-001":
        return [186, 174, 160, 154, 140, 132]

    return [165, 150, 132, 118]


def _creatinine_series(has_ckd: bool) -> list[float]:
    if has_ckd:
        return [1.4, 1.5, 1.6, 1.7, 1.5, 1.4]

    return [0.9, 0.9, 1.0, 0.9]


def _hemoglobin_series() -> list[float]:
    return [9.8, 10.6, 11.4, 12.1]


def _ferritin_series() -> list[int]:
    return [12, 18, 25, 34]


def _series_value(values: list[float | int], index: int) -> float | int:
    return values[min(index, len(values) - 1)]


def _make_lab(lab_type: str, value: float | int) -> dict[str, Any]:
    return {
        "lab_type": lab_type,
        "value": value,
        "unit": LAB_UNITS[lab_type],
        "reference_range": LAB_REFERENCE_RANGES[lab_type],
        "flag": _flag_for_lab(lab_type, value),
    }


def _flag_for_lab(lab_type: str, value: float | int) -> str:
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