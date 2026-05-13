"""Extraction service — full pipeline with mocked LLM, real DB."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.adapters.llm_client import ExtractionResult
from app.services.extraction_service import extract_from_pdf

FIXTURES = Path(__file__).parents[1] / "fixtures"
CLEAN_PDF = FIXTURES / "digital_invoice_clean.pdf"


def _fake_llm_result() -> ExtractionResult:
    return ExtractionResult(
        fields={
            "vendor_name": "Vega Logistics",
            "invoice_number": "INV-2026-0042",
            "invoice_date": "2026-05-13",
            "subtotal": 1000.0,
            "tax": 180.0,
            "total": 1180.0,
            "currency": "USD",
        },
        self_reported_confidence={"total": 0.99, "vendor_name": 0.95},
        extraction_failed=False,
        extraction_failure_reason=None,
        model="claude-haiku-4-5",
        prompt_hash="hashabc",
        schema_hash="hashdef",
        usage={
            "input_tokens": 500,
            "output_tokens": 80,
            "cache_creation_input_tokens": 400,
            "cache_read_input_tokens": 0,
        },
    )


class TestExtractFromPdf:
    def test_happy_path_creates_invoice_and_confident_extraction(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        # Copy the fixture into the test's temp dir so file_path is unique.
        test_pdf = tmp_path / "test.pdf"
        test_pdf.write_bytes(CLEAN_PDF.read_bytes())

        with patch(
            "app.services.extraction_service.LLMClient.extract_header",
            return_value=_fake_llm_result(),
        ):
            result = extract_from_pdf(db_session, pdf_path=test_pdf)

        # Returns the invoice + current extraction
        assert result.invoice.review_status == "pending"
        assert result.extraction.predicted_triage_state == "confident"
        assert result.extraction.is_current is True
        # Composite confidence applied (history default 0.85 on cold-start vendor)
        assert result.extraction.confidence_per_field["total"] == 0.85

    def test_duplicate_file_returns_existing_invoice(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        test_pdf = tmp_path / "dup.pdf"
        test_pdf.write_bytes(CLEAN_PDF.read_bytes())

        with patch(
            "app.services.extraction_service.LLMClient.extract_header",
            return_value=_fake_llm_result(),
        ):
            r1 = extract_from_pdf(db_session, pdf_path=test_pdf)
            r2 = extract_from_pdf(db_session, pdf_path=test_pdf)
        # Same file → same invoice (file_hash dedup).
        assert r1.invoice.id == r2.invoice.id

    def test_llm_reported_failure_produces_extraction_failed_reason(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        """When the LLM sets extraction_failed=True, the service short-circuits
        domain logic and writes a single extraction_failed reason per ADR-0006."""
        # Write distinct bytes so file_hash differs from other tests that use CLEAN_PDF.
        test_pdf = tmp_path / "fail.pdf"
        test_pdf.write_bytes(CLEAN_PDF.read_bytes() + b"\x00")

        failed_result = ExtractionResult(
            fields={
                "vendor_name": None,
                "invoice_number": None,
                "invoice_date": None,
                "subtotal": None,
                "tax": None,
                "total": None,
                "currency": None,
            },
            self_reported_confidence={},
            extraction_failed=True,
            extraction_failure_reason="document is a resume, not an invoice",
            model="claude-haiku-4-5",
            prompt_hash="h",
            schema_hash="h",
            usage={
                "input_tokens": 100,
                "output_tokens": 5,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        )

        with patch(
            "app.services.extraction_service.LLMClient.extract_header",
            return_value=failed_result,
        ):
            result = extract_from_pdf(db_session, pdf_path=test_pdf)

        assert result.extraction.predicted_triage_state == "needs_review"
        reasons = result.extraction.predicted_triage_reasons
        assert len(reasons) == 1
        assert reasons[0]["type"] == "extraction_failed"
        assert reasons[0]["stage"] == "llm_call"
        assert "resume" in reasons[0]["detail"]
        # No structural validation ran — empty fields:
        assert result.extraction.extracted_fields == {}
