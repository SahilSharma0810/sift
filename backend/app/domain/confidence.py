"""Composite Confidence per ADR-0003.

Single source of truth for "given extracted fields, vendor stats, and
optional cascade agreement scores, what's the per-field confidence and
why?"

The Composite Confidence in Sift is min(structural_score, history_score)
per ADR-0003, plus a Cascade agreement-score override on disputed fields.
Each component lives in its own pure helper here so the report's trace
fields can show a clerk exactly which signal drove a field's score.

Layered correctly: pure. No IO, no ORM, no LLM. The caller extracts the
`vendor_stats` dict from `vendor.memory.stats` before invoking - this
module never sees an ORM row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.scoring import (
    apply_agreement_overrides,
    compute_composite_confidence,
)
from app.domain.validators import compute_structural_scores, math_reconciles

NUMERIC_HISTORY_FIELDS: tuple[str, ...] = ("total",)

MIN_HISTORY_SAMPLES = 3

@dataclass(frozen=True, slots=True)
class FieldConfidence:
    """Per-field confidence with full provenance.

    `composite` is the final value triage uses. The other fields are the
    components that produced it, surfaced so the UI can show a clerk WHY
    a field's confidence is what it is.
    """

    field: str
    composite: float
    structural: float
    history: float | None
    agreement_override: float | None

@dataclass(frozen=True, slots=True)
class ConfidenceReport:
    """Full per-extraction confidence picture."""

    fields: dict[str, FieldConfidence]
    math_passed: bool
    has_vendor_history: bool

    @property
    def composite(self) -> dict[str, float]:
        """Convenience dict view of the final per-field scores."""
        return {f: c.composite for f, c in self.fields.items()}

def compute_confidence(
    *,
    extracted_fields: dict[str, Any],
    vendor_stats: dict[str, Any] | None = None,
    agreement_overrides: dict[str, float] | None = None,
) -> ConfidenceReport:
    """Compute Composite Confidence + provenance for one extraction.

    `vendor_stats` is the cleaned dict from `vendor.memory.stats` (or
    None for a cold-start Vendor). `agreement_overrides` is the per-field
    score returned by the Cascade module when it fired.
    """
    structural = compute_structural_scores(extracted_fields)
    history = compute_history_scores_from_stats(
        extracted_fields=extracted_fields, vendor_stats=vendor_stats
    )
    composite = compute_composite_confidence(structural, history=history)
    if agreement_overrides:
        composite = apply_agreement_overrides(composite, agreement_overrides)
    math_passed = _math_passed(extracted_fields)

    fields: dict[str, FieldConfidence] = {}
    for fname, s_score in structural.items():
        fields[fname] = FieldConfidence(
            field=fname,
            composite=composite[fname],
            structural=s_score,
            history=history.get(fname),
            agreement_override=(agreement_overrides or {}).get(fname),
        )
    return ConfidenceReport(
        fields=fields,
        math_passed=math_passed,
        has_vendor_history=bool(history),
    )

def compute_history_scores_from_stats(
    *,
    extracted_fields: dict[str, Any],
    vendor_stats: dict[str, Any] | None,
) -> dict[str, float]:
    """Per-field history score from a clean vendor-stats dict.

    Returns scores only for numeric fields with sufficient history;
    cold-start / sparse fields are absent (the composite scorer falls
    back to DEFAULT_HISTORY_SCORE for missing keys).
    """
    if not vendor_stats:
        return {}
    n = int(vendor_stats.get("total_seen", 0) or 0)
    if n < MIN_HISTORY_SAMPLES:
        return {}
    out: dict[str, float] = {}
    for fname in NUMERIC_HISTORY_FIELDS:
        value = extracted_fields.get(fname)
        if value is None:
            continue
        try:
            x = float(value)
        except (TypeError, ValueError):
            continue
        mean = float(vendor_stats.get(f"avg_{fname}", 0.0) or 0.0)
        std = float(vendor_stats.get(f"std_{fname}", 0.0) or 0.0)
        if std <= 0:
            continue
        z = (x - mean) / std
        out[fname] = _history_bucket(z)
    return out

def _history_bucket(z: float) -> float:
    """ADR-0003 Z-score buckets: |z|<1: 1.0, <2: 0.85, <3: 0.6, else 0.3."""
    az = abs(z)
    if az < 1.0:
        return 1.0
    if az < 2.0:
        return 0.85
    if az < 3.0:
        return 0.6
    return 0.3

def _math_passed(fields: dict[str, Any]) -> bool:
    return math_reconciles(
        subtotal=_maybe_float(fields.get("subtotal")),
        tax=_maybe_float(fields.get("tax")),
        total=_maybe_float(fields.get("total")),
    )

def _maybe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
