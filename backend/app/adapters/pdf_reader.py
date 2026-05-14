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


def resolve_bboxes(
    *,
    words: list[WordBox] | tuple[WordBox, ...],
    page_count: int,
    extracted: dict[str, object],
) -> dict[str, tuple[float, float, float, float]]:
    """Fuzzy-match extracted string values against the word stream.

    Returns a dict from field-name → normalized 0-1 bbox per page. The bbox is
    the bounding rectangle of the matched word(s). Multi-word values are
    matched by the longest contiguous sub-sequence of word tokens.
    """
    if not words or page_count <= 0:
        return {}

    # Build a per-page word list and a page-size map (max coords).
    page_words: dict[int, list[WordBox]] = {}
    page_dims: dict[int, tuple[float, float]] = {}
    for w in words:
        page_words.setdefault(w.page, []).append(w)
        cx, cy = page_dims.get(w.page, (0.0, 0.0))
        page_dims[w.page] = (max(cx, w.bbox[2]), max(cy, w.bbox[3]))

    out: dict[str, tuple[float, float, float, float]] = {}
    for field, raw_value in extracted.items():
        if raw_value is None or raw_value == "":
            continue
        target_tokens = str(raw_value).split()
        if not target_tokens:
            continue
        match = _find_token_run(page_words, target_tokens)
        if not match:
            continue
        page_idx, matched = match
        dim = page_dims.get(page_idx)
        if not dim or dim[0] <= 0 or dim[1] <= 0:
            continue
        x0 = min(w.bbox[0] for w in matched) / dim[0]
        y0 = min(w.bbox[1] for w in matched) / dim[1]
        x1 = max(w.bbox[2] for w in matched) / dim[0]
        y1 = max(w.bbox[3] for w in matched) / dim[1]
        # Clamp to [0, 1] as a safety net against rounding drift.
        out[field] = (
            max(0.0, min(1.0, x0)),
            max(0.0, min(1.0, y0)),
            max(0.0, min(1.0, x1)),
            max(0.0, min(1.0, y1)),
        )
    return out


def _find_token_run(
    page_words: dict[int, list[WordBox]],
    target: list[str],
) -> tuple[int, list[WordBox]] | None:
    """Find the first run of consecutive words whose lowercased texts match `target`.

    Returns (page_index, matched_words). Match is case-insensitive and
    ignores trailing punctuation on each token.
    """
    norm_target = [_normalize_token(t) for t in target]
    for page_idx in sorted(page_words.keys()):
        plist = page_words[page_idx]
        norm = [_normalize_token(w.text) for w in plist]
        for i in range(len(norm) - len(norm_target) + 1):
            if norm[i : i + len(norm_target)] == norm_target:
                return page_idx, plist[i : i + len(norm_target)]
    return None


def _normalize_token(s: str) -> str:
    return s.strip().rstrip(".,:;").lower()
