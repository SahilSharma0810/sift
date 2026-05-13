"""PDF reader integration test — real PyMuPDF, real fixture PDF.

The adapter has two responsibilities:
1. has_text() — branch logic for path selection per ADR-0001
2. read_digital() — returns text + per-word bboxes for the digital path
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.pdf_reader import has_text, read_digital

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


def test_has_text_on_image_only(tmp_path: Path) -> None:
    """Branch logic for path selection — image-only PDF must return False."""
    import fitz

    doc = fitz.open()
    doc.new_page()  # blank page, no text layer
    out = tmp_path / "blank.pdf"
    doc.save(str(out))
    doc.close()
    assert has_text(out) is False
