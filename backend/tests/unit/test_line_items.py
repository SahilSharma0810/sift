"""LineItem domain model + line_items_sum_check validator (Day 3).

Day-3 line items are quality-gated: the validator is logged but does NOT
alter triage state. These tests pin down the shape + the math semantics
so the service can call them confidently.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.models import LineItem
from app.domain.validators import AMOUNT_TOLERANCE, line_items_sum_check

class TestLineItemModel:
    def test_minimal_line_item(self) -> None:
        li = LineItem(description="Freight last mile", line_total=780.0)
        assert li.description == "Freight last mile"
        assert li.line_total == 780.0
        assert li.quantity is None
        assert li.unit_price is None
        assert li.confidence == 0.0
        assert li.page == 0
        assert li.bbox is None

    def test_full_line_item(self) -> None:
        li = LineItem(
            description="Aurora delivery",
            quantity=12.0,
            unit_price=65.0,
            line_total=780.0,
            bbox=(0.08, 0.55, 0.92, 0.62),
            page=0,
            confidence=0.92,
        )
        assert li.quantity == 12.0
        assert li.unit_price == 65.0
        assert li.bbox == (0.08, 0.55, 0.92, 0.62)

    def test_extra_keys_rejected(self) -> None:

        with pytest.raises(ValueError):
            LineItem(
                description="x",
                line_total=1.0,
                unknown_field="oops",  # type: ignore[call-arg]
            )

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValueError):
            LineItem(description="x", line_total=1.0, confidence=1.5)
        with pytest.raises(ValueError):
            LineItem(description="x", line_total=1.0, confidence=-0.1)

class TestLineItemsSumCheck:
    def test_empty_list_is_vacuously_true(self) -> None:
        ok, delta = line_items_sum_check([], subtotal=1000.0)
        assert ok is True
        assert delta == Decimal("0")

    def test_none_subtotal_is_vacuously_true(self) -> None:
        ok, delta = line_items_sum_check(
            [{"line_total": 100.0}, {"line_total": 200.0}], subtotal=None
        )
        assert ok is True
        assert delta == Decimal("0")

    def test_exact_match(self) -> None:
        ok, delta = line_items_sum_check(
            [{"line_total": 500.0}, {"line_total": 500.0}], subtotal=1000.0
        )
        assert ok is True
        assert delta == Decimal("0")

    def test_within_tolerance(self) -> None:

        ok, delta = line_items_sum_check(
            [{"line_total": 500.005}, {"line_total": 500.005}], subtotal=1000.0
        )
        assert ok is True
        assert abs(delta) <= AMOUNT_TOLERANCE

    def test_mismatch_returns_false_with_delta(self) -> None:
        ok, delta = line_items_sum_check(
            [{"line_total": 500.0}, {"line_total": 400.0}], subtotal=1000.0
        )
        assert ok is False
        assert delta == Decimal("-100.0")

    def test_missing_line_total_treats_as_zero(self) -> None:
        ok, delta = line_items_sum_check([{"description": "no total"}], subtotal=0.0)
        assert ok is True
        assert delta == Decimal("0")

    def test_non_numeric_line_total_returns_false(self) -> None:
        ok, _ = line_items_sum_check([{"line_total": "not a number"}], subtotal=10.0)
        assert ok is False
