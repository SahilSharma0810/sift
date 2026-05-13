"""Validators per ADR-0003 — pure functions producing per-field structural_score.

If math validation fails on amount fields, structural_score on those fields drops
to 0.2 (hard floor). Per ADR-0003 the composite confidence will then pin those
fields to ≤0.2 regardless of vendor history — math-failing extractions can never
be marked `confident`.
"""

from __future__ import annotations

from app.domain.validators import (
    find_missing_required,
    is_valid_currency_code,
    is_valid_date,
    math_reconciles,
)


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


class TestIsValidDate:
    def test_iso_date(self) -> None:
        assert is_valid_date("2026-05-13") is True

    def test_us_format(self) -> None:
        assert is_valid_date("05/13/2026") is True

    def test_uk_format(self) -> None:
        assert is_valid_date("13/05/2026") is True

    def test_garbage(self) -> None:
        assert is_valid_date("not a date") is False

    def test_empty(self) -> None:
        assert is_valid_date("") is False

    def test_none(self) -> None:
        assert is_valid_date(None) is False


class TestIsValidCurrencyCode:
    def test_usd(self) -> None:
        assert is_valid_currency_code("USD") is True

    def test_eur(self) -> None:
        assert is_valid_currency_code("EUR") is True

    def test_inr(self) -> None:
        assert is_valid_currency_code("INR") is True

    def test_lowercase(self) -> None:
        assert is_valid_currency_code("usd") is True

    def test_invented(self) -> None:
        assert is_valid_currency_code("ZZZ") is False

    def test_empty(self) -> None:
        assert is_valid_currency_code("") is False


class TestFindMissingRequired:
    def test_all_present(self) -> None:
        fields = {
            "vendor_name": "Vega Logistics",
            "invoice_number": "INV-001",
            "invoice_date": "2026-05-13",
            "total": 1180.0,
            "currency": "USD",
        }
        assert find_missing_required(fields) == []

    def test_missing_total(self) -> None:
        fields = {
            "vendor_name": "Vega Logistics",
            "invoice_number": "INV-001",
            "invoice_date": "2026-05-13",
            "currency": "USD",
        }
        assert find_missing_required(fields) == ["total"]

    def test_blank_string_counts_as_missing(self) -> None:
        fields = {
            "vendor_name": "",
            "invoice_number": "INV-001",
            "invoice_date": "2026-05-13",
            "total": 1180.0,
            "currency": "USD",
        }
        assert find_missing_required(fields) == ["vendor_name"]

    def test_none_counts_as_missing(self) -> None:
        fields = {
            "vendor_name": "Vega Logistics",
            "invoice_number": None,
            "invoice_date": "2026-05-13",
            "total": 1180.0,
            "currency": "USD",
        }
        assert find_missing_required(fields) == ["invoice_number"]
