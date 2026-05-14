# Sift

Vendor invoices in mixed formats → clean, structured data an AP clerk can review and query.

> Built for the Zamp Engineering Project Round (Problem 01).
> See [CONTEXT.md](./CONTEXT.md) for domain language and [PLAN.md](./PLAN.md) for the 5-day execution plan.
> Architecture decisions live in [docs/adr/](./docs/adr/).

---

## Quick start (no API key required)

```bash
git clone <this repo>
cd sift
cp .env.example .env       # defaults are safe for local dev — no key needed
make dev                   # docker compose up backend + frontend + Postgres
open http://localhost:5173
```

Drop a PDF on the inbox. The pipeline runs end-to-end with **zero external API calls** — the default `SIFT_LLM_PROVIDER=stub` setting routes every LLM call through `StubLLMClient`, which returns deterministic canned extractions that exercise the full cascade (Haiku → Sonnet → Opus → agreement-score override). Useful for:

- Reviewing the codebase without spending anything
- Running the demo on a flight / offline
- CI: every test runs offline against the stub

Switch to real model calls by editing `.env`:

```env
SIFT_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

The architecture documents the swap as a single setting change — see ADR-0005 (`adapters/llm_client.py` Protocol + factory). Adding an OpenAI or local provider is a new implementation class + one factory branch.

## Stub-mode scenarios

`StubLLMClient` ships with three keyword-keyed scenarios so the demo narrative still works without keys:

| Keyword in invoice text | Scenario | Drives demo beat |
|---|---|---|
| `halcyon`            | Halcyon Software, $34,062.50 | Vendor anomaly (large value vs history) |
| `bramble`            | Bramble Catering, $750.00    | Near-duplicate review |
| `[stub:fail]` / `encrypted` | extraction_failed=True | Unprocessable + retry |
| (anything else)      | Vega Logistics, $1,180.00    | Cascade + agreement-override |

Every scenario returns a `total` that's off by $1 on tier-1 (Haiku) vs tier-2 (Sonnet) so the cascade actually fires and the trace shows real disagreement / agreement-override behavior. Different invoice text → different invoice numbers (seeded from SHA-256), so multiple uploads in stub mode show as distinct rows.

---

## What gets extracted

| Field group        | Surface              | Source / status |
|---|---|---|
| Header fields      | vendor_name, invoice_number, invoice_date, subtotal, tax, total, currency | Shipped Day 1 / 2 |
| Bounding boxes     | per-field rect on the PDF for hover-highlight | Shipped Day 2 (digital + vision) |
| Cascade trace      | every tier the request hit, with token usage   | Shipped Day 2 |
| Anomaly + duplicate flags | flagged in the review pane with the matching reason card | Shipped Day 2 |
| **Line items**     | description / quantity / unit price / line total per row | Shipped Day 3 — quality-gated |
| **Tax breakdown**  | per-jurisdiction tax rows | Shipped Day 4 — quality-gated |

### Day-3 line items — what's in vs deliberately out

**In:** `extractions.line_items` JSONB column · separate LLM method (`extract_line_items`) at the cascade-final tier · stub returns scenario-appropriate line items (Vega freight x3 / Halcyon software x2 / Bramble catering x5) · read-only table mounted in `ReviewScreen` below the header fields panel · `line_items_sum_check` validator runs after extraction.

**Deliberately out for Day 3:** inline editing of line items · per-line bbox-on-hover · vision-path line items (the vision branch returns `[]` for line items in Day 3) · line-item-level cascade · `line_items_dont_sum` as a triage reason (sum mismatch is logged but does NOT change `predicted_triage_state` — Day-3 line items are quality-gated and false-positive math reasons would pollute the inbox).

**Eval gate (Day 5):** when running with `SIFT_LLM_PROVIDER=anthropic`, the line-items section will be benchmarked against a DocILE subset. If the per-line F1 falls below the threshold documented in `EVAL.md`, the section gets cut from the demo seed with a written failure analysis — that's the PLAN.md "honest cut" path rather than half-shipping unreliable extraction.

### Day-4 tax breakdown — what's in vs deliberately out

**In:** `extractions.tax_breakdown` JSONB column · separate `extract_tax_breakdown` LLM method at the cascade-final tier · stub returns scenario-appropriate jurisdiction rows · read-only table mounted in `ReviewScreen` below the line-items panel · `tax_breakdown_sum_check` validator (sum of `amount` vs header `tax`).

**Deliberately out:** inline editing · vision-path tax breakdown (returns `[]` for now) · `tax_breakdown_dont_sum` as a triage reason. Same quality-gating logic as line items — a noisy sum mismatch would erode the inbox's trust signal.

---

## Search & query — NL → structured query (Day 4)

Sift's "messy documents → **queryable** data" promise (Anchor 1) ships as a real search page at `/search`, plus a ⌘K palette that uses the same backend. Both surfaces route through:

```
NL input  →  POST /api/search/translate  →  StructuredQuery
StructuredQuery  →  POST /api/search       →  list[InvoiceOut]
```

### Architecture stakes (ADR-0004)

- **Whitelisted field set + per-field op compatibility.** The whitelist lives in `domain/nl_schema.py`, gets reflected into the LLM tool-use schema (so the model only sees legal ops), and is re-checked by the Pydantic validator before any SQL builder sees it. Malformed payloads → 422 with field-level errors — never silently coerced.
- **No raw text from the LLM hits SQL.** The LLM emits a typed `StructuredQuery` (filters / sort / limit / `untranslated_intent`); the SQL builder dispatches each (field, op) pair through a hand-written, type-checked SQLAlchemy expression. Values come in as typed Python objects.
- **Chips ARE the state.** The search page stores the entire `StructuredQuery` in the URL `?q=` param. Editing or removing a chip mutates the URL → TanStack Query re-runs the search. Browser back/forward Just Works. Deep-link sharing preserves the exact search verbatim.
- **Partial translation always surfaces.** If the LLM can't translate part of the request, that text comes back in `untranslated_intent` and renders in an amber notice above the results — never silently dropped.
- **One translator, everywhere.** The ⌘K palette uses the same `/api/search/translate` endpoint as the full `/search` page. No client-side translation map that can diverge.

### What you can search on

```
field            ops                                  value type
─────────────    ──────────────────────────────────   ───────────────
vendor_name      eq, neq, in, contains                string / list
invoice_date     eq, neq, gt, gte, lt, lte, between   YYYY-MM-DD / pair
total            eq, neq, gt, gte, lt, lte, between   number
subtotal         (same as total)
tax_total        (same as total)
currency         eq, neq, in                          ISO 4217 string
triage_state     eq, neq, in                          confident | needs_review | likely_duplicate
review_status    eq, neq, in                          pending | confirmed | dismissed_duplicate | unprocessable
has_anomaly      eq                                   boolean
is_duplicate     eq                                   boolean
raw_text         contains, fts_matches                string
```

`raw_text` is Postgres FTS via a `tsvector` generated column maintained automatically on every extraction. The service writes a `raw_text` column from the concatenation of every extracted field value + line-item description + tax-jurisdiction label; the database derives `raw_text_tsv` and a GIN index from it.

### Demo prompts (stub mode)

The stub provider's deterministic regex translator covers the demo phrasings end-to-end. Try these on `/search`:

- *"duplicates from Vega"*
- *"anomalies from Halcyon Software"*
- *"invoices over $5,000"*
- *"encrypted invoices"*
- *"confirmed from Halcyon Software"*

Anything outside the demo phrasings shows up in the amber "partial translation" notice — the system tells you what it couldn't translate instead of guessing.

### CSV / JSON export

`/search` has Export CSV and Export JSON buttons. Both go through `POST /api/search/export?format=...` with the current `StructuredQuery` as the body, and return a self-describing file:

- CSV: leading `# Sift export · <timestamp>` / `# Rows: N` / `# Query: {...}` comment lines, then the standard header + data rows.
- JSON: wrapper `{ exported_at, row_count, query, rows }`.

Anyone who finds the exported file later can see exactly what query produced it.

---

This README is still a placeholder for the rest of the project narrative. The real README ships on Day 5 with the 60-second demo story, architecture diagram, eval numbers, and live URL.
