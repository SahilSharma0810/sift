"""End-to-end search accuracy eval.

Translates each natural-language query through `nl_translation_service.translate`,
executes the resulting `StructuredQuery` via `search_service.run_query`, and
diffs the returned invoice set against the ground-truth set derived from
`eval/groundtruth.json`.

This is the search half of the extraction eval — same shape, different
half of the pipeline. The translation step alone is covered by
`eval_nl.py`; this script covers translate → SQL builder → executor → rows.

Per case it reports:
  - precision / recall on the returned invoice set
  - false positives + false negatives (sample)
  - whether the set matches exactly

Writes a Markdown report to `eval/search.md`.

Expected ground-truth membership is derived from the `case` dict on each
seeded record (the asdict-ed `EvalCase`), not hardcoded IDs — so the eval
stays robust if seed counts shift.

Run from inside the backend container:
    docker compose exec backend uv run python -m scripts.eval_search
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.db.session import SessionLocal
from app.services.nl_translation_service import TranslationError, translate
from app.services.search_service import run_query

log = logging.getLogger("eval_search")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")

GTPredicate = Callable[[dict], bool]


@dataclass(frozen=True, slots=True)
class SearchCase:
    nl: str
    matches: GTPredicate
    description: str
    notes: str = ""


def _is_dup(c: dict) -> bool:
    return c["expected_triage_state"] == "likely_duplicate"


def _needs_review(c: dict) -> bool:
    return c["expected_triage_state"] == "needs_review"


def _is_anomaly(c: dict) -> bool:
    return "anomaly" in c["expected_reason_types"]


def _confirmed(c: dict) -> bool:
    return bool(c.get("confirm"))


def _unprocessable(c: dict) -> bool:
    return bool(c.get("unprocessable"))


def _vendor(name: str) -> GTPredicate:
    return lambda c: c["expected_vendor"] == name


def _total_gt(thresh: float) -> GTPredicate:
    return lambda c: not _unprocessable(c) and float(c["expected_total"]) > thresh


def _total_lt(thresh: float) -> GTPredicate:
    return lambda c: not _unprocessable(c) and 0 < float(c["expected_total"]) < thresh


def _and(*preds: GTPredicate) -> GTPredicate:
    return lambda c: all(p(c) for p in preds)


CASES: list[SearchCase] = [
    SearchCase("duplicates", _is_dup, "triage_state = likely_duplicate"),
    SearchCase(
        "show me likely duplicates",
        _is_dup,
        "triage_state = likely_duplicate",
    ),
    SearchCase("needs review", _needs_review, "triage_state = needs_review"),
    SearchCase("anomalies", _is_anomaly, "has_anomaly = True"),
    SearchCase("flagged invoices", _is_anomaly, "has_anomaly = True"),
    SearchCase("confirmed", _confirmed, "review_status = confirmed"),
    SearchCase("unprocessable", _unprocessable, "review_status = unprocessable"),
    SearchCase(
        "failed to extract",
        _unprocessable,
        "review_status = unprocessable",
    ),
    SearchCase("over $5000", _total_gt(5000.0), "total > 5000"),
    SearchCase("invoices above $1,000", _total_gt(1000.0), "total > 1000"),
    SearchCase("under $200", _total_lt(200.0), "0 < total < 200 (no seeded rows)"),
    SearchCase(
        "from Atlas Freight",
        _vendor("Atlas Freight"),
        "vendor_name = Atlas Freight",
    ),
    SearchCase(
        "from Fjord Services",
        _vendor("Fjord Services"),
        "vendor_name = Fjord Services (includes outlier)",
    ),
    SearchCase(
        "anomalies from Fjord Services",
        _and(_is_anomaly, _vendor("Fjord Services")),
        "has_anomaly = True AND vendor_name = Fjord Services",
    ),
    SearchCase(
        "confirmed over $1000",
        _and(_confirmed, _total_gt(1000.0)),
        "review_status = confirmed AND total > 1000",
    ),
]


@dataclass(slots=True)
class CaseResult:
    nl: str
    description: str
    expected_n: int
    actual_n: int
    precision: float
    recall: float
    exact_match: bool
    false_positives: list[str]
    false_negatives: list[str]
    error: str | None = None


def _load_groundtruth() -> list[dict]:
    gt_path = Path("eval") / "groundtruth.json"
    if not gt_path.exists():
        raise FileNotFoundError(
            f"{gt_path} missing — run `make seed-eval` first to populate the eval corpus."
        )
    return json.loads(gt_path.read_text())


def _expected_ids(case: SearchCase, gt: list[dict]) -> set[str]:
    return {rec["invoice_id"] for rec in gt if case.matches(rec["case"])}


def _label_for(invoice_id: str, gt: list[dict]) -> str:
    for rec in gt:
        if rec["invoice_id"] == invoice_id:
            return rec["case"]["label"]
    return invoice_id[:8]


def _evaluate(case: SearchCase, session, gt: list[dict]) -> CaseResult:
    expected = _expected_ids(case, gt)
    try:
        query = translate(natural_language=case.nl)
    except TranslationError as exc:
        return CaseResult(
            nl=case.nl,
            description=case.description,
            expected_n=len(expected),
            actual_n=0,
            precision=0.0,
            recall=0.0,
            exact_match=False,
            false_positives=[],
            false_negatives=sorted(_label_for(i, gt) for i in expected),
            error=f"TranslationError: {exc}",
        )

    rows = run_query(session, query=query)
    actual = {str(r.id) for r in rows}

    tp = expected & actual
    fp = actual - expected
    fn = expected - actual

    precision = (len(tp) / len(actual)) if actual else (1.0 if not expected else 0.0)
    recall = (len(tp) / len(expected)) if expected else (1.0 if not actual else 1.0)
    exact = not fp and not fn

    return CaseResult(
        nl=case.nl,
        description=case.description,
        expected_n=len(expected),
        actual_n=len(actual),
        precision=precision,
        recall=recall,
        exact_match=exact,
        false_positives=sorted(_label_for(i, gt) for i in fp),
        false_negatives=sorted(_label_for(i, gt) for i in fn),
    )


def _write_report(results: list[CaseResult], out_path: Path) -> None:
    total = len(results)
    exact = sum(r.exact_match for r in results)
    avg_p = sum(r.precision for r in results) / total
    avg_r = sum(r.recall for r in results) / total

    lines: list[str] = []
    lines.append("# Sift search eval (end-to-end)\n")
    lines.append(
        f"Corpus: **{total}** natural-language queries · runs full pipeline "
        "(NL → translate → SQL builder → executor → invoice set).\n"
    )
    lines.append("Ground truth derived from `eval/groundtruth.json` predicates, not hardcoded IDs.\n")

    lines.append("## Headline numbers\n")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| exact-set-match rate | **{exact / total:.1%}** ({exact} / {total}) |")
    lines.append(f"| set precision (avg) | **{avg_p:.1%}** |")
    lines.append(f"| set recall (avg) | **{avg_r:.1%}** |")
    lines.append("")

    lines.append("## Per-case results\n")
    lines.append("| nl | expected | actual | precision | recall | match |")
    lines.append("|---|---:|---:|---:|---:|:-:|")
    for r in results:
        mark = "✓" if r.exact_match else "✗"
        nl_display = r.nl if r.nl else "_(empty)_"
        lines.append(
            f"| {nl_display} | {r.expected_n} | {r.actual_n} | "
            f"{r.precision:.1%} | {r.recall:.1%} | {mark} |"
        )
    lines.append("")

    errors = [r for r in results if not r.exact_match]
    if errors:
        lines.append(f"## Errors ({len(errors)} of {total})\n")
        lines.append("| nl | description | false positives | false negatives | error |")
        lines.append("|---|---|---|---|---|")
        for r in errors:
            fp = ", ".join(f"`{l}`" for l in r.false_positives[:5]) or "—"
            if len(r.false_positives) > 5:
                fp += f" _+{len(r.false_positives) - 5}_"
            fn = ", ".join(f"`{l}`" for l in r.false_negatives[:5]) or "—"
            if len(r.false_negatives) > 5:
                fn += f" _+{len(r.false_negatives) - 5}_"
            err = r.error or "—"
            lines.append(f"| {r.nl} | {r.description} | {fp} | {fn} | {err} |")
        lines.append("")
    else:
        lines.append("## Errors\n\nNone. Every case returned the expected invoice set.\n")

    lines.append("## How to reproduce\n")
    lines.append("```bash")
    lines.append("make reset-db")
    lines.append("make seed-eval     # seeds the synthetic corpus + ground truth")
    lines.append("make eval-search")
    lines.append("```")
    lines.append(
        "\n_Stub provider runs offline. To eval the Anthropic translator + SQL "
        "executor end-to-end, set `SIFT_LLM_PROVIDER=anthropic` + "
        "`ANTHROPIC_API_KEY=...` and re-run._"
    )

    out_path.write_text("\n".join(lines))
    log.info("report written to %s", out_path)


def main() -> None:
    gt = _load_groundtruth()
    log.info("loaded %d ground-truth records", len(gt))
    log.info("running %d search cases", len(CASES))

    session = SessionLocal()
    try:
        results = [_evaluate(c, session, gt) for c in CASES]
    finally:
        session.close()

    out_dir = Path("eval")
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_report(results, out_dir / "search.md")

    exact = sum(r.exact_match for r in results)
    log.info(
        "exact-set-match: %d / %d (%.1f%%)",
        exact,
        len(results),
        100.0 * exact / len(results),
    )


if __name__ == "__main__":
    main()
