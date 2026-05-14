# Sift

Vendor invoices in mixed formats → clean, structured data an AP clerk can review and query.

Built for the Zamp Engineering Project Round (Problem 01: messy documents → structured queryable data).

---

## 60-second demo

The three beats live in `make demo`:

1. **It understands messy.** Drop a PDF on the inbox. The pipeline runs through a Haiku → Sonnet → Opus cascade, resolves bboxes per field, renders the review screen with hover-highlight overlays on the PDF — even on scanned-image PDFs where the vision path takes over.
2. **It catches what a clerk would catch.** A `$89,000` Halcyon Software invoice lands flagged as `needs_review` with two reason cards stacked: `anomaly` (Z=219 vs vendor mean $34,250 ±$250) and `low_confidence` (cascade agreement override fired). The clerk sees *why* in one glance — no PDF reading required.
3. **It gets better with use.** A second Vega invoice with identical visual content flags as `likely_duplicate`, pointing back at the original. The duplicate-review screen shows both PDFs side-by-side with a field-diff panel.

Plus a fourth beat that's the queryable half of the promise:

4. **It's actually queryable.** Type `anomalies from Halcyon Software` at `/search`. The backend translator returns a typed `StructuredQuery`; the URL state updates; the result list shows one row — the $89k anomaly. Hit "Export CSV" to get a self-describing audit file.

---

## Quick start (no API key required)

```bash
git clone <this repo>
cd sift
cp .env.example .env       # defaults are safe for local dev — no key needed
make demo                  # = reset-db + seed 7 curated invoices
open http://localhost:5173
```

`make demo` runs the full pipeline with `SIFT_LLM_PROVIDER=stub` — every LLM call goes through `StubLLMClient`, which returns deterministic canned extractions that exercise the entire cascade (Haiku→Sonnet→Opus → agreement override). **Zero API key. Zero credits burned.** Reviewers can clone, demo, and read the codebase without any setup beyond Docker.

Switch to real model calls by editing `.env`:

```env
SIFT_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

The architecture supports this as a single setting change — see ADR-0005 (`adapters/llm_client.py` Protocol + factory). Adding an OpenAI or local provider is a new implementation class plus one factory branch.

---

## Architecture

```
                  ┌──────────────────────────────────────────────┐
                  │  Frontend (React + TanStack Query)           │
                  │                                              │
                  │  /inbox  /invoice/:id  /duplicate-review/:id │
                  │  /search ←─── chips ARE the URL state        │
                  └────────────────┬─────────────────────────────┘
                                   │ JSON
                  ┌────────────────▼─────────────────────────────┐
                  │  api/       thin handlers, no DB / no LLM    │
                  ├──────────────────────────────────────────────┤
                  │  services/  extraction · nl_translation ·    │
                  │             search · vendor_memory · triage  │
                  ├──────────────────────────────────────────────┤
                  │  domain/    pure: models · validators ·      │
                  │             scoring · triage · anomalies ·   │
                  │             duplicates · nl_schema           │
                  ├──────────────────────────────────────────────┤
                  │  adapters/  llm_client · pdf_reader ·        │
                  │             storage/*_repo                   │
                  └────┬────────────────────┬────────────────────┘
                       │                    │
            ┌──────────▼─┐         ┌───────▼─────────┐
            │ Anthropic  │         │ Postgres        │
            │ (or Stub)  │         │  + tsvector FTS │
            │ via the    │         │  + pgvector     │
            │ Protocol   │         └─────────────────┘
            └────────────┘
```

Four layers with strict one-way dependencies (enforced by `import-linter` in CI per ADR-0005):

- `api/` is a thin shell. No imports from `adapters/` or `db/`. One exception in CI config for FastAPI's `Depends(get_session)`.
- `services/` orchestrates everything else. Knows about `domain/` and `adapters/`.
- `domain/` is pure. No I/O, no DB, no LLM. The eval harness sits on this seam.
- `adapters/` are the IO seams. `LLMClient` is a Protocol — Anthropic + Stub implementations live behind it.

---

## What's extracted

| Field group | Surface | Where it lands |
|---|---|---|
| Header fields | vendor_name, invoice_number, invoice_date, subtotal, tax, total, currency | `extracted_fields` JSONB on extractions |
| Bounding boxes | Per-field rect on the PDF for hover-highlight | inside each `ExtractedField` |
| Cascade trace | Every tier the request hit + token usage | `cascade_trace` JSONB |
| Anomaly / duplicate flags | Reason cards in the review pane | `predicted_triage_reasons` JSONB |
| Line items | description / qty / unit / line_total per row | `line_items` JSONB |
| Tax breakdown | Per-jurisdiction tax rows | `tax_breakdown` JSONB |
| FTS index | Concatenated extracted text, GIN-indexed | `raw_text_tsv` generated column |

---

## Scope decisions

Anchored to PLAN.md's cut-down ladder:

| Shipped | Why it stays |
|---|---|
| Scanned-PDF vision path + bbox highlight | Beat-1 hero. Without it, "messy" means "messy text"; PLAN.md anchors on "messy documents". |
| Triage cards (math · anomaly · duplicate · low-conf · missing · unseen-vendor · extraction-failed) | Beat-2 backbone. The system tells the clerk *why* it's flagged. |
| Composite confidence + cascade agreement override (ADR-0003) | Calibrated triage states across every beat — `min(structural, history)` with cascade override. |
| `ExtractionFailedCard` with Retry / Mark unprocessable / Manual entry (ADR-0006) | Demo never dead-ends on a bad PDF. |
| Inbox + ReviewScreen + DuplicateReviewScreen + `/search` | Minimum UX shell that exercises all three demo beats. |
| NL→SQL translator (whitelist + per-field-op compatibility + partial-translation surface) | Anchor-1 "queryable" promise. |
| CSV/JSON export with serialized-query audit header | Anchor-1 deep-link + audit trust signal. |
| Provider pattern (`Stub` + `Anthropic` + factory) | Interview-review path. Clone → demo, zero cost. |

| Deliberately out | Why |
|---|---|
| Active learning (clerk-correction → vendor.memory rules → memory-applied auto-fill on next invoice) | Day-5 stretch in PLAN.md. Skipped to hold the quality bar on Phases 1-5. The bones are there (`field_corrections` table, `vendor.memory` shape, `source: memory-applied` flag) — the loop just isn't wired. |
| Multi-currency invoices | Out per PLAN.md rung 5. Surfaces in the export "currency" column but isn't a first-class feature. |
| Vision-path line items + vision-path tax breakdown | Day-4 stretch in PLAN.md. Returns `[]` on scanned PDFs; documented in code. |
| Sort UI on `/search` | The `StructuredQuery.sort` field is supported by the backend SQL builder; the frontend just doesn't expose a sort picker yet. |
| Bulk-confirm with delayed-dispatch undo | Bulk-confirm ships with informational sonner-undo (toast says "applied"); the queued-send-with-cancel version is a polish item. |

---

## Eval

Run `make eval` to reproduce. Headline numbers from the latest stub-mode pass:

| Metric | Value | Detail |
|---|---|---|
| Extraction `vendor_name` exact-match | **100.0%** | 55/55 synthetic cases |
| Extraction `total` exact-match (±$0.50) | **100.0%** | 55/55 |
| Triage `predicted_triage_state` accuracy | **100.0%** | confusion matrix in `backend/eval/extraction.md` |
| NL→SQL translator exact-match | **90.9%** | 20/22 — the 2 "misses" are partial-translation cases surfacing in `untranslated_intent` by design |

Full reports:
- [EVAL.md](./EVAL.md) — extraction + calibration methodology
- [TRIAGE-EVAL.md](./TRIAGE-EVAL.md) — synthetic triage corpus
- [NL_EVAL.md](./NL_EVAL.md) — NL translator
- [backend/eval/extraction.md](./backend/eval/extraction.md), [nl.md](./backend/eval/nl.md), [calibration.png](./backend/eval/calibration.png) — auto-generated detail

Stub-mode 100% accuracy isn't the boast — what matters is that the same corpus + same pipeline produces the same number every run. Anthropic-mode rerun is a single env-var flip (`SIFT_LLM_PROVIDER=anthropic`) on the same harness; cost ~$0.50–$2.00 per pass.

---

## Stub-mode scenarios

`StubLLMClient` ships with three keyword-keyed scenarios so the demo narrative works without keys:

| Keyword in invoice text | Scenario | Drives demo beat |
|---|---|---|
| `halcyon`            | Halcyon Software, $34,062.50 | Vendor anomaly (large value vs history) |
| `bramble`            | Bramble Catering, $750.00    | Near-duplicate review |
| `[stub:fail]` / `encrypted` | extraction_failed=True | Unprocessable + retry |
| (anything else)      | Vega Logistics, $1,180.00    | Cascade + agreement-override |

Every scenario returns a `total` off by $1 on tier-1 (Haiku) vs tier-2 (Sonnet), so the cascade actually fires and the trace shows real disagreement / agreement-override behavior. Different invoice text → different invoice numbers (seeded from SHA-256), so multiple uploads in stub mode show as distinct rows.

---

## Setup details

### Requirements

- Docker + Docker Compose
- That's it. The backend runs `uv` + Python 3.12 inside the container; the frontend runs `pnpm` + Node inside its own container.

### Environment variables (`.env`)

```env
DATABASE_URL=postgresql+psycopg://sift:sift@db:5432/sift
SIFT_LLM_PROVIDER=stub           # 'stub' (default) or 'anthropic'
ANTHROPIC_API_KEY=               # required only when provider=anthropic
SIFT_MODEL_TIER_1=claude-haiku-4-5
SIFT_MODEL_TIER_2=claude-sonnet-4-6
SIFT_MODEL_TIER_3=claude-opus-4-7
SIFT_UPLOAD_DIR=/data/uploads
SIFT_LOG_LEVEL=INFO
SIFT_LOG_FORMAT=json
SIFT_CORS_ORIGINS=http://localhost:5173
```

### Common commands

```bash
make dev               # bring everything up
make demo              # reset DB + seed 7 curated invoices (beats 1-4)
make test              # full backend + frontend test suite
make lint              # ruff + import-linter + tsc
make eval              # full eval pipeline (reset + seed-eval + score + write reports)
make seed-demo         # populate inbox without resetting (idempotent: skips dupes)
make reset-db          # drop schema + recreate + migrate + wipe uploads
```

---

## Deployment

The backend builds a single Docker image with the production Vite bundle served by FastAPI's `StaticFiles`. `fly.toml` is in the repo; Neon Postgres is the recommended managed DB. CI deploys on push to `main` via `.github/workflows/deploy.yml`.

See **[DEPLOY.md](./DEPLOY.md)** for the full guide — Neon setup, Fly app creation, secrets, GitHub Actions wire-up, migration safety, rollback. A live URL will land here once the first deploy goes through.

---

## Future work

Order matches what would ship next given another sprint:

1. **Active learning loop.** Clerk corrections persist to `field_corrections`; `vendor_memory_service.consolidate()` aggregates corrections into `vendor.memory.rules`; the stub provider applies those rules on subsequent extractions. The "watch it learn" demo line. All the bones are in place — needs ~4-6 small tasks of wiring.
2. **DocILE-based eval.** Replace synthetic corpus with a real subset; per-row human-reviewed ground truth; surface the cut decision on line items / tax breakdown if anthropic-mode F1 falls below threshold.
3. **Vision-path line items + tax breakdown.** The current vision branch returns `[]` for both; extending the vision tool-use schema is straightforward, and the eval gate would say whether they're worth shipping.
4. **Sort UI on `/search`.** Backend supports it via `StructuredQuery.sort`; the frontend needs a column-header click handler.
5. **Bulk-confirm with delayed dispatch.** Replace the "applied + informational undo toast" pattern with a queued-send model so undo actually cancels in-flight confirmations.
6. **pgvector semantic search.** "Find invoices similar to this one" — pgvector is enabled from day one per ADR-0002 but unused.

---

## References

- [PLAN.md](./PLAN.md) — 5-day execution plan, cut-down ladder, seed-corpus design
- [CONTEXT.md](./CONTEXT.md) — domain language
- [docs/adr/](./docs/adr/) — six locked architecture decisions:
  - ADR-0001: extraction pipeline (no Docling)
  - ADR-0002: Postgres on Neon over SQLite
  - ADR-0003: composite confidence scoring
  - ADR-0004: NL→SQL via flat conjunction + field whitelist
  - ADR-0005: layered architecture (api → services → domain ← adapters)
  - ADR-0006: failure modes
