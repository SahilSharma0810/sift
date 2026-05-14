"""PDF reader integration test — real PyMuPDF, real fixture PDF.

The adapter has two responsibilities:
1. has_text() — branch logic for path selection per ADR-0001
2. read_digital() — returns text + per-word bboxes for the digital path
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.pdf_reader import (
    compute_perceptual_hash,
    has_text,
    read_digital,
    render_page_pngs,
    resolve_bboxes,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"
CLEAN_PDF = FIXTURES / "digital_invoice_clean.pdf"


@pytest.mark.skipif(not CLEAN_PDF.exists(), reason="run generate_clean.py first")
class TestPdfReader:
    def test_has_text_on_digital(self) -> None:
        assert has_text(CLEAN_PDF) is True

    def test_read_digital_returns_text(self) -> None:
        result = read_digital(CLEAN_PDF)
        assert "Vega Logistics" in result.full_text
        assert "INV-2026-0042" in result.full_text
        assert "1,180.00" in result.full_text or "1180.00" in result.full_text
        assert result.page_count == 1

    def test_read_digital_returns_word_boxes(self) -> None:
        result = read_digital(CLEAN_PDF)
        # At least one word box for "Vega"
        vega_boxes = [w for w in result.words if w.text == "Vega"]
        assert len(vega_boxes) >= 1
        box = vega_boxes[0]
        assert box.bbox[0] < box.bbox[2]  # x0 < x1
        assert box.bbox[1] < box.bbox[3]  # y0 < y1
        assert box.page == 0


@pytest.mark.skipif(not CLEAN_PDF.exists(), reason="run generate_clean.py first")
class TestResolveBboxes:
    def test_finds_vendor_name(self) -> None:
        result = read_digital(CLEAN_PDF)
        bboxes = resolve_bboxes(
            words=result.words,
            page_count=result.page_count,
            extracted={"vendor_name": "Vega Logistics"},
        )
        assert "vendor_name" in bboxes
        x0, y0, x1, y1 = bboxes["vendor_name"]
        # Normalized 0-1
        assert 0.0 <= x0 < x1 <= 1.0
        assert 0.0 <= y0 < y1 <= 1.0

    def test_returns_empty_for_unmatched_value(self) -> None:
        result = read_digital(CLEAN_PDF)
        bboxes = resolve_bboxes(
            words=result.words,
            page_count=result.page_count,
            extracted={"vendor_name": "Not In Document"},
        )
        assert "vendor_name" not in bboxes

    def test_handles_multi_word_value(self) -> None:
        result = read_digital(CLEAN_PDF)
        bboxes = resolve_bboxes(
            words=result.words,
            page_count=result.page_count,
            extracted={"vendor_name": "Vega Logistics", "invoice_number": "INV-2026-0042"},
        )
        # Both fields should resolve
        assert "vendor_name" in bboxes
        assert "invoice_number" in bboxes


def test_has_text_on_image_only(tmp_path: Path) -> None:
    """Branch logic for path selection — image-only PDF must return False."""
    import fitz

    doc = fitz.open()
    doc.new_page()  # blank page, no text layer
    out = tmp_path / "blank.pdf"
    doc.save(str(out))
    doc.close()
    assert has_text(out) is False


@pytest.mark.skipif(not CLEAN_PDF.exists(), reason="run generate_clean.py first")
class TestPerceptualHash:
    def test_returns_16_hex_chars(self) -> None:
        h = compute_perceptual_hash(CLEAN_PDF)
        assert isinstance(h, str)
        assert len(h) == 16
        int(h, 16)  # parses as hex

    def test_same_pdf_same_hash(self) -> None:
        assert compute_perceptual_hash(CLEAN_PDF) == compute_perceptual_hash(CLEAN_PDF)


@pytest.mark.skipif(not CLEAN_PDF.exists(), reason="run generate_clean.py first")
class TestRenderPagePngs:
    def test_renders_at_least_one_page(self, tmp_path) -> None:
        pages = render_page_pngs(CLEAN_PDF, scale=1.2)
        assert len(pages) >= 1
        # Each entry is raw PNG bytes
        assert pages[0][:8] == b"\x89PNG\r\n\x1a\n"
