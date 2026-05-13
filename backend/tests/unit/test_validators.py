"""Validators per ADR-0003 — pure functions producing per-field structural_score.

If math validation fails on amount fields, structural_score on those fields drops
to 0.2 (hard floor). Per ADR-0003 the composite confidence will then pin those
fields to ≤0.2 regardless of vendor history — math-failing extractions can never
be marked `confident`.
"""

from __future__ import annotations

from app.domain.validators import math_reconciles


class TestMathReconciles:
    def test_exact_match(self) -> None:
        assert math_reconciles(subtotal=1000.0, tax=180.0, total=1180.0) is True

    def test_off_by_a_dollar(self) -> None:
        assert math_reconciles(subtotal=1000.0, tax=180.0, total=1181.0) is False

    def test_within_rounding_tolerance(self) -> None:
        # 2-cent tolerance for rounding in scanned/OCRd amounts.
        assert math_reconciles(subtotal=1000.0, tax=180.0, total=1180.01) is True

    def test_negative_amounts_rejected(self) -> None:
        assert math_reconciles(subtotal=-100.0, tax=18.0, total=-82.0) is False
