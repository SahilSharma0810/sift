"""Digital-path PDF reader per ADR-0001.

PyMuPDF (`fitz`) extracts text and per-word bounding boxes. The vision path
(`pdf2image` + Claude Sonnet) lives in a sibling adapter, added Day 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF


@dataclass(frozen=True, slots=True)
class WordBox:
    text: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1
    page: int


@dataclass(frozen=True, slots=True)
class DigitalRead:
    full_text: str
    words: tuple[WordBox, ...]
    page_count: int


def has_text(pdf_path: Path) -> bool:
    """True if the PDF has any extractable text on any page.

    Used by extraction_service for path selection: text path vs vision path.
    """
    with fitz.open(pdf_path) as doc:
        for page in doc:
            if page.get_text("text").strip():
                return True
    return False


def read_digital(pdf_path: Path) -> DigitalRead:
    """Extract full text + per-word bboxes from a digital PDF.

    Each word entry is `(x0, y0, x1, y1, text, block_no, line_no, word_no)` —
    we keep just the text + bbox + page index for downstream consumption.
    """
    words: list[WordBox] = []
    full_text_chunks: list[str] = []

    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc):
            full_text_chunks.append(page.get_text("text"))
            for w in page.get_text("words"):
                x0, y0, x1, y1, text, *_ = w
                if text.strip():
                    words.append(
                        WordBox(
                            text=text,
                            bbox=(float(x0), float(y0), float(x1), float(y1)),
                            page=page_index,
                        )
                    )
        page_count = len(doc)

    return DigitalRead(
        full_text="\n".join(full_text_chunks),
        words=tuple(words),
        page_count=page_count,
    )
