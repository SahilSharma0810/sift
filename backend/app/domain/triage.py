"""Triage state + reason derivation per PLAN.md schema sketch.

Outputs are written to extractions.predicted_triage_state and
extractions.predicted_triage_reasons (JSONB). Both are immutable per row.

This module is pure: no IO. Anomaly + duplicate detection live in
adjacent domain modules (anomalies.py, duplicates.py); this module only
consumes their results.
"""

from __future__ import annotations

from app.domain.models import (
    AnomalyReason,
    DuplicateOfReason,
    FieldValue,
    LowConfidenceReason,
    MathFailsReason,
    MissingFieldReason,
    TriageReason,
    TriageState,
    UnseenVendorReason,
)
from app.domain.scoring import CASCADE_THRESHOLD
from app.domain.validators import REQUIRED_FIELDS

def derive_triage(
    *,
    extracted_fields: dict[str, FieldValue],
    confidence: dict[str, float],
    math_passed: bool,
    is_unseen_vendor: bool,
    duplicate_of: DuplicateOfReason | None,
    anomalies: list[AnomalyReason] | None = None,
) -> tuple[TriageState, list[TriageReason]]:
    """Derive (predicted_triage_state, predicted_triage_reasons).

    Reason types are the discriminated union from app.domain.models:
      math_fails | anomaly | duplicate_of | low_confidence |
      missing_field | unseen_vendor | extraction_failed
    """
    reasons: list[TriageReason] = []

    if duplicate_of is not None:
        reasons.append(duplicate_of)
        return "likely_duplicate", reasons

    if not math_passed:
        subtotal = _to_float(extracted_fields.get("subtotal"))
        tax = _to_float(extracted_fields.get("tax"))
        total = _to_float(extracted_fields.get("total"))
        if subtotal is not None and tax is not None and total is not None:
            reasons.append(
                MathFailsReason(
                    subtotal=subtotal,
                    tax=tax,
                    total=total,
                    delta=round(abs((subtotal + tax) - total), 2),
                )
            )

    if anomalies:
        reasons.extend(anomalies)

    missing_fields: set[str] = set()
    for field in REQUIRED_FIELDS:
        value = extracted_fields.get(field)
        if value is None or value == "":
            missing_fields.add(field)
            reasons.append(MissingFieldReason(field=field))

    for field, score in confidence.items():
        if not (0.0 < score < CASCADE_THRESHOLD):
            continue
        value = extracted_fields.get(field)
        if value is None or value == "":
            continue
        reasons.append(
            LowConfidenceReason(
                field=field,
                score=round(score, 3),
                reason="below_threshold",
            )
        )

    if is_unseen_vendor:
        reasons.append(
            UnseenVendorReason(
                vendor_name=str(extracted_fields.get("vendor_name", "")),
            )
        )

    blocking_types = {"math_fails", "anomaly", "missing_field", "low_confidence"}
    if any(r.type in blocking_types for r in reasons):
        return "needs_review", reasons

    return "confident", reasons


def _to_float(v: FieldValue) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
