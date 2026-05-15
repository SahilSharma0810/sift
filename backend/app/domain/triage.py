"""Triage state + reason derivation per PLAN.md schema sketch.

Outputs are written to extractions.predicted_triage_state and
extractions.predicted_triage_reasons (JSONB). Both are immutable per row.

This module is pure: no IO. Anomaly + duplicate detection live in
adjacent domain modules (anomalies.py, duplicates.py); this module only
consumes their results.
"""

from __future__ import annotations

from typing import Any

from app.domain.scoring import CASCADE_THRESHOLD
from app.domain.validators import REQUIRED_FIELDS

def derive_triage(
    *,
    extracted_fields: dict[str, object],
    confidence: dict[str, float],
    math_passed: bool,
    is_unseen_vendor: bool,
    duplicate_of: dict[str, Any] | None,
    anomalies: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Derive (predicted_triage_state, predicted_triage_reasons).

    Reason types are the discriminated union from app.domain.models:
      math_fails | anomaly | duplicate_of | low_confidence |
      missing_field | unseen_vendor | extraction_failed
    """
    reasons: list[dict[str, Any]] = []

    if duplicate_of:
        reasons.append({"type": "duplicate_of", **duplicate_of})
        return "likely_duplicate", reasons

    if not math_passed:
        try:
            subtotal = float(extracted_fields.get("subtotal", 0) or 0)
            tax = float(extracted_fields.get("tax", 0) or 0)
            total = float(extracted_fields.get("total", 0) or 0)
            reasons.append(
                {
                    "type": "math_fails",
                    "subtotal": subtotal,
                    "tax": tax,
                    "total": total,
                    "delta": round(abs((subtotal + tax) - total), 2),
                }
            )
        except (TypeError, ValueError):
            pass

    if anomalies:
        for a in anomalies:
            reasons.append({"type": "anomaly", **a})

    missing_fields: set[str] = set()
    for field in REQUIRED_FIELDS:
        value = extracted_fields.get(field)
        if value is None or value == "":
            missing_fields.add(field)
            reasons.append({"type": "missing_field", "field": field})

    for field, score in confidence.items():
        if not (0.0 < score < CASCADE_THRESHOLD):
            continue
        value = extracted_fields.get(field)
        if value is None or value == "":
            continue
        reasons.append(
            {
                "type": "low_confidence",
                "field": field,
                "score": round(score, 3),
                "reason": "below_threshold",
            }
        )

    if is_unseen_vendor:
        reasons.append(
            {
                "type": "unseen_vendor",
                "vendor_name": str(extracted_fields.get("vendor_name", "")),
            }
        )

    blocking_types = {"math_fails", "anomaly", "missing_field", "low_confidence"}
    if any(r["type"] in blocking_types for r in reasons):
        return "needs_review", reasons

    return "confident", reasons
