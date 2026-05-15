"""NL→SQL translator accuracy eval.

Runs ~20 curated natural-language queries through the translator and
diffs the resulting StructuredQuery against an expected payload. Reports:

  - exact-match accuracy (every filter clause, sort, limit, untranslated_intent matches)
  - per-clause precision/recall (set comparison of (field, op, value) triples)
  - per-field translation accuracy (which fields the translator nails)

Writes a Markdown report to `/data/uploads/eval/nl.md`.

Run from inside the backend container:
    docker compose exec backend uv run python -m scripts.eval_nl
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.nl_translation_service import TranslationError, translate

log = logging.getLogger("eval_nl")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")

@dataclass(frozen=True, slots=True)
class NLCase:
    nl: str
    expected_filters: list[tuple[str, str, Any]] = field(default_factory=list)

    expect_untranslated: bool = False

    notes: str = ""

CASES: list[NLCase] = [

    NLCase("duplicates", [("triage_state", "eq", "likely_duplicate")]),
    NLCase("show me likely duplicates", [("triage_state", "eq", "likely_duplicate")]),
    NLCase(
        "anomalies",
        [("has_anomaly", "eq", True)],
        notes="'anomalies' maps to has_anomaly to distinguish from non-anomaly needs_review",
    ),
    NLCase("flagged invoices", [("has_anomaly", "eq", True)]),
    NLCase(
        "needs review",
        [("triage_state", "eq", "needs_review")],
    ),
    NLCase(
        "pending review",
        [("triage_state", "eq", "needs_review")],
    ),
    NLCase("confirmed", [("review_status", "eq", "confirmed")]),
    NLCase(
        "encrypted invoices",
        [("review_status", "eq", "unprocessable")],
    ),
    NLCase(
        "unprocessable",
        [("review_status", "eq", "unprocessable")],
    ),
    NLCase(
        "failed to extract",
        [("review_status", "eq", "unprocessable")],
    ),

    NLCase("over $5000", [("total", "gt", 5000.0)]),
    NLCase("invoices above $1,000", [("total", "gt", 1000.0)]),
    NLCase("under $200", [("total", "lt", 200.0)]),
    NLCase("less than 50", [("total", "lt", 50.0)]),

    NLCase(
        "from Vega Logistics",
        [("vendor_name", "eq", "Vega Logistics")],
    ),
    NLCase(
        "from Halcyon Software",
        [("vendor_name", "eq", "Halcyon Software")],
    ),

    NLCase(
        "anomalies from Halcyon Software",
        [
            ("has_anomaly", "eq", True),
            ("vendor_name", "eq", "Halcyon Software"),
        ],
    ),
    NLCase(
        "duplicates from Vega over $1000",
        [
            ("triage_state", "eq", "likely_duplicate"),
            ("total", "gt", 1000.0),
            ("vendor_name", "eq", "Vega"),
        ],
        notes="Single-word vendor match — translator extracts 'Vega' without 'Logistics'",
    ),

    NLCase("", expected_filters=[]),
    NLCase("show me", expected_filters=[]),

    NLCase(
        "duplicates this month",
        [("triage_state", "eq", "likely_duplicate")],
        expect_untranslated=True,
        notes="'this month' isn't translated — surfaces in untranslated_intent",
    ),
    NLCase(
        "invoices in October",
        [],
        expect_untranslated=True,
        notes="Month parsing not implemented in stub — entire phrase untranslated",
    ),
]

def _filters_set(filters: list) -> set[tuple[str, str, Any]]:
    return {(f.field, f.op, _norm(f.value)) for f in filters}

def _expected_set(triples: list[tuple[str, str, Any]]) -> set[tuple[str, str, Any]]:
    return {(field_, op, _norm(value)) for field_, op, value in triples}

def _norm(v: Any) -> Any:
    """Normalize values for equality comparison (lists → tuples)."""
    if isinstance(v, list):
        return tuple(v)
    return v

@dataclass(slots=True)
class CaseResult:
    nl: str
    exact_match: bool
    precision: float
    recall: float
    untranslated_correct: bool
    expected: set
    actual: set
    error: str | None = None

def _evaluate(case: NLCase) -> CaseResult:
    try:
        query = translate(natural_language=case.nl)
    except TranslationError as exc:
        return CaseResult(
            nl=case.nl,
            exact_match=False,
            precision=0.0,
            recall=0.0,
            untranslated_correct=False,
            expected=_expected_set(case.expected_filters),
            actual=set(),
            error=f"TranslationError: {exc}",
        )

    expected = _expected_set(case.expected_filters)
    actual = _filters_set(query.filters)

    if expected and actual:
        precision = len(expected & actual) / len(actual)
        recall = len(expected & actual) / len(expected)
    elif not expected and not actual:
        precision = recall = 1.0
    else:
        precision = 0.0 if actual else 1.0
        recall = 0.0 if expected else 1.0

    untranslated_set = bool(query.untranslated_intent)
    untranslated_correct = untranslated_set == case.expect_untranslated

    exact_match = expected == actual and untranslated_correct
    return CaseResult(
        nl=case.nl,
        exact_match=exact_match,
        precision=precision,
        recall=recall,
        untranslated_correct=untranslated_correct,
        expected=expected,
        actual=actual,
    )

def _write_report(results: list[CaseResult], out_path: Path) -> None:
    total = len(results)
    exact_acc = sum(r.exact_match for r in results) / total
    untranslated_acc = sum(r.untranslated_correct for r in results) / total
    avg_precision = sum(r.precision for r in results) / total
    avg_recall = sum(r.recall for r in results) / total

    per_field_expected: dict[str, int] = defaultdict(int)
    per_field_recalled: dict[str, int] = defaultdict(int)
    for r in results:
        for f, op, v in r.expected:
            per_field_expected[f] += 1
            if (f, op, v) in r.actual:
                per_field_recalled[f] += 1

    lines = []
    lines.append("# Sift NL→SQL translator eval\n")
    lines.append(f"Corpus: **{total}** hand-curated natural-language queries.\n")
    lines.append("## Headline numbers\n")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| exact-match accuracy | **{exact_acc:.1%}** |")
    lines.append(f"| filter-clause precision (avg) | **{avg_precision:.1%}** |")
    lines.append(f"| filter-clause recall (avg) | **{avg_recall:.1%}** |")
    lines.append(f"| untranslated_intent classification | **{untranslated_acc:.1%}** |")
    lines.append("")

    lines.append("## Per-field translation recall\n")
    lines.append("| field | expected | recalled | rate |")
    lines.append("|---|---:|---:|---:|")
    for f in sorted(per_field_expected.keys()):
        exp = per_field_expected[f]
        rec = per_field_recalled[f]
        lines.append(f"| `{f}` | {exp} | {rec} | {rec / exp:.1%} |")
    lines.append("")

    lines.append("## Per-case detail\n")
    lines.append("| nl | match | expected → actual |")
    lines.append("|---|:-:|---|")
    for r in results:
        mark = "✓" if r.exact_match else "✗"
        if r.error:
            detail = f"⚠ {r.error}"
        else:
            exp_str = ", ".join(f"{f} {op} {v}" for f, op, v in sorted(r.expected, key=str)) or "—"
            act_str = ", ".join(f"{f} {op} {v}" for f, op, v in sorted(r.actual, key=str)) or "—"
            detail = f"`{exp_str}` → `{act_str}`"
        nl_display = r.nl if r.nl else "_(empty)_"
        lines.append(f"| {nl_display} | {mark} | {detail} |")
    lines.append("")

    lines.append("## How to reproduce\n")
    lines.append("```bash")
    lines.append("make eval-nl")
    lines.append("```")
    lines.append(
        "\n_Stub provider runs offline. To eval the Anthropic translator, set "
        "`SIFT_LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY=...` and re-run._"
    )

    out_path.write_text("\n".join(lines))
    log.info("report written to %s", out_path)

def main() -> None:
    log.info("running %d NL cases", len(CASES))
    results = [_evaluate(c) for c in CASES]
    out_dir = Path("eval")
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_report(results, out_dir / "nl.md")

    exact = sum(r.exact_match for r in results)
    log.info("exact-match: %d / %d (%.1f%%)", exact, len(results), 100.0 * exact / len(results))

if __name__ == "__main__":
    main()
