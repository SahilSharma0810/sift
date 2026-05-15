"""Composite confidence per ADR-0003.

    confidence_per_field = min(structural_score, history_score)

`structural_score` comes from app.domain.validators.compute_structural_scores.
`history_score` comes from per-vendor Z-score computation against
vendors.memory.stats — that lives in services/vendor_memory_service.

When history is absent for a field (cold-start vendor, non-numeric field
without a rule), it defaults to 0.85 per ADR-0003.
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.validators import AMOUNT_FIELDS

DEFAULT_HISTORY_SCORE = 0.85

CASCADE_THRESHOLD = 0.7

UNSEEN_VENDOR_CONFIDENCE_FLOOR = 0.85

def compute_composite_confidence(
    structural: dict[str, float],
    history: dict[str, float],
) -> dict[str, float]:
    """Per-field composite confidence.

    For each field in `structural`, returns min(structural_score, history_score)
    where history_score defaults to DEFAULT_HISTORY_SCORE if not in `history`.
    """
    out: dict[str, float] = {}
    for field, s_score in structural.items():
        h_score = history.get(field, DEFAULT_HISTORY_SCORE)
        out[field] = min(s_score, h_score)
    return out

def should_trigger_cascade(
    confidence: dict[str, float],
    math_passed: bool,
    is_unseen_vendor: bool,
) -> bool:
    """Cascade trigger per ADR-0003 (amended).

    Fires when ANY of:
      - math reconciliation failed
      - confidence dict is empty (extraction failure / upstream bug)
      - min(confidence) < CASCADE_THRESHOLD (0.7)
      - vendor is unseen AND min(confidence) < UNSEEN_VENDOR_CONFIDENCE_FLOOR (0.85)

    Originally ADR-0003 treated `is_unseen_vendor` as an unconditional
    trigger. In practice that fired the cascade on every first-touch
    vendor regardless of how strongly the initial tier had pinned the
    fields, which inflated cost without improving correctness when the
    initial tier was already confident. The amended rule keeps the
    unseen-vendor signal as a strong risk factor — it lowers the
    threshold to 0.85 — but no longer forces escalation when the
    initial tier is convinced.

    Empty confidence is still a failsafe-to-True so triage can't be
    silently bypassed on missing signal.
    """
    if not math_passed:
        return True
    if not confidence:
        return True
    min_conf = min(confidence.values())
    if is_unseen_vendor and min_conf < UNSEEN_VENDOR_CONFIDENCE_FLOOR:
        return True
    return min_conf < CASCADE_THRESHOLD

NUMERIC_AGREEMENT_TOLERANCE = Decimal("0.01")

def agreement_score(left: object, right: object, field: str) -> float:
    """Two-bucket cascade-agreement score per ADR-0003.

    1.0 when two model outputs agree on a field, 0.3 when they don't.
    Amount fields use a Decimal 1-cent tolerance.
    """
    if left is None and right is None:
        return 1.0
    if left is None or right is None:
        return 0.3
    if field in AMOUNT_FIELDS:
        try:
            diff = abs(Decimal(str(left)) - Decimal(str(right)))
            return 1.0 if diff <= NUMERIC_AGREEMENT_TOLERANCE else 0.3
        except Exception:
            return 0.3
    return 1.0 if str(left).strip() == str(right).strip() else 0.3

def apply_agreement_overrides(
    composite: dict[str, float],
    overrides: dict[str, float],
) -> dict[str, float]:
    """Apply Cascade agreement-score overrides to composite confidence.

    Per ADR-0003 the disputed-field confidence is REPLACED by the
    agreement score, but we take min() against the existing composite
    so a low structural floor (e.g. math failed -> 0.2) never gets
    lifted by a high agreement override. No-op when `overrides` is
    empty (cascade did not fire).
    """
    if not overrides:
        return dict(composite)
    out = dict(composite)
    for field, score in overrides.items():
        out[field] = min(out.get(field, 1.0), score)
    return out
