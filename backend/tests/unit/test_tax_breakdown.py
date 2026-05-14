"""TaxBreakdownLine domain model + tax_breakdown_sum_check validator (Day 4).

Day-4 tax breakdown is quality-gated, mirroring Day-3 line items: the
validator is logged but does NOT alter triage state. These tests pin
down the shape + math semantics.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.models import TaxBreakdownLine
from app.domain.validators import AMOUNT_TOLERANCE, tax_breakdown_sum_check


class TestTaxBreakdownLineModel:
    def test_minimal_row(self) -> None:
        row = TaxBreakdownLine(jurisdiction="CA Sales Tax", amount=72.50)
        assert row.jurisdiction == "CA Sales Tax"
        assert row.amount == 72.50
        assert row.rate is None
        assert row.page == 0
        assert row.bbox is None

    def test_full_row(self) -> None:
        row = TaxBreakdownLine(
            jurisdiction="VAT 20%",
            rate=20.0,
            amount=200.00,
            bbox=(0.55, 0.71, 0.88, 0.74),
            page=0,
            confidence=0.95,
        )
        assert row.rate == 20.0
        assert row.bbox == (0.55, 0.71, 0.88, 0.74)

    def test_extra_keys_rejected(self) -> None:
        with pytest.raises(ValueError):
            TaxBreakdownLine(
                jurisdiction="x",
                amount=1.0,
                weird_key="oops",  # type: ignore[call-arg]
            )

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValueError):
            TaxBreakdownLine(jurisdiction="x", amount=1.0, confidence=1.5)


class TestTaxBreakdownSumCheck:
    def test_empty_is_vacuously_true(self) -> None:
        ok, delta = tax_breakdown_sum_check([], header_tax=180.0)
        assert ok is True
        assert delta == Decimal("0")

    def test_none_header_tax_is_vacuously_true(self) -> None:
        ok, delta = tax_breakdown_sum_check([{"amount": 50.0}, {"amount": 130.0}], header_tax=None)
        assert ok is True
        assert delta == Decimal("0")

    def test_exact_match(self) -> None:
        ok, delta = tax_breakdown_sum_check([{"amount": 90.0}, {"amount": 90.0}], header_tax=180.0)
        assert ok is True
        assert delta == Decimal("0")

    def test_within_tolerance(self) -> None:
        ok, delta = tax_breakdown_sum_check(
            [{"amount": 90.005}, {"amount": 90.005}], header_tax=180.0
        )
        assert ok is True
        assert abs(delta) <= AMOUNT_TOLERANCE

    def test_mismatch_returns_false_with_delta(self) -> None:
        ok, delta = tax_breakdown_sum_check([{"amount": 90.0}, {"amount": 50.0}], header_tax=180.0)
        assert ok is False
        assert delta == Decimal("-40.0")

    def test_non_numeric_returns_false(self) -> None:
        ok, _ = tax_breakdown_sum_check([{"amount": "not a number"}], header_tax=10.0)
        assert ok is False
