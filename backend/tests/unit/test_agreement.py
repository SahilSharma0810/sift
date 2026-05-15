"""Agreement score per ADR-0003 cascade override.

Two-bucket function: 1.0 (exact) or 0.3 (mismatch). For amount fields, a
Decimal 1-cent tolerance counts as exact (handles OCR drift, locale formatting).
"""

from __future__ import annotations

from app.domain.scoring import agreement_score

class TestAgreementScore:
    def test_exact_string_match(self) -> None:
        assert agreement_score("Vega", "Vega", "vendor_name") == 1.0

    def test_string_mismatch(self) -> None:
        assert agreement_score("Vega", "Vegan", "vendor_name") == 0.3

    def test_amount_within_one_cent(self) -> None:
        assert agreement_score(1180.00, 1180.005, "total") == 1.0

    def test_amount_off_by_a_dollar(self) -> None:
        assert agreement_score(1180.00, 1181.00, "total") == 0.3

    def test_both_none(self) -> None:
        assert agreement_score(None, None, "currency") == 1.0

    def test_one_none(self) -> None:
        assert agreement_score(None, "USD", "currency") == 0.3

    def test_whitespace_normalized_on_strings(self) -> None:
        assert agreement_score("Vega  ", " Vega", "vendor_name") == 1.0

    def test_non_numeric_string_for_amount_field_returns_mismatch(self) -> None:

        assert agreement_score("N/A", 1180.00, "total") == 0.3

    def test_right_none_symmetric(self) -> None:
        assert agreement_score("USD", None, "currency") == 0.3

    def test_at_tolerance_boundary(self) -> None:

        assert agreement_score(1180.00, 1180.01, "total") == 1.0
        assert agreement_score(1180.00, 1180.02, "total") == 0.3
