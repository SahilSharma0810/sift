"""Composite confidence per ADR-0003: min(structural, history)."""

from __future__ import annotations

from app.domain.scoring import (
    apply_agreement_overrides,
    compute_composite_confidence,
    should_trigger_cascade,
)


class TestCompositeConfidence:
    def test_no_history_falls_back_to_neutral(self) -> None:
        structural = {"total": 1.0, "vendor_name": 0.9}
        history: dict[str, float] = {}  # cold-start vendor
        out = compute_composite_confidence(structural, history)
        # min(1.0, 0.85) = 0.85; min(0.9, 0.85) = 0.85
        assert out["total"] == 0.85
        assert out["vendor_name"] == 0.85

    def test_history_present_takes_min(self) -> None:
        structural = {"total": 1.0}
        history = {"total": 0.6}  # vendor history says this total is unusual
        out = compute_composite_confidence(structural, history)
        assert out["total"] == 0.6

    def test_math_floor_dominates_even_with_perfect_history(self) -> None:
        structural = {"total": 0.2}  # math failed
        history = {"total": 1.0}  # vendor history says normal
        out = compute_composite_confidence(structural, history)
        # Math failure should never be overridden — pinned to 0.2.
        assert out["total"] == 0.2

    def test_missing_field_dominates(self) -> None:
        structural = {"currency": 0.0}
        history = {"currency": 1.0}
        out = compute_composite_confidence(structural, history)
        assert out["currency"] == 0.0


class TestCascadeTrigger:
    def test_all_confident_no_trigger(self) -> None:
        assert (
            should_trigger_cascade(
                confidence={"total": 0.95, "vendor_name": 0.85},
                math_passed=True,
                is_unseen_vendor=False,
            )
            is False
        )

    def test_low_confidence_triggers(self) -> None:
        assert (
            should_trigger_cascade(
                confidence={"total": 0.5, "vendor_name": 0.85},
                math_passed=True,
                is_unseen_vendor=False,
            )
            is True
        )

    def test_math_failure_always_triggers(self) -> None:
        assert (
            should_trigger_cascade(
                confidence={"total": 0.95},
                math_passed=False,
                is_unseen_vendor=False,
            )
            is True
        )

    def test_unseen_vendor_always_triggers(self) -> None:
        assert (
            should_trigger_cascade(
                confidence={"total": 0.95},
                math_passed=True,
                is_unseen_vendor=True,
            )
            is True
        )

    def test_empty_confidence_triggers(self) -> None:
        """No fields scored at all — failsafe to cascade so triage isn't silently bypassed."""
        assert (
            should_trigger_cascade(
                confidence={},
                math_passed=True,
                is_unseen_vendor=False,
            )
            is True
        )

    def test_exactly_at_threshold_does_not_trigger(self) -> None:
        """ADR-0003 says < 0.7 triggers — boundary value should NOT trigger."""
        assert (
            should_trigger_cascade(
                confidence={"total": 0.7},
                math_passed=True,
                is_unseen_vendor=False,
            )
            is False
        )

    def test_just_below_threshold_triggers(self) -> None:
        assert (
            should_trigger_cascade(
                confidence={"total": 0.69},
                math_passed=True,
                is_unseen_vendor=False,
            )
            is True
        )


class TestApplyAgreementOverrides:
    def test_empty_overrides_returns_copy(self) -> None:
        composite = {"total": 0.85, "vendor_name": 0.9}
        out = apply_agreement_overrides(composite, {})
        assert out == composite
        assert out is not composite  # defensive copy

    def test_dispute_override_lowers_confidence(self) -> None:
        composite = {"total": 0.85}
        overrides = {"total": 0.3}
        out = apply_agreement_overrides(composite, overrides)
        assert out["total"] == 0.3

    def test_agreement_override_never_lifts_low_floor(self) -> None:
        """Math failed -> structural pinned `total` at 0.2. Even if both
        tiers agreed (override=1.0), the 0.2 floor must hold."""
        composite = {"total": 0.2}
        overrides = {"total": 1.0}
        out = apply_agreement_overrides(composite, overrides)
        assert out["total"] == 0.2

    def test_override_for_field_missing_from_composite_uses_neutral_default(self) -> None:
        """An override for a field that wasn't in the composite (e.g.
        `subtotal` on an invoice that didn't surface one) is min'd
        against 1.0 - the override score becomes the final confidence."""
        composite: dict[str, float] = {}
        overrides = {"subtotal": 0.3}
        out = apply_agreement_overrides(composite, overrides)
        assert out["subtotal"] == 0.3

    def test_non_overridden_fields_pass_through(self) -> None:
        composite = {"total": 0.85, "vendor_name": 0.9}
        overrides = {"total": 0.3}
        out = apply_agreement_overrides(composite, overrides)
        assert out["vendor_name"] == 0.9
