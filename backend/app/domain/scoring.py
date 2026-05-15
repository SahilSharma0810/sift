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

# Cold-start default per ADR-0003 — "slightly hedged" so structural_score
# dominates when no per-vendor history exists.
DEFAULT_HISTORY_SCORE = 0.85

# Cascade trigger threshold per ADR-0003.
CASCADE_THRESHOLD = 0.7


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
    """Cascade fires when math fails OR unseen vendor OR min(confidence) < 0.7.

    Empty confidence dict is treated as total extraction failure (or upstream
    bug) — failsafe to True so the triage layer never silently bypasses
    review on missing signal.

    Per ADR-0003. The disputed-field agreement-override logic lives in
    services/extraction_service when the cascade actually runs.
    """
    if not math_passed:
        return True
    if is_unseen_vendor:
        return True
    if not confidence:
        return True  # failsafe: missing signal = cascade
    return min(confidence.values()) < CASCADE_THRESHOLD


# 1-cent tolerance for cross-model agreement — stricter than the 2-cent
# AMOUNT_TOLERANCE in validators.py because two models seeing the same
# input have no reason to diverge by more than a rounding artifact.
# The 2-cent math-reconciliation budget absorbs OCR drift before agreement
# is even checked.
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
