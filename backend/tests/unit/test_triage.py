"""Triage state derivation per ADR-0003 + PLAN.md schema sketch.

Output: (predicted_triage_state, predicted_triage_reasons) — both immutable
per extraction row, preserved as eval ground truth.
"""

from __future__ import annotations

from uuid import uuid4

from app.domain.triage import derive_triage


class TestDeriveTriage:
    def _clean_fields(self) -> dict[str, object]:
        return {
            "vendor_name": "Vega Logistics",
            "invoice_number": "INV-001",
            "invoice_date": "2026-05-13",
            "subtotal": 1000.0,
            "tax": 180.0,
            "total": 1180.0,
            "currency": "USD",
        }

    def test_clean_invoice_is_confident(self) -> None:
        state, reasons = derive_triage(
            extracted_fields=self._clean_fields(),
            confidence={
                "total": 0.95,
                "vendor_name": 0.85,
                "invoice_date": 0.99,
                "currency": 0.99,
                "subtotal": 0.95,
                "tax": 0.95,
                "invoice_number": 0.85,
            },
            math_passed=True,
            is_unseen_vendor=False,
            duplicate_of=None,
        )
        assert state == "confident"
        assert reasons == []

    def test_math_failure_is_needs_review(self) -> None:
        fields = self._clean_fields()
        fields["total"] = 1181.0  # off
        state, reasons = derive_triage(
            extracted_fields=fields,
            confidence={"total": 0.2, "vendor_name": 0.85},
            math_passed=False,
            is_unseen_vendor=False,
            duplicate_of=None,
        )
        assert state == "needs_review"
        assert any(r["type"] == "math_fails" for r in reasons)
        math_reason = next(r for r in reasons if r["type"] == "math_fails")
        assert math_reason["subtotal"] == 1000.0
        assert math_reason["tax"] == 180.0
        assert math_reason["total"] == 1181.0
        assert math_reason["delta"] == 1.0

    def test_duplicate_is_likely_duplicate(self) -> None:
        original_id = uuid4()
        state, reasons = derive_triage(
            extracted_fields=self._clean_fields(),
            confidence={"total": 0.95},
            math_passed=True,
            is_unseen_vendor=False,
            duplicate_of={
                "invoice_id": original_id,
                "similarity": 0.98,
                "match_method": "perceptual_hash",
            },
        )
        assert state == "likely_duplicate"
        dup_reason = next(r for r in reasons if r["type"] == "duplicate_of")
        assert dup_reason["invoice_id"] == original_id
        assert dup_reason["similarity"] == 0.98

    def test_low_confidence_field_is_needs_review(self) -> None:
        state, reasons = derive_triage(
            extracted_fields=self._clean_fields(),
            confidence={"invoice_number": 0.5, "total": 0.95, "vendor_name": 0.85},
            math_passed=True,
            is_unseen_vendor=False,
            duplicate_of=None,
        )
        assert state == "needs_review"
        low = next(r for r in reasons if r["type"] == "low_confidence")
        assert low["field"] == "invoice_number"

    def test_missing_field_is_needs_review(self) -> None:
        fields = self._clean_fields()
        del fields["currency"]
        state, reasons = derive_triage(
            extracted_fields=fields,
            confidence={"currency": 0.0, "total": 0.95},
            math_passed=True,
            is_unseen_vendor=False,
            duplicate_of=None,
        )
        assert state == "needs_review"
        missing = next(r for r in reasons if r["type"] == "missing_field")
        assert missing["field"] == "currency"

    def test_unseen_vendor_attaches_reason_but_state_can_still_be_confident(self) -> None:
        # Per Q3: unseen_vendor is a reason that surfaces but doesn't by itself
        # demote a clean extraction to needs_review.
        state, reasons = derive_triage(
            extracted_fields=self._clean_fields(),
            confidence={
                "total": 0.95,
                "vendor_name": 0.85,
                "invoice_date": 0.99,
                "currency": 0.99,
                "subtotal": 0.95,
                "tax": 0.95,
                "invoice_number": 0.85,
            },
            math_passed=True,
            is_unseen_vendor=True,
            duplicate_of=None,
        )
        assert state == "confident"
        assert any(r["type"] == "unseen_vendor" for r in reasons)
