"""Extraction accuracy eval.

Reads `eval/groundtruth.json` (produced by seed_eval.py), pulls each
invoice's current extraction from the DB, and compares the extracted
header fields + triage state + triage reason types against ground truth.

Output:
- per-field exact-match accuracy
- per-triage-state confusion matrix
- per-reason-type recall
- top-N error examples
- calibration buckets (composite confidence vs ground-truth correctness)

Writes a Markdown report to `/data/uploads/eval/extraction.md` plus a
calibration PNG to `/data/uploads/eval/calibration.png`.

Run from inside the backend container:
    docker compose exec backend uv run python -m scripts.eval_extraction
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from app.db.session import SessionLocal
from app.services.invoice_queries import get_invoice_dto

log = logging.getLogger("eval_extraction")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")

@dataclass(slots=True)
class CaseResult:
    label: str
    vendor_ok: bool
    total_ok: bool
    triage_ok: bool
    reasons_ok: bool
    expected_triage: str
    actual_triage: str
    expected_reasons: set[str]
    actual_reasons: set[str]
    confidence_min: float

def _load_groundtruth() -> list[dict[str, Any]]:
    gt_path = Path("eval") / "groundtruth.json"
    if not gt_path.exists():
        raise FileNotFoundError(
            f"{gt_path} missing — run `make seed-eval` first to populate the eval corpus."
        )
    return json.loads(gt_path.read_text())

def _field_value(extraction_fields: Any, name: str) -> Any:
    """Read a value from extracted_fields, tolerating both Pydantic models and dicts."""
    if not extraction_fields:
        return None
    if hasattr(extraction_fields, "get"):
        fd = extraction_fields.get(name)
    else:
        return None
    if fd is None:
        return None
    if hasattr(fd, "value"):
        return fd.value
    if isinstance(fd, dict):
        return fd.get("value")
    return None

def _min_field_confidence(extraction: Any) -> float:
    if extraction is None:
        return 0.0
    cpf = getattr(extraction, "confidence_per_field", None) or {}
    if not cpf:
        return 0.0
    return min(cpf.values())

def _evaluate(record: dict, dto: Any) -> CaseResult:
    case = record["case"]
    expected_vendor = case["expected_vendor"]
    expected_total = float(case["expected_total"])
    expected_triage = case["expected_triage_state"]
    expected_reasons = set(case["expected_reason_types"])

    ext = dto.current_extraction if dto else None
    fields = ext.extracted_fields if ext else {}
    actual_vendor = _field_value(fields, "vendor_name")
    actual_total = _field_value(fields, "total")
    actual_triage = ext.predicted_triage_state if ext else "unknown"
    actual_reasons = {r.type for r in ext.predicted_triage_reasons} if ext else set()

    vendor_ok = actual_vendor == expected_vendor or (
        case.get("unprocessable") and actual_vendor in ("Unknown", None)
    )

    if case.get("unprocessable"):
        total_ok = actual_total in (None, 0, 0.0)
    else:
        total_ok = actual_total is not None and abs(float(actual_total) - expected_total) <= 0.50

    triage_ok = actual_triage == expected_triage

    reasons_ok = expected_reasons.issubset(actual_reasons)

    return CaseResult(
        label=case["label"],
        vendor_ok=vendor_ok,
        total_ok=total_ok,
        triage_ok=triage_ok,
        reasons_ok=reasons_ok,
        expected_triage=expected_triage,
        actual_triage=actual_triage,
        expected_reasons=expected_reasons,
        actual_reasons=actual_reasons,
        confidence_min=_min_field_confidence(ext),
    )

def _write_calibration_png(results: list[CaseResult], out_path: Path) -> None:
    """10-bucket calibration plot: x = confidence bucket, y = correctness rate."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        log.warning("matplotlib not installed — skipping calibration PNG.")
        return

    buckets: dict[int, list[bool]] = defaultdict(list)
    for r in results:

        if r.expected_triage == "needs_review" and "extraction_failed" in r.expected_reasons:
            continue
        idx = min(int(r.confidence_min * 10), 9)

        correct = r.triage_ok and r.reasons_ok and r.vendor_ok and r.total_ok
        buckets[idx].append(correct)

    xs: list[float] = []
    ys: list[float] = []
    ys_perfect: list[float] = []
    for i in range(10):
        ys_perfect.append((i + 0.5) / 10.0)
        if buckets[i]:
            xs.append((i + 0.5) / 10.0)
            ys.append(sum(buckets[i]) / len(buckets[i]))

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot([0, 1], [0, 1], "--", color="#888", label="perfect calibration")
    ax.plot(xs, ys, "o-", color="#2c6ec7", label="composite confidence")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("composite confidence (min over header fields)")
    ax.set_ylabel("ground-truth correctness rate")
    ax.set_title("Sift extraction calibration")
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    log.info("calibration plot written to %s", out_path)

def _write_report(results: list[CaseResult], out_path: Path) -> None:
    total = len(results)
    field_acc = {
        "vendor_name": sum(r.vendor_ok for r in results) / total,
        "total": sum(r.total_ok for r in results) / total,
    }
    triage_acc = sum(r.triage_ok for r in results) / total
    reason_recall = sum(r.reasons_ok for r in results) / total

    by_state: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        by_state[r.expected_triage].append(r)

    confusion: dict[tuple[str, str], int] = defaultdict(int)
    for r in results:
        confusion[(r.expected_triage, r.actual_triage)] += 1

    errors = [
        r for r in results if not (r.triage_ok and r.reasons_ok and r.vendor_ok and r.total_ok)
    ]

    lines: list[str] = []
    lines.append("# Sift extraction eval\n")
    lines.append(f"Corpus size: **{total}** invoices (synthetic).\n")
    lines.append("## Headline numbers\n")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| vendor_name exact-match | **{field_acc['vendor_name']:.1%}** |")
    lines.append(f"| total exact-match (±$0.50) | **{field_acc['total']:.1%}** |")
    lines.append(f"| triage_state exact-match | **{triage_acc:.1%}** |")
    lines.append(f"| expected reasons recall | **{reason_recall:.1%}** |")
    lines.append("")

    lines.append("## Per-triage-state accuracy\n")
    lines.append("| expected state | n | triage matched | reasons recalled |")
    lines.append("|---|---:|---:|---:|")
    for state, rs in sorted(by_state.items()):
        n = len(rs)
        t = sum(x.triage_ok for x in rs) / n if n else 0
        r = sum(x.reasons_ok for x in rs) / n if n else 0
        lines.append(f"| {state} | {n} | {t:.1%} | {r:.1%} |")
    lines.append("")

    lines.append("## Triage confusion matrix\n")
    states = sorted({r.expected_triage for r in results} | {r.actual_triage for r in results})
    header = "| expected \\\\ predicted | " + " | ".join(states) + " |"
    lines.append(header)
    lines.append("|" + "---|" * (len(states) + 1))
    for exp in states:
        cells = [f"{confusion[(exp, p)]}" for p in states]
        lines.append(f"| **{exp}** | " + " | ".join(cells) + " |")
    lines.append("")

    if errors:
        lines.append(f"## Errors ({len(errors)} of {total})\n")
        lines.append("| label | expected | actual | reasons expected | reasons actual |")
        lines.append("|---|---|---|---|---|")
        for r in errors[:20]:
            exp = ",".join(sorted(r.expected_reasons)) or "—"
            act = ",".join(sorted(r.actual_reasons)) or "—"
            lines.append(
                f"| `{r.label}` | {r.expected_triage} | {r.actual_triage} | {exp} | {act} |"
            )
        if len(errors) > 20:
            lines.append(f"\n_... and {len(errors) - 20} more_")
        lines.append("")
    else:
        lines.append("## Errors\n\nNone. Every case matched ground truth.\n")

    lines.append("## How to reproduce\n")
    lines.append("```bash")
    lines.append("make reset-db")
    lines.append("make seed-eval     # seeds the synthetic corpus + ground truth")
    lines.append("make eval-extraction")
    lines.append("```")

    out_path.write_text("\n".join(lines))
    log.info("report written to %s", out_path)

def main() -> None:
    records = _load_groundtruth()
    log.info("loaded %d ground-truth records", len(records))

    session = SessionLocal()
    results: list[CaseResult] = []
    try:
        for rec in records:
            dto = get_invoice_dto(session, UUID(rec["invoice_id"]))
            if dto is None:
                log.warning("invoice %s not found — skipping", rec["invoice_id"])
                continue
            results.append(_evaluate(rec, dto))
    finally:
        session.close()

    out_dir = Path("eval")
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_report(results, out_dir / "extraction.md")
    _write_calibration_png(results, out_dir / "calibration.png")

if __name__ == "__main__":
    main()
