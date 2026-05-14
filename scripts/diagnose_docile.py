#!/usr/bin/env python3
"""Diagnose specific DocILE failures by showing the LLM's view + cascade trace.

For each invoice you specify, prints:
- The first ~1500 chars of PDF text the LLM saw
- Ground truth from DocILE annotation
- What the system extracted
- The cascade trace (which tiers fired, their self-reported confidence)
- A side-by-side diff of right vs wrong fields

Runs on the host, uses the live backend. No API calls, no cost — pulls
existing extractions from the DB via /api/invoices/<id>.

Usage:
  uv run --with httpx python scripts/diagnose_docile.py
  uv run --with httpx python scripts/diagnose_docile.py --doc-id 450aa854ecb548ba956d5707
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

DOCILE_ROOT = Path("/Users/lscypher/Workspace/docile/data/docile")
BASE_URL = "http://localhost:8000"

# Same mapping the smoke script uses
DOCILE_TO_SIFT = {
    "vendor_name": "vendor_name",
    "document_id": "invoice_number",
    "date_issue": "invoice_date",
    "amount_total_gross": "total",
    "amount_total_base": "subtotal",
    "amount_total_tax": "tax",
    "currency_code_amount_due": "currency",
}


def _load_groundtruth(doc_id: str) -> dict[str, str]:
    ann = json.loads((DOCILE_ROOT / "annotations" / f"{doc_id}.json").read_text())
    fields: dict[str, str] = {}
    for fe in ann.get("field_extractions", []):
        ft = fe.get("fieldtype")
        if ft in DOCILE_TO_SIFT:
            fields.setdefault(DOCILE_TO_SIFT[ft], fe.get("text", ""))
    return fields


def _extract_pdf_text(doc_id: str, max_chars: int = 2000) -> str:
    """Pull text from the DocILE OCR (much faster than re-running PyMuPDF)."""
    ocr_path = DOCILE_ROOT / "ocr" / f"{doc_id}.json"
    if not ocr_path.exists():
        return f"[no ocr file: {ocr_path}]"
    ocr = json.loads(ocr_path.read_text())
    chunks: list[str] = []
    # DocILE OCR JSON shape: { "pages": [ { "blocks": [ {"text": ...} ] } ] }
    for page in ocr.get("pages", []):
        for block in page.get("blocks", []):
            t = block.get("text") or ""
            if t.strip():
                chunks.append(t.strip())
    joined = " ".join(chunks)
    return joined[:max_chars] + ("..." if len(joined) > max_chars else "")


def _find_invoice_by_file_hash(file_hash: str) -> dict[str, Any] | None:
    """Look up an invoice by file hash in the inbox list."""
    all_inv = httpx.get(f"{BASE_URL}/api/invoices", timeout=10).json()
    for inv in all_inv:
        if inv.get("file_hash") == file_hash:
            return inv
    return None


def _file_hash_for_pdf(doc_id: str) -> str:
    """Compute SHA-256 of the DocILE PDF — same hash the backend uses for dedup."""
    import hashlib

    pdf = DOCILE_ROOT / "pdfs" / f"{doc_id}.pdf"
    return hashlib.sha256(pdf.read_bytes()).hexdigest()


def _print_invoice_diag(doc_id: str) -> None:
    print("=" * 78)
    print(f"DOC ID: {doc_id}")
    print("=" * 78)

    file_hash = _file_hash_for_pdf(doc_id)
    print(f"file_hash: {file_hash[:16]}...")

    inv = _find_invoice_by_file_hash(file_hash)
    if not inv:
        print(f"NOT FOUND in /api/invoices — has the smoke test run on this doc?")
        return

    ext = inv.get("current_extraction") or {}
    fields = ext.get("extracted_fields") or {}
    cascade = ext.get("cascade_trace") or {}
    confidence = ext.get("confidence_per_field") or {}
    reasons = ext.get("predicted_triage_reasons") or []
    triage = ext.get("predicted_triage_state", "?")

    gt = _load_groundtruth(doc_id)

    print(f"\n--- PDF text (first 1500 chars) ---")
    print(_extract_pdf_text(doc_id, max_chars=1500))

    print(f"\n--- Ground truth (DocILE annotation) ---")
    for k, v in gt.items():
        print(f"  {k:<18} {v!r}")

    print(f"\n--- Extracted ---")
    for k in ("vendor_name", "invoice_number", "invoice_date", "subtotal", "tax", "total", "currency"):
        if k in fields and fields[k]:
            f = fields[k]
            v = f.get("value") if isinstance(f, dict) else f
            conf = confidence.get(k, "?")
            source = f.get("source", "?") if isinstance(f, dict) else "?"
            print(f"  {k:<18} {v!r:<40} conf={conf} source={source}")

    print(f"\n--- Triage ---")
    print(f"  state: {triage}")
    if reasons:
        for r in reasons:
            print(f"  reason: {r}")

    print(f"\n--- Cascade trace ---")
    for i, tier in enumerate(cascade.get("tiers", []), start=1):
        model = tier.get("model", "?")
        usage = tier.get("usage", {})
        self_conf = tier.get("llm_self_confidence", {})
        print(f"  Tier {i}: {model}")
        if usage:
            print(f"    tokens: in={usage.get('input_tokens')} out={usage.get('output_tokens')}")
        if self_conf:
            print(f"    LLM self-confidence per field:")
            for fk, fv in self_conf.items():
                print(f"      {fk:<18} {fv}")

    print(f"\n--- Diff vs ground truth ---")
    for sift_field, gt_text in gt.items():
        f = fields.get(sift_field) if fields else None
        actual = f.get("value") if isinstance(f, dict) else f
        actual_s = str(actual).strip() if actual is not None else "—"
        match_marker = "✓" if (actual_s and gt_text.strip().lower() in actual_s.lower() or actual_s.lower() in gt_text.lower()) else "✗"
        print(f"  {match_marker} {sift_field:<18} gt={gt_text!r}")
        print(f"    {'':<18}   got={actual_s!r}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--doc-id",
        action="append",
        help="Specific doc IDs to diagnose. Defaults to the 3 known failures.",
    )
    args = p.parse_args()

    failing = [
        "450aa854ecb548ba956d5707",  # vendor + date errors
        "04345516ddca4de2a96a22b5",  # total error
    ]
    doc_ids = args.doc_id or failing

    for doc_id in doc_ids:
        _print_invoice_diag(doc_id)
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
