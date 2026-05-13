---
status: accepted
date: 2026-05-13
---

# NL → SQL via flat-conjunction `StructuredQuery` with field whitelist

## Context

Day 4 of Sift ships an NL search box (Cmd+K) that translates natural
language ("Vega invoices last 3 months over $5k") to executed queries
against Postgres. The product promise — Anchor 1, "messy docs →
structured, **queryable** data" — only holds if the queries are
trustworthy.

Running free-form LLM-generated SQL against a financial database is
unacceptable for two reasons: injection risk (cheap to mitigate) and
silent correctness bugs (expensive — looks-right-but-wrong queries
return looks-right-but-wrong answers, and a clerk has no way to tell).

Some typed intermediate representation between NL and SQL is required.
This ADR specifies it.

## Decision

NL queries translate to a typed `StructuredQuery` via Claude tool-use:

```python
class FilterClause(BaseModel):
    field: Literal[
        "vendor_name", "invoice_date", "total", "subtotal", "tax_total",
        "currency", "triage_state", "review_status",
        "has_anomaly", "is_duplicate", "raw_text"
    ]
    op: Literal[
        "eq", "neq", "gt", "gte", "lt", "lte",
        "in", "between", "contains", "fts_matches"
    ]
    value: str | float | list[str] | tuple[date, date]

class StructuredQuery(BaseModel):
    filters: list[FilterClause]                # implicit AND
    sort: tuple[FieldName, Literal["asc","desc"]] | None
    limit: int | None                          # default 50, max 500
    untranslated_intent: str | None            # what the LLM couldn't translate
```

Key properties:

- **Flat conjunction** of `FilterClause`s — implicit AND between
  clauses. No OR / NOT / nested groups in v1.
- **Field whitelist** enforced by the `Literal` type; off-whitelist
  fields are a validator failure.
- **Per-field op compatibility** enforced in the model validator
  (e.g. `currency` accepts `eq` / `neq` / `in` only; `raw_text` only
  `fts_matches` / `contains`).
- **Best-effort partial translation** — when NL exceeds the schema
  (aggregates like median, correlated comparisons), the LLM emits
  whatever fits and populates `untranslated_intent` with the dropped
  phrase. The UI surfaces this in an amber notice above results — never
  silently dropped.
- **Chips ARE the state.** Translated clauses render as removable chips
  in the filter bar *before* results render. Editing or removing a chip
  re-queries. The NL box is a chip-editor fast-path, not a parallel
  state stream — no NL-text vs chip-state divergence by design.
- **FTS bridge.** Postgres `tsvector` full-text on `raw_text` is exposed
  as `{field: "raw_text", op: "fts_matches", value: "..."}`. NL queries
  route through this naturally; same chip render path, no separate FTS
  UI.
- **Sort + limit** are top-level on `StructuredQuery`. Sortable fields
  are a subset of the filter whitelist (e.g. `total`, `invoice_date`).
- **CSV/JSON export** serializes the `StructuredQuery` itself into the
  exported file's header — audit-able structured queries, not anonymous
  result blobs.

## Considered Options

- **(a) Filter tree with AND/OR/NOT nodes.** Expressive and forward-
  compatible. Rejected because chip UI requires a tree-aware
  nested-brackets surface (Anchor 2 cost), the validator becomes
  recursive (Anchor 2 code-quality cost), and real AP clerk workflows
  are almost always conjunctive — the OR cases are better served by
  Cmd+K command-palette actions ("find similar to this") than by
  generic OR support.
- **(b) Named-query DSL (predefined tool-use functions per query
  shape).** Strongest guardrails. Rejected because it collapses
  NL→SQL into a thin RPC wrapper — kills the depth signal for the
  interview eval, and locks clerks out of slight variations on canned
  queries. Every new shape requires new code.
- **(c) Flat conjunction with field whitelist (chosen).** ~90% of
  realistic AP clerk queries covered. Validator is ~50 LOC. Chip
  rendering is a single map over the filter list. Failure mode is
  overcommunicating drops, not silent wrongness.
- **(d) Reject-gracefully on untranslatable.** Dead-end UX — clerk gets
  nothing back and must guess what's allowed. Replaced by best-effort
  partial translation with the visible drop notice.
- **(e) Trust LLM self-report of "I translated everything."** Same
  miscalibration argument as ADR-0003. The `untranslated_intent` field
  is logged as a secondary signal for NL_EVAL.md but never used to drive
  UI behavior — the validator is the ground truth.

## Consequences

- **OR / NOT / nested groups are not expressible in v1.** Acceptable.
  Cmd+K command-palette covers the motivating cases. Schema is
  forward-compatible if demand emerges.
- **Chips and NL box cannot diverge** — a class of state-sync bugs
  eliminated by design.
- **Testable seam** — the NL→`StructuredQuery` translator is a pure
  function. `NL_EVAL.md` sits on this seam: ~15 hand-curated NL inputs
  with expected outputs, diffed exact-match and per-field.
- **Audit posture** — every query the system runs is a serialized
  `StructuredQuery` and is logged with the request. Exports include the
  query in the header. A clerk can always answer "what did I ask for?"
- **Implementation size** — `StructuredQuery` + validator ~50 LOC,
  chip render + state hook ~150 LOC, LLM tool-use prompt is a single
  cached schema. No new tables.
- **`raw_text` denormalization** — the `tsvector` column lives on
  `extractions` (or a materialized view across extractions) — decided
  on the implementation pass.
