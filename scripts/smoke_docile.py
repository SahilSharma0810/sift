#!/usr/bin/env python3
"""Smoke-test Sift's extraction against real DocILE invoices.

Runs on the HOST (not inside the backend container) and hits the live
backend at http://localhost:8000. Picks N random invoices from the DocILE
val split, uploads each via /api/invoices, and diffs the extracted fields
against the DocILE ground-truth annotations.

Requires:
  - Backend running in anthropic mode (set SIFT_LLM_PROVIDER=anthropic +
    ANTHROPIC_API_KEY in .env and `docker compose restart backend`)
  - DocILE dataset at /Users/lscypher/Workspace/docile/data/docile (or
    override with --docile-root)

Usage:
  uv run --with httpx --with rich python scripts/smoke_docile.py
  uv run --with httpx --with rich python scripts/smoke_docile.py --n 5 --seed 42
  uv run --with httpx --with rich python scripts/smoke_docile.py --doc 00134dd3...

This is a SMOKE test, not the full eval. Catches obvious breakage (schema
errors, wrong fields, missing fields, blatantly wrong values) before
running the 500-invoice eval.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

DOCILE_TO_SIFT: dict[str, str] = {
    "vendor_name": "vendor_name",
    "document_id": "invoice_number",
    "date_issue": "invoice_date",
    "amount_total_gross": "total",
    "amount_total_base": "subtotal",
    "amount_total_tax": "tax",
    "currency_code_amount_due": "currency",
}

PRICING_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-haiku-4-5":   {"input": 1.00,  "output": 5.00,  "cache_write": 1.25,  "cache_read": 0.10},
    "claude-sonnet-4-6":  {"input": 3.00,  "output": 15.00, "cache_write": 3.75,  "cache_read": 0.30},
    "claude-opus-4-7":    {"input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50},
}

def _model_key(model_id: str) -> str:
    for k in PRICING_PER_MTOK:
        if model_id.startswith(k):
            return k
    return model_id

def _tier_cost_usd(model_id: str, usage: dict[str, int]) -> float:
    p = PRICING_PER_MTOK.get(_model_key(model_id))
    if p is None:
        return 0.0
    return (
        usage.get("input_tokens", 0) * p["input"]
        + usage.get("output_tokens", 0) * p["output"]
        + usage.get("cache_creation_input_tokens", 0) * p["cache_write"]
        + usage.get("cache_read_input_tokens", 0) * p["cache_read"]
    ) / 1_000_000

@dataclass
class GroundTruth:
    doc_id: str
    fields: dict[str, str]

def _load_ground_truth(docile_root: Path, doc_id: str) -> GroundTruth:
    """Parse a DocILE annotation JSON into Sift-shape ground truth.

    DocILE annotations have a `field_extractions` array of typed boxes.
    We keep only the field types Sift extracts; the rest stay annotated
    in DocILE but aren't Sift's surface.
    """
    ann_path = docile_root / "annotations" / f"{doc_id}.json"
    raw = json.loads(ann_path.read_text())
    fields: dict[str, str] = {}
    for fe in raw.get("field_extractions", []):
        ft = fe.get("fieldtype")
        if ft in DOCILE_TO_SIFT:
            sift_field = DOCILE_TO_SIFT[ft]

            fields.setdefault(sift_field, fe.get("text", ""))
    return GroundTruth(doc_id=doc_id, fields=fields)

def _post_invoice(client: httpx.Client, pdf_path: Path) -> dict[str, Any]:
    with pdf_path.open("rb") as fh:
        r = client.post(
            "/api/invoices",
            files={"file": (pdf_path.name, fh, "application/pdf")},
            timeout=180.0,
        )
    if r.status_code >= 400:
        raise RuntimeError(f"upload failed for {pdf_path.name}: {r.status_code} {r.text[:200]}")
    return r.json()


def _login(client: httpx.Client, *, email: str, password: str) -> None:
    r = client.post(
        "/api/auth/login",
        json={"email": email, "password": password, "remember": False},
        timeout=15.0,
    )
    if r.status_code != 200:
        raise RuntimeError(f"login failed: {r.status_code} {r.text[:200]}")

def _extracted_value(invoice_json: dict[str, Any], field: str) -> Any:
    ext = invoice_json.get("current_extraction") or {}
    fields = ext.get("extracted_fields") or {}
    f = fields.get(field)
    return f.get("value") if isinstance(f, dict) else None

def _numeric_close(a: Any, b: Any, tol_frac: float = 0.01) -> bool:
    try:
        fa = float(a)
        fb = float(b)
        if fa == 0 and fb == 0:
            return True
        return abs(fa - fb) / max(abs(fa), abs(fb), 1.0) <= tol_frac
    except (TypeError, ValueError):
        return False

_AMOUNT_STRIP_RE = re.compile(r"[,$£€¥₹\s]|USD|EUR|GBP|INR|JPY|US\$|CAD|AUD")
_AMOUNT_TRAIL_RE = re.compile(r"[.\-−–—\s]+$")
_DATE_NORMALIZE_RE = re.compile(r"[\s/\-.l|]+")

def _normalize_date(s: str) -> str:
    """Collapse all common separators (/ - . space l |) to '/' for date comparison."""
    return _DATE_NORMALIZE_RE.sub("/", s.strip()).strip("/")

def _clean_amount_str(s: str) -> str:
    """Strip currency tokens, thousands separators, and trailing dash/dot from a number string."""
    cleaned = _AMOUNT_STRIP_RE.sub("", s)
    cleaned = _AMOUNT_TRAIL_RE.sub("", cleaned)
    return cleaned

def _compare_field(field: str, gt_text: str, actual: Any) -> tuple[bool, str]:
    """Return (match, note). Soft comparisons per field type."""
    if actual is None:
        return False, "missing"

    actual_s = str(actual).strip()
    gt_s = str(gt_text).strip()

    if field in ("subtotal", "tax", "total"):
        gt_n = _clean_amount_str(gt_s)
        actual_n = _clean_amount_str(actual_s)
        try:
            return _numeric_close(float(gt_n), float(actual_n)), f"gt={gt_n!r} got={actual_n!r}"
        except ValueError:
            return False, f"bad-number gt={gt_s!r} got={actual_s!r}"

    if field == "currency":
        _SYMBOL_TO_ISO = {
            "$": "USD", "US$": "USD", "C$": "CAD", "CA$": "CAD", "A$": "AUD", "AU$": "AUD",
            "€": "EUR", "£": "GBP", "₹": "INR", "¥": "JPY",
        }
        gt_norm = _SYMBOL_TO_ISO.get(gt_s, gt_s.upper())
        return actual_s.upper() == gt_norm, f"gt={gt_s!r}→{gt_norm!r} got={actual_s!r}"

    if field == "invoice_date":
        gt_norm = _normalize_date(gt_s)
        actual_norm = _normalize_date(actual_s)
        match = (
            actual_norm == gt_norm
            or actual_norm in gt_norm
            or gt_norm in actual_norm
        )
        return match, f"gt={gt_s!r} got={actual_s!r}"

    a_lower = actual_s.lower()
    g_lower = gt_s.lower()
    match = a_lower == g_lower or a_lower in g_lower or g_lower in a_lower
    return match, f"gt={gt_s!r} got={actual_s!r}"

def _print(line: str = "") -> None:
    print(line, flush=True)

def _try_rich():
    try:
        from rich.console import Console
        from rich.table import Table

        return Console(), Table
    except ImportError:
        return None, None

def _run(
    *,
    docile_root: Path,
    base_url: str,
    doc_ids: list[str],
    email: str,
    password: str,
) -> dict[str, Any]:
    console, RichTable = _try_rich()

    total_attempts = 0
    total_correct = 0
    per_field = {sift: {"ok": 0, "total": 0} for sift in DOCILE_TO_SIFT.values()}
    failures: list[dict[str, Any]] = []
    cascade_tiers: list[int] = []
    per_model_totals: dict[str, dict[str, int]] = {}
    total_cost_usd = 0.0

    with httpx.Client(base_url=base_url) as client:
        _login(client, email=email, password=password)

        for doc_id in doc_ids:
            pdf = docile_root / "pdfs" / f"{doc_id}.pdf"
            if not pdf.exists():
                _print(f"[skip] {doc_id}: PDF missing")
                continue

            gt = _load_ground_truth(docile_root, doc_id)
            if not gt.fields:
                _print(f"[skip] {doc_id}: no Sift-relevant fields in annotation")
                continue

            _print(f"\n── {doc_id} ──")
            _print(f"  PDF: {pdf.name}  ({pdf.stat().st_size // 1024} KB)")
            t0 = time.time()
            try:
                resp = _post_invoice(client, pdf)
            except Exception as exc:
                _print(f"  [ERROR] upload failed: {exc}")
                failures.append({"doc_id": doc_id, "error": str(exc)})
                continue
            elapsed = time.time() - t0

            ext = resp.get("current_extraction") or {}
            cascade = ext.get("cascade_trace") or {}
            tiers_list = cascade.get("tiers", []) or []
            n_tiers = len(tiers_list)
            cascade_tiers.append(n_tiers)
            triage = ext.get("predicted_triage_state", "—")

            invoice_cost = 0.0
            for t in tiers_list:
                model = t.get("model", "unknown")
                usage = t.get("usage") or {}
                invoice_cost += _tier_cost_usd(model, usage)
                bucket = per_model_totals.setdefault(
                    _model_key(model),
                    {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "calls": 0},
                )
                for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
                    bucket[k] += usage.get(k, 0)
                bucket["calls"] += 1
            total_cost_usd += invoice_cost

            _print(f"  Pipeline: {elapsed:.1f}s · cascade={n_tiers} tier(s) · triage={triage} · ${invoice_cost:.4f}")

            rows: list[tuple[str, str, bool]] = []
            for sift_field, gt_text in gt.fields.items():
                actual = _extracted_value(resp, sift_field)
                match, note = _compare_field(sift_field, gt_text, actual)
                rows.append((sift_field, note, match))
                per_field[sift_field]["total"] += 1
                if match:
                    per_field[sift_field]["ok"] += 1
                total_attempts += 1
                if match:
                    total_correct += 1

            if console and RichTable:
                tbl = RichTable(show_header=True, header_style="bold")
                tbl.add_column("field")
                tbl.add_column("match")
                tbl.add_column("detail")
                for field, note, match in rows:
                    tbl.add_row(field, "✓" if match else "✗", note)
                console.print(tbl)
            else:
                for field, note, match in rows:
                    mark = "✓" if match else "✗"
                    _print(f"  {mark} {field:<16} {note}")

            if any(not m for _, _, m in rows):
                failures.append({
                    "doc_id": doc_id,
                    "mismatches": [(f, n) for f, n, m in rows if not m],
                })

    _print("\n" + "=" * 60)
    _print("Summary")
    _print("=" * 60)
    _print(f"Overall: {total_correct}/{total_attempts} field-comparisons matched ({total_correct/max(total_attempts,1):.1%})")
    if cascade_tiers:
        _print(f"Cascade depth: avg {sum(cascade_tiers)/len(cascade_tiers):.1f} tiers, max {max(cascade_tiers)}")
    _print("")
    _print("Per-field accuracy:")
    for field, counts in per_field.items():
        if counts["total"] == 0:
            continue
        rate = counts["ok"] / counts["total"]
        _print(f"  {field:<16} {counts['ok']:>3}/{counts['total']:<3}  {rate:.1%}")
    if failures:
        _print(f"\n{len(failures)} invoice(s) had at least one mismatch.")

    n_invoices = len(cascade_tiers)
    if n_invoices:
        _print("")
        _print("Cost breakdown (per Anthropic public pricing):")
        for model, u in sorted(per_model_totals.items()):
            cost = _tier_cost_usd(model, u)
            _print(
                f"  {model:<22} calls={u['calls']:>3}  "
                f"in={u['input_tokens']:>8,}  out={u['output_tokens']:>6,}  "
                f"cache_w={u['cache_creation_input_tokens']:>7,}  cache_r={u['cache_read_input_tokens']:>8,}  "
                f"${cost:.4f}"
            )
        _print(f"  Total: ${total_cost_usd:.4f}  (avg ${total_cost_usd / n_invoices:.4f}/invoice over {n_invoices} invoice(s))")
    return {
        "total_correct": total_correct,
        "total_attempts": total_attempts,
        "per_field": per_field,
        "failures": failures,
        "total_cost_usd": round(total_cost_usd, 6),
        "per_model_totals": per_model_totals,
    }

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--docile-root",
        default="/Users/lscypher/Workspace/docile/data/docile",
        help="Path to DocILE data root (contains pdfs/, annotations/, val.json)",
    )
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--n", type=int, default=10, help="number of invoices to test")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--split",
        default="val",
        choices=["val", "train", "trainval"],
        help="DocILE split to draw from",
    )
    p.add_argument("--doc", action="append", help="explicit doc_id(s) (overrides --n)")
    p.add_argument(
        "--email",
        default="ap-clerk@sift.demo",
        help="login email (must already exist; run seed_demo_user or make seed-demo first)",
    )
    p.add_argument("--password", default="letmein-demo", help="login password")
    args = p.parse_args()

    root = Path(args.docile_root)
    if not (root / "pdfs").is_dir():
        _print(f"ERROR: {root}/pdfs not found")
        return 1

    try:
        meta = httpx.get(f"{args.base_url}/api/meta", timeout=3.0).json()
    except Exception as e:
        _print(f"ERROR: can't reach backend at {args.base_url} ({e})")
        return 1
    _print(f"Backend: version={meta.get('version')} llm_provider={meta.get('llm_provider')}")
    if meta.get("llm_provider") != "anthropic":
        _print("WARN: backend is not in anthropic mode — extraction will be stub data.")
        _print("      set SIFT_LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY in .env and")
        _print("      `docker compose restart backend` before running this script.")

    if args.doc:
        doc_ids = args.doc
    else:
        split_path = root / f"{args.split}.json"
        all_ids = json.loads(split_path.read_text())
        rng = random.Random(args.seed)
        doc_ids = rng.sample(all_ids, k=min(args.n, len(all_ids)))

    _print(f"Testing {len(doc_ids)} invoice(s) from {args.split} split (seed={args.seed})")
    summary = _run(
        docile_root=root,
        base_url=args.base_url,
        doc_ids=doc_ids,
        email=args.email,
        password=args.password,
    )
    return 0 if summary["total_correct"] == summary["total_attempts"] else 0

if __name__ == "__main__":
    sys.exit(main())
