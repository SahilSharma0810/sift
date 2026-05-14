"""Extraction service — full pipeline with mocked LLM, real DB."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.adapters.llm_client import ExtractionResult, LineItemsResult
from app.services.extraction_service import extract_from_pdf
from tests.conftest import patch_make_llm_client

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

        with patch_make_llm_client(header=_fake_llm_result()):
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

        with patch_make_llm_client(header=_fake_llm_result()):
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

        with patch_make_llm_client(header=failed_result):
            result = extract_from_pdf(db_session, pdf_path=test_pdf)

        assert result.extraction.predicted_triage_state == "needs_review"
        reasons = result.extraction.predicted_triage_reasons
        assert len(reasons) == 1
        assert reasons[0]["type"] == "extraction_failed"
        assert reasons[0]["stage"] == "llm_call"
        assert "resume" in reasons[0]["detail"]
        # No structural validation ran — empty fields:
        assert result.extraction.extracted_fields == {}


SCAN_PDF = FIXTURES / "scan_invoice.pdf"


class TestExtractFromPdfVisionPath:
    def test_vision_path_taken_for_scan(self, db_session: Session, tmp_path: Path) -> None:
        from app.adapters.llm_client import ExtractionResult

        test_pdf = tmp_path / "scan.pdf"
        test_pdf.write_bytes(SCAN_PDF.read_bytes())

        vision_result = ExtractionResult(
            fields={
                "vendor_name": {
                    "value": "Vega Logistics",
                    "bbox": [0.08, 0.06, 0.55, 0.10],
                    "page": 0,
                    "confidence": 0.95,
                },
                "invoice_number": {
                    "value": "INV-2026-0042",
                    "bbox": [0.66, 0.13, 0.92, 0.16],
                    "page": 0,
                    "confidence": 0.97,
                },
                "invoice_date": {
                    "value": "2026-05-13",
                    "bbox": [0.66, 0.17, 0.92, 0.20],
                    "page": 0,
                    "confidence": 0.96,
                },
                "subtotal": {
                    "value": 1000.0,
                    "bbox": [0.70, 0.61, 0.92, 0.64],
                    "page": 0,
                    "confidence": 0.97,
                },
                "tax": {
                    "value": 180.0,
                    "bbox": [0.70, 0.65, 0.92, 0.68],
                    "page": 0,
                    "confidence": 0.97,
                },
                "total": {
                    "value": 1180.0,
                    "bbox": [0.70, 0.71, 0.92, 0.74],
                    "page": 0,
                    "confidence": 0.97,
                },
                "currency": {
                    "value": "USD",
                    "bbox": [0.62, 0.71, 0.69, 0.74],
                    "page": 0,
                    "confidence": 0.94,
                },
            },
            self_reported_confidence={"total": 0.97},
            extraction_failed=False,
            extraction_failure_reason=None,
            model="claude-sonnet-4-6",
            prompt_hash="vh",
            schema_hash="vh",
            usage={
                "input_tokens": 2000,
                "output_tokens": 120,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        )
        with patch_make_llm_client(vision=vision_result):
            result = extract_from_pdf(db_session, pdf_path=test_pdf)

        assert result.extraction.model == "claude-sonnet-4-6"
        assert result.extraction.predicted_triage_state == "confident"
        # Vision path stored per-field bboxes
        v = result.extraction.extracted_fields["vendor_name"]
        assert v["bbox"] == [0.08, 0.06, 0.55, 0.10]


class TestExtractFromPdfCascade:
    def test_low_haiku_confidence_triggers_sonnet(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        """When Haiku result hits the cascade trigger, Sonnet runs and
        agreement-score replaces the disputed field's confidence."""
        from app.adapters.llm_client import ExtractionResult

        test_pdf = tmp_path / "cascade.pdf"
        # Use unique bytes to avoid file_hash collision with other committed tests.
        test_pdf.write_bytes(CLEAN_PDF.read_bytes() + b"\n%cascade-unique\n")

        haiku_result = ExtractionResult(
            fields={
                "vendor_name": "Vega Logistics",
                "invoice_number": "INV-2026-0042",
                "invoice_date": "2026-05-13",
                "subtotal": 1000.0,
                "tax": 180.0,
                "total": 1181.0,  # math fails!
                "currency": "USD",
            },
            self_reported_confidence={"total": 0.85},
            extraction_failed=False,
            extraction_failure_reason=None,
            model="claude-haiku-4-5",
            prompt_hash="h",
            schema_hash="h",
            usage={
                "input_tokens": 500,
                "output_tokens": 80,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        )
        sonnet_result = ExtractionResult(
            fields={
                "vendor_name": "Vega Logistics",
                "invoice_number": "INV-2026-0042",
                "invoice_date": "2026-05-13",
                "subtotal": 1000.0,
                "tax": 180.0,
                "total": 1180.0,  # disagrees on total with haiku
                "currency": "USD",
            },
            self_reported_confidence={"total": 0.97},
            extraction_failed=False,
            extraction_failure_reason=None,
            model="claude-sonnet-4-6",
            prompt_hash="s",
            schema_hash="s",
            usage={
                "input_tokens": 500,
                "output_tokens": 80,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        )
        # total is a REQUIRED_FIELD that disputes between haiku and sonnet,
        # so the cascade escalates to Opus. Provide an Opus result that agrees
        # with Sonnet's value so the override is lifted.
        opus_result = ExtractionResult(
            fields={
                "vendor_name": "Vega Logistics",
                "invoice_number": "INV-2026-0042",
                "invoice_date": "2026-05-13",
                "subtotal": 1000.0,
                "tax": 180.0,
                "total": 1180.0,  # agrees with sonnet
                "currency": "USD",
            },
            self_reported_confidence={"total": 0.99},
            extraction_failed=False,
            extraction_failure_reason=None,
            model="claude-opus-4-7",
            prompt_hash="o",
            schema_hash="o",
            usage={
                "input_tokens": 800,
                "output_tokens": 80,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        )
        with patch_make_llm_client(
            header_seq=[haiku_result, sonnet_result, opus_result],
        ):
            result = extract_from_pdf(db_session, pdf_path=test_pdf)

        # Sonnet's (and Opus's) total wins; math now reconciles
        assert result.extraction.extracted_fields["total"]["value"] == 1180.0
        trace = result.extraction.cascade_trace
        assert len(trace["tiers"]) == 3
        assert trace["tiers"][0]["model"] == "claude-haiku-4-5"
        assert trace["tiers"][1]["model"] == "claude-sonnet-4-6"
        assert trace["tiers"][2]["model"] == "claude-opus-4-7"

    def test_sonnet_resolves_dispute_without_opus_escalation(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        """Cascade triggers (low confidence on a non-REQUIRED field), but
        Sonnet agrees with Haiku on every REQUIRED field. Opus must NOT fire."""
        from app.adapters.llm_client import ExtractionResult

        test_pdf = tmp_path / "cascade_2tier.pdf"
        # Unique bytes so file_hash differs from prior test runs
        test_pdf.write_bytes(CLEAN_PDF.read_bytes() + b"\n%cascade-2tier\n")

        # Haiku result with a math failure (triggers cascade) but matching values
        # on REQUIRED_FIELDS for both Haiku and Sonnet. Sonnet only disagrees
        # on `subtotal` (which is NOT in REQUIRED_FIELDS) — so Opus must not fire.
        haiku_result = ExtractionResult(
            fields={
                "vendor_name": "Vega Logistics",
                "invoice_number": "INV-2026-0042",
                "invoice_date": "2026-05-13",
                "subtotal": 1000.0,
                "tax": 180.0,
                "total": 1181.0,  # math fails (off $1)
                "currency": "USD",
            },
            self_reported_confidence={"total": 0.85},
            extraction_failed=False,
            extraction_failure_reason=None,
            model="claude-haiku-4-5",
            prompt_hash="h",
            schema_hash="h",
            usage={
                "input_tokens": 500,
                "output_tokens": 80,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        )
        # Sonnet: SAME values as Haiku for every REQUIRED_FIELD (vendor_name,
        # invoice_number, invoice_date, total, currency), only `subtotal` differs.
        # subtotal disagreement → cascade override on subtotal but NOT a
        # REQUIRED-field dispute → Opus does NOT fire.
        sonnet_result = ExtractionResult(
            fields={
                "vendor_name": "Vega Logistics",
                "invoice_number": "INV-2026-0042",
                "invoice_date": "2026-05-13",
                "subtotal": 1001.0,
                "tax": 180.0,
                "total": 1181.0,  # only subtotal differs
                "currency": "USD",
            },
            self_reported_confidence={"total": 0.95},
            extraction_failed=False,
            extraction_failure_reason=None,
            model="claude-sonnet-4-6",
            prompt_hash="s",
            schema_hash="s",
            usage={
                "input_tokens": 500,
                "output_tokens": 80,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        )
        with patch_make_llm_client(header_seq=[haiku_result, sonnet_result]):
            result = extract_from_pdf(db_session, pdf_path=test_pdf)

        # Cascade trace has exactly 2 tiers — Opus did not fire.
        trace = result.extraction.cascade_trace
        assert len(trace["tiers"]) == 2, (
            f"Expected 2 tiers (no Opus escalation), got {len(trace['tiers'])}: "
            f"{[t['model'] for t in trace['tiers']]}"
        )
        assert trace["tiers"][0]["model"] == "claude-haiku-4-5"
        assert trace["tiers"][1]["model"] == "claude-sonnet-4-6"


class TestExtractFromPdfDuplicate:
    def test_second_near_identical_upload_flags_duplicate(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        from app.adapters.llm_client import ExtractionResult

        # Use SCAN_PDF as the base: its rendered image (phash) is visually distinct
        # from CLEAN_PDF, so it won't collide with phashes committed by other tests.
        first = tmp_path / "dup-a.pdf"
        first.write_bytes(SCAN_PDF.read_bytes())
        second = tmp_path / "dup-b.pdf"
        # Different bytes (so file_hash differs) but same rendered image → phash matches.
        second.write_bytes(SCAN_PDF.read_bytes() + b"\n%dup-second-trailer\n")

        # Vision path: both PDFs have no embedded text.
        vision_good = ExtractionResult(
            fields={
                "vendor_name": {
                    "value": "Dup Vendor",
                    "bbox": [0.1, 0.05, 0.5, 0.09],
                    "page": 0,
                    "confidence": 0.95,
                },
                "invoice_number": {
                    "value": "INV-DUP-001",
                    "bbox": [0.6, 0.12, 0.9, 0.15],
                    "page": 0,
                    "confidence": 0.97,
                },
                "invoice_date": {
                    "value": "2026-05-13",
                    "bbox": [0.6, 0.16, 0.9, 0.19],
                    "page": 0,
                    "confidence": 0.96,
                },
                "subtotal": {
                    "value": 500.0,
                    "bbox": [0.7, 0.60, 0.9, 0.63],
                    "page": 0,
                    "confidence": 0.97,
                },
                "tax": {
                    "value": 90.0,
                    "bbox": [0.7, 0.64, 0.9, 0.67],
                    "page": 0,
                    "confidence": 0.97,
                },
                "total": {
                    "value": 590.0,
                    "bbox": [0.7, 0.70, 0.9, 0.73],
                    "page": 0,
                    "confidence": 0.97,
                },
                "currency": {
                    "value": "USD",
                    "bbox": [0.6, 0.70, 0.7, 0.73],
                    "page": 0,
                    "confidence": 0.94,
                },
            },
            self_reported_confidence={"total": 0.97},
            extraction_failed=False,
            extraction_failure_reason=None,
            model="claude-sonnet-4-6",
            prompt_hash="dv",
            schema_hash="dv",
            usage={
                "input_tokens": 2000,
                "output_tokens": 120,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        )
        with patch_make_llm_client(vision=vision_good):
            r1 = extract_from_pdf(db_session, pdf_path=first)
            r2 = extract_from_pdf(db_session, pdf_path=second)

        assert r1.invoice.id != r2.invoice.id
        assert r2.extraction.predicted_triage_state == "likely_duplicate"
        dup_reasons = [
            r for r in r2.extraction.predicted_triage_reasons if r["type"] == "duplicate_of"
        ]
        assert len(dup_reasons) == 1
        assert dup_reasons[0]["invoice_id"] == str(r1.invoice.id)


class TestExtractFromPdfLineItems:
    def test_line_items_returned_on_digital_path(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        test_pdf = tmp_path / "line-items.pdf"
        test_pdf.write_bytes(CLEAN_PDF.read_bytes() + b"\n%line-items-test\n")

        items = [
            {"description": "Freight", "quantity": 1, "unit_price": 1000.0, "line_total": 1000.0, "confidence": 0.95},
        ]
        line_items_result = LineItemsResult(
            items=items,
            model="claude-haiku-4-5",
            prompt_hash="h",
            schema_hash="h",
            usage={"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        )

        with patch_make_llm_client(header=_fake_llm_result(), line_items=line_items_result):
            result = extract_from_pdf(db_session, pdf_path=test_pdf)

        assert result.extraction.line_items == items

    def test_vision_path_skips_line_items_in_day3(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        """Vision branch returns no line items in Day 3 — vision line-item
        extraction is a Day 4+ stretch. The mock's line_items return value
        should NOT be observed because the service short-circuits."""
        test_pdf = tmp_path / "vision-no-lineitems.pdf"
        test_pdf.write_bytes(SCAN_PDF.read_bytes() + b"\n%vision-no-li\n")

        items = [{"description": "Should not be reached", "line_total": 1.0}]
        line_items_result = LineItemsResult(
            items=items, model="claude-sonnet-4-6", prompt_hash="x", schema_hash="x",
            usage={"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        )
        vision_result = ExtractionResult(
            fields={
                "vendor_name": {"value": "V", "bbox": [0.1, 0.1, 0.2, 0.2], "page": 0, "confidence": 0.9},
                "invoice_number": {"value": "X-1", "bbox": [0.1, 0.1, 0.2, 0.2], "page": 0, "confidence": 0.9},
                "invoice_date": {"value": "2026-01-01", "bbox": [0.1, 0.1, 0.2, 0.2], "page": 0, "confidence": 0.9},
                "subtotal": {"value": 100.0, "bbox": [0.1, 0.1, 0.2, 0.2], "page": 0, "confidence": 0.9},
                "tax": {"value": 18.0, "bbox": [0.1, 0.1, 0.2, 0.2], "page": 0, "confidence": 0.9},
                "total": {"value": 118.0, "bbox": [0.1, 0.1, 0.2, 0.2], "page": 0, "confidence": 0.9},
                "currency": {"value": "USD", "bbox": [0.1, 0.1, 0.2, 0.2], "page": 0, "confidence": 0.9},
            },
            self_reported_confidence={"total": 0.9},
            extraction_failed=False, extraction_failure_reason=None,
            model="claude-sonnet-4-6", prompt_hash="vh", schema_hash="vh",
            usage={"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        )
        with patch_make_llm_client(vision=vision_result, line_items=line_items_result):
            result = extract_from_pdf(db_session, pdf_path=test_pdf)

        assert result.extraction.line_items == []  # vision short-circuits
