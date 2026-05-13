"""Composite confidence per ADR-0003.

    confidence_per_field = min(structural_score, history_score)

`structural_score` comes from app.domain.validators.compute_structural_scores.
`history_score` comes from per-vendor Z-score computation against
vendors.memory.stats — that lives in services/vendor_memory_service.

When history is absent for a field (cold-start vendor, non-numeric field
without a rule), it defaults to 0.85 per ADR-0003.
"""

from __future__ import annotations

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
