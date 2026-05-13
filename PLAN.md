# Sift — 5-Day Execution Plan

Built for the Zamp Engineering Project Round (Problem 01: messy docs → structured, queryable data).

For domain language, see [CONTEXT.md](./CONTEXT.md). For architecture
decisions, see [docs/adr/](./docs/adr/).

## Operating principle

**Every day ends in a deployable, demo-able state.** Quality over quantity.
If a feature won't ship reliably, cut it and document why.

---

## Day 1 — Foundation + happy-path extraction

**Goal at EOD:** Upload a clean digital PDF → see extracted header fields on
the review screen, **deployed to a live URL**.

- Repo scaffold: Vite/React + FastAPI monorepo, one Dockerfile, push to GitHub
- Backend module layout per ADR-0005 (`api / services / domain /
  adapters`), `import-linter` wired in CI to enforce one-way deps from
  Day 1 — drift caught on commit, not on Day 4
- Frontend `types/` generated from backend Pydantic via
  `pydantic-to-typescript` build step — eliminates model/type drift
- Postgres on Neon, Alembic migrations
- Schema (locked Day 1, four tables — see "Schema sketch" below):
  - `invoices` — file refs, hashes, `vendor_id`, `review_status`
    (`pending` / `confirmed` / `dismissed_duplicate` / `unprocessable`)
  - `vendors` — name, tax_id, normalized_name, first_seen_at
  - `extractions` — 1:N to invoices, holds `predicted_triage_state` +
    `predicted_triage_reasons` + `confidence_per_field` + `cascade_trace`,
    with `is_current` partial-unique index
  - `field_corrections` — event log of clerk edits, drives EVAL.md
    "top-10 corrections" and unblocks Day 5 active-learning stretch
- File upload endpoint → save PDF to Fly volume
- PyMuPDF text extraction (digital PDFs only — vision path is Day 2)
- Claude Haiku call with tool-use schema for **header fields only**
  (vendor, invoice #, dates, subtotal/tax/total, currency). Prompt-cached
  schema + examples. LLM self-reported `confidence` field included in the
  schema but **logged only** — never used for triage (see ADR-0003).
- `adapters/llm_client.py` ships service-layer auto-retry on transient
  errors (timeout, 429, 5xx) — three attempts with exponential backoff,
  retry-count logged on the extraction row (ADR-0006).
- Validator layer + per-field structural confidence:
  - Math reconciles (subtotal + tax = total), required fields present,
    format valid (date parses, currency code in ISO 4217), each yields a
    `structural_score` per field with hard floors/ceilings.
  - `history_score` stub at 0.85 (vendor history lands Day 2).
  - `confidence_per_field = min(structural_score, history_score)`.
- Frontend shell: theme tokens, routes (`/inbox`, `/invoice/:id`), shadcn
  primitives wired
- Inbox table (no triage states yet)
- Review screen (side-by-side, no bbox highlight yet)
- **Deploy to Fly before writing any feature code** — verify the deploy
  pipeline first thing.

## Day 2 — The depth bet (triage intelligence) — DEMO-COMPLETE STATE

**Goal at EOD:** Upload anything (digital or scanned), get the right triage
state with a specific reason. **The full demo loop works.**

- Vision path: pdf2image → Claude Sonnet for scanned PDFs
- Branch logic: `PyMuPDF.has_text()` → text path / else vision path
- Per-vendor history table populated; `history_score` wired in (Z-score on
  numeric fields, 0.85 default elsewhere). Same table feeds anomaly check.
- Tiered cascade: Haiku → Sonnet → Opus triggers on
  `min_field_confidence < 0.7` OR math fails OR unseen vendor. When the
  cascade fires, the disputed fields' confidence is replaced by an
  **agreement score** between upstream and downstream model outputs.
- Anomaly detection vs per-vendor history (mean ± 3σ on totals)
- Duplicate detection (perceptual hash via `imagehash` + content fingerprint)
- Per-vendor memory hint injected into prompt for repeat vendors
- Triage state computation — reason strings name the specific validator or
  score that fired ("subtotal + tax ≠ total, off by $0.40"), never
  "model uncertain"
- Inbox UI with three pill states + Why column + bulk confirm flow with undo
- Bbox highlight on the PDF that follows the focused field

**If Day 2 slips, this is the cut-off line. Everything after is icing.**

## Day 3 — Line items (first gated phase)

**Goal at EOD:** Line items extracted with usable accuracy, OR cleanly cut
from demo with reasoning in README.

- Schema extension: `line_items` JSONB array column
- Extraction prompt extended for line items
- PyMuPDF `find_tables()` for digital path; vision handles tables natively
- Line item editable table in review UI
- Run mini-eval on DocILE subset (~20 invoices)
- **Gate:** if error rate >30%, cut from demo seed and document why in
  README. *"Line item extraction is the obvious sub-problem; I tested it, it
  wasn't reliable enough to ship without misleading users — here's the
  failure analysis."* That's a stronger story than half-shipping.

## Day 4 — Per-jurisdiction tax + query/search

**Goal at EOD:** Tax breakdown extracted (or cut); search page works with
structured filters + NL query.

- Schema: `tax_breakdown` JSONB array of `{rate, jurisdiction, amount}`
- Extraction prompt updated for tax breakdown
- Tax breakdown display in review UI
- Same gate as Day 3 — if unreliable, cut and document
- NL query → `StructuredQuery` via Claude tool-use (flat-conjunction
  schema, field whitelist, per-field op compatibility — see ADR-0004).
  Validator rejects malformed LLM outputs. Best-effort partial
  translation: untranslated intent surfaces in an amber notice above
  results, never silently dropped.
- Search page: **chips ARE the state**; NL box is a chip-editor fast-path,
  not a separate state stream. Editing/removing chips re-queries. URL-state
  persistence so deep-links share the exact query (Anchor 1 trust signal).
- FTS via `tsvector` on raw OCR text exposed as the
  `raw_text fts_matches` clause in the schema — NL queries route through
  it naturally; same chip rendering, no parallel UI path.
- CSV/JSON export endpoint + button — exports the current
  `StructuredQuery` results, with the query itself serialized in the
  file header for audit.

## Day 5 — Eval, polish, README, ship

**Goal at EOD:** Submitted.

- DocILE extraction eval harness + `EVAL.md` report (per-field accuracy
  table, per-vendor breakdown, top-10 error examples)
- Synthetic triage corpus (20 invoices: 5 math errors + 5 duplicates +
  5 anomalies + 5 clean) + `TRIAGE-EVAL.md` report
- Calibration plot — composite confidence vs actual accuracy, with a
  secondary line plotting raw LLM self-reported confidence to demonstrate
  the miscalibration the composite model fixes. PNG embedded in `EVAL.md`.
- NL query eval — ~15 hand-curated NL queries with expected
  `StructuredQuery` outputs. Run through the pipeline, diff predicted vs
  expected, report exact-match and per-field accuracy. Lives as a
  section in `EVAL.md` (or separate `NL_EVAL.md` if length warrants).
  Surfaces the failure modes you'd miss in manual demo testing.
- Seed scripts (see Seed corpus section below):
  - `scripts/seed_demo.py` — 25 beat-driven invoices for the demo
  - `scripts/seed_eval.py` — ~50 invoices for EVAL.md / TRIAGE-EVAL.md
  - `scripts/seed_minimal.py` — 5 invoices for `tests/integration/` fixtures
- Vega Logistics arrangement baked into `seed_demo.py`:
  beat-1 hero scan + beat-2 $14,231 anomaly + beat-3 history (3 invoices
  with `field_corrections` rows) + beat-3 payoff invoice
- README from scratch:
  - 60-second demo story (screenshots/GIFs from the demo loop)
  - Architecture diagram
  - Scope-decisions table (in / deliberately out / why)
  - Eval numbers
  - Setup/run instructions
  - Live demo URL
  - Future work with rationale for cuts
- Empty states, loading states, error states pass once-over
- Final deploy and submit

---

## The cut-down ladder

### Protected (never cut — these break the three demo beats)

- **Scanned PDF path** — beat 1 hero
- **bbox-highlight following focused field** — beat 1
- **Anomaly detection + Duplicate detection** — beat 2
- **Typed reason cards** (math_fails, anomaly, duplicate_of, …) + dispatch — beat 2
- **Bulk-confirm** (without undo) — beat 2
- **DuplicateReviewScreen 3-pane** — beat 2 strongest sub-beat
- **`field_corrections` event log + `vendors.memory`** — beat 3
- **Composite confidence + cascade-agreement override** (ADR-0003) — every beat depends on calibrated triage states
- **`ExtractionFailedCard` with Retry + Mark unprocessable** (ADR-0006) — failure-mode floor; without these the demo can dead-end live
- **Inbox + ReviewScreen + chip-filter Search** — minimum UX shell

### Cut in this order if behind schedule. Each cut leaves a working demo:

1. ❌ **Per-jurisdiction tax breakdown** → demote to single `tax_total` field
2. ❌ **NL query box** → keep structured chip filters + FTS only (chip filters preserve Anchor 1's "queryable" promise; NL is the highest-risk surface per ADR-0004 — cleaner story to cut on evidence)
3. ❌ **Line items** → demo with header fields only (existing Day 3 gate)
4. ❌ **CSV/JSON export**
5. ❌ **"Manually enter fields"** mode in `ExtractionFailedCard` (Retry + Mark unprocessable remain — failure path still graceful)
6. ❌ **Bulk-confirm undo affordance** (bulk-confirm itself still ships; clerk re-opens individual rows to revert)
7. ❌ **Field provenance hover tooltips** (source badges remain visible at icon-level)
8. ❌ **Cmd+K "Force Sonnet/Opus" entries** (Cmd+K palette stays for search / jump-to / find-similar)

**Floor:** Day-2 floor + DocILE extraction numbers in EVAL.md + **three
beats hand-walkable on the demo seed** + failure-mode UX intact (Retry +
Mark unprocessable). A reviewer following the 60-second narrative can
complete beats 1, 2, and 3 against the live URL without hitting a broken
screen or a dead-end state.

---

## Above-and-beyond stretches (only if Day 5 has room)

Pick at most one. None worth >2 hours of risk.

- **Active learning** — clerk corrections update per-vendor memory in
  real-time, visibly improving extraction on the next invoice from that
  vendor. The killer demo line.
- **Semantic search via pgvector** — "find invoices similar to this one"
- **Spending dashboard** — small charts for spend-per-vendor-over-time

---

## Risk surface

| Day | Highest risk | Mitigation |
|---|---|---|
| 1 | Fly deploy + Neon connection fights | Deploy a "hello world" first thing, before any feature code |
| 2 | Vision LLM latency / failure modes on scans | Build the cascade carefully; have a manual-extraction fallback button so demo never blocks |
| 3 | Line item extraction unreliable | Pre-decide the cut; don't burn Day 4 on it |
| 4 | NL → SQL has correctness bugs | Pin to a strict schema via tool-use; never run free-form SQL |
| 5 | README undersells the work | Start it on Day 1 and update each EOD |

---

## Pre-grilled non-decisions for execution

Do NOT relitigate during the build — just make the call and move:

- shadcn/ui components straight, no restyling for the first 4 days
- TanStack Query for all server state; no Redux/Zustand
- React Hook Form + Zod for all forms
- structlog + JSON to stdout for logs, nothing else
- Errors: toast via `sonner` + log to stdout
- Tests: pytest + Vitest; skip Playwright unless Day 5 has room

---

## Code architecture (locked Day 1, see ADR-0005)

Four layers, strict one-way deps:

```
api ──→ services ──→ domain ←── adapters
```

```
backend/app/
  api/                # thin route handlers
  services/           # orchestration: extract, query, nl-translate, triage, vendor-memory
  domain/             # pure: models, validators, scoring, triage, cascade, anomalies,
                      # duplicates, nl_schema
  adapters/           # IO seams: llm_client, pdf_reader, storage/*_repo
  prompts/            # versioned prompt files + tool-use JSON schemas
  db/                 # SQLAlchemy models, session, alembic
tests/
  unit/               # against domain — pure, <1s
  integration/        # services with stubbed adapters
  fixtures/

frontend/src/
  routes/             # inbox, review, duplicate-review, search
  components/
    primitives/       # FieldRow, PdfViewerWithBbox, BboxOverlay, ChipFilter, ...
    reason-cards/     # typed dispatch by reason.type
    command-palette/
    shell/
  hooks/              # useKeyboardShortcuts, useUrlState, ...
  state/              # TanStack Query keys + mutations
  types/              # generated from backend Pydantic at build time
  utils/
```

Three load-bearing rules (CI-enforced):

1. **One-way dependency direction** — `import-linter` fails the build
   if `domain/` imports `services/` or `adapters/`, etc.
2. **LLM client lives in `adapters/llm_client.py` only.** One method
   per use case; never a generic `call_claude`.
3. **Prompts + tool-use schemas are versioned files** in
   `app/prompts/`. Content-hashed; hash logged with every LLM call so
   EVAL.md numbers correlate to prompt versions.

## Seed corpus (locked Day 5, scaffolded earlier)

Three seed scripts, separate purposes — **no overlap** between them:

| Script | Purpose | Volume | Visible in |
|---|---|---|---|
| `scripts/seed_demo.py` | The invoices a reviewer clicks through. Each slot has a beat-driven role. Pre-populates `field_corrections` + runs `vendor_memory_service.consolidate(...)` to populate `vendors.memory` — exercising the real active-learning code path, no shadow seed logic. | 25 | Demo DB |
| `scripts/seed_eval.py` | Pipeline inputs for EVAL.md numbers — DocILE subset + adversarial synthetic triage corpus. | ~30 DocILE + 20 synthetic | Eval pass only, never demo |
| `scripts/seed_minimal.py` | Fixture data for `tests/integration/`. Smallest set that exercises all four `predicted_triage_state` values + the `unprocessable` review_status. | 5 | Tests only |

### Demo seed slots (25 invoices, beat-driven)

| Slot | Role | Vendor | Type | Triage | Beat |
|---|---|---|---|---|---|
| 1 | Beat-1 hero — scan, clean extraction, bbox highlight demo | Vega Logistics | Scan | confident | 1 |
| 2-6 | Bulk-confirm batch (must be ≥5 for the moment to feel real) | Acme · Globex · Initech · Hooli · Pied Piper | Digital | confident ×5 | 2 |
| 7 | Math error (subtotal+tax ≠ total, off by $0.40) | Wonka Co. | Digital | needs_review (math_fails) | 2 |
| 8 | Anomaly ($14,231 vs Vega avg $1,180, Z=12.4) | Vega Logistics | Digital | needs_review (anomaly) | 2 |
| 9 | Low confidence on a field (invoice # unreadable on scan) | Cyberdyne | Scan | needs_review (low_confidence) | 2 |
| 10 | Missing field (no tax_total in document) | Soylent Corp. | Digital | needs_review (missing_field) | 2 |
| 11 | Unseen vendor | Stark Industries | Digital | needs_review (unseen_vendor) | 2 |
| 12-13 | Duplicate pair | Tyrell Corp. | Digital | likely_duplicate + confident original | 2 |
| 14 | Unprocessable — encrypted PDF (exercises `ExtractionFailedCard`) | (unknown) | Encrypted | review_status = `unprocessable` | 2 |
| 15-17 | Beat-3 Vega history with `field_corrections` logged | Vega Logistics | 2 digital + 1 scan | confirmed ×3 | 3 |
| 18 | Beat-3 payoff — fresh Vega invoice benefitting from memory (`source: "memory-applied"` on affected fields) | Vega Logistics | Digital | confident (no cascade fired) | 3 |
| 19-25 | Inbox filler — varied vendors / dates / totals | Various | Mix | mostly confident | — |

### PDF sources

- **DocILE subset** for slots 1, 2-6, 9, 19-25 — real invoices, vendor-renamed for narrative consistency.
- **LaTeX-generated synthetics** for slots 7, 8, 10-13, 15-18 — need controlled properties (specific math errors, specific Z-score anomaly, specific Vega name consistency for beat 3). One Jinja+LaTeX template in `scripts/synthetic/` + a YAML config.
- **Encrypted PDF** (slot 14) via `qpdf --encrypt`.

### Out of seed

- **Multi-currency invoices** — explicitly out-of-scope per CONTEXT.md and rung #5 in the cut-down ladder. Mentioned in README's scope-decisions table (text), never as pixels in the demo.

## UX surface (locked Day 1, polished through Day 5)

Three named sub-screens. Each has its own route, its own keyboard map, its
own component tree. Shared primitives (`FieldRow`, `PdfViewerWithBbox`,
`ReasonCardStack`, `BboxOverlay`, `ConfidenceBadge`, `SourceBadge`) live in
a `components/primitives/` folder and are composed by the screens — no
mode-toggle conditionals.

### `InboxScreen` (`/inbox`)

- shadcn `Table`, sticky header, virtualized rows when >100
- Columns: triage pill, vendor, invoice #, date, total, confidence pill,
  Why (typed reason cards on hover), review_status
- **4th pill style for `unprocessable`** (gray, distinct from the three
  triage pills — failed extractions and successful extractions have
  fundamentally different action sets; see ADR-0006)
- `J / K` row navigation, `Space` to multi-select, `Enter` to open review
- Bulk actions toolbar appears with ≥1 selection: Confirm / Dismiss-dupe /
  Mark-unprocessable. Each bulk action shows a `sonner` toast with a
  **10-second client-side undo** — no server-side review_events log needed
  for v1.
- Filters (triage, vendor, date range) live in URL state for deep-links

### `ReviewScreen` (`/invoice/:id`)

- 2-column: PDF viewer on left (PDF.js), fields panel on right
- Active field highlights in panel AND on PDF (bbox overlay; zoom-to-fit
  for small bboxes)
- `Tab / Shift-Tab` walks fields; `E` or `Enter` enters edit mode;
  `Esc` cancels; `Enter` commits
- Each `FieldRow` shows: label · editable value · `ConfidenceBadge` ·
  `SourceBadge` (model / memory-applied / manual-correction)
- Provenance hover on a field reveals: extracted by [model], corrected by
  clerk [date], auto-applied from vendor memory — the visible-in-UI
  evidence of structured memory (Beat 3's static support)
- `ReasonCardStack` at top of fields panel renders typed cards via a
  dispatch table: `{ math_fails, anomaly, duplicate_of, low_confidence,
  missing_field, unseen_vendor }` → component. Each card is actionable
  (e.g. duplicate_of card opens DuplicateReviewScreen)
- Action bar: `C` Confirm · `D` Dismiss · `U` Mark unprocessable
- Typed fields (date, currency, amount) get format validation on commit;
  malformed values rejected inline so they never re-pollute the
  structured store
- **Failure-mode UX (ADR-0006):** when the extraction's
  `predicted_triage_reasons` contains `extraction_failed`, the fields
  panel renders an `ExtractionFailedCard` with: failure stage +
  plain-English detail, and three actions:
  - **Retry** — creates a new `extractions` row, runs full pipeline
  - **Mark unprocessable** — sets `invoices.review_status = unprocessable`
  - **Manually enter fields** — fields panel switches to manual-entry mode
    (reuses `FieldRow` primitives); values are written with
    `source: "manual-entry"` and seed `vendors.memory` for active learning

### `DuplicateReviewScreen` (`/duplicate-review/:id`)

- 3-column: original PDF · new PDF · field diff panel
- Field diff: same-row pairs; matching fields rendered subtly, differing
  fields highlighted; similarity score + match method at top
- Two actions:
  - **Confirm duplicate** → `invoices.review_status = dismissed_duplicate`
    on the new one; original untouched; link logged so the pair is
    auditable
  - **Not a duplicate** → persist a `not_a_duplicate` marker so the same
    pair does not re-fire next month (without this, the duplicate detector
    re-flags forever — broken on the second demo run)
- 1280px minimum width; below that it stacks vertically (PDF — PDF — diff)

### Cross-screen

- `Cmd+K` opens the command palette: "Confirm all visible", "Find similar
  to this", "Show corrections for vendor X", "Jump to invoice #",
  **"Force Sonnet on this invoice"**, **"Force Opus on this invoice"**
  (cascade-on-demand — depth signal for the demo)
- `?` opens a keyboard cheat-sheet overlay
- A single `useKeyboardShortcuts` hook used by all three screens. Vitest
  tests simulate key events against the fixtures.

## Schema sketch (locked Day 1)

```sql
invoices (
  id, file_path, file_hash, perceptual_hash, vendor_id,
  uploaded_at, review_status  -- pending | confirmed | dismissed_duplicate | unprocessable
)

vendors (
  id, name, tax_id, normalized_name, first_seen_at,
  memory JSONB DEFAULT '{}'  -- learned rules + per-vendor stats, see shape below
)

extractions (
  id, invoice_id, model, cascade_trace JSONB,
  extracted_fields JSONB,   -- per-field {value, bbox, page, confidence, source}
  confidence_per_field JSONB,
  predicted_triage_state,   -- confident | needs_review | likely_duplicate
  predicted_triage_reasons JSONB,  -- discriminated union, see shape below
  is_current BOOLEAN, created_at
)
-- partial unique index: (invoice_id) WHERE is_current = TRUE

field_corrections (
  id, extraction_id, field_name,
  original_value, corrected_value, corrected_at
)
```

### `extracted_fields` shape

Each field is an object, not a bare value — so bbox-highlight, confidence
display, and provenance ("came from memory" vs "extracted by model") all
work without retrofitting:

```json
{
  "vendor_name": {
    "value": "Acme Logistics",
    "bbox": [120, 80, 340, 110],
    "page": 0,
    "confidence": 0.92,
    "source": "pymupdf+haiku"   // claude-vision | memory-applied | manual-correction
  }
}
```

### `predicted_triage_reasons` shape (discriminated union)

Typed reason objects drive the Why column's typed reason cards in the UI:

```json
[
  {"type": "math_fails", "subtotal": 1000.00, "tax": 180.00, "total": 1180.40, "delta": 0.40},
  {"type": "anomaly", "field": "total", "vendor_mean": 1180.00, "vendor_std": 142.50, "z_score": 12.4},
  {"type": "duplicate_of", "invoice_id": 17, "similarity": 0.98, "match_method": "perceptual_hash"},
  {"type": "low_confidence", "field": "invoice_number", "score": 0.42, "reason": "format_mismatch"},
  {"type": "missing_field", "field": "tax_breakdown"},
  {"type": "unseen_vendor", "vendor_name": "Acme Logistics"},
  {"type": "extraction_failed", "stage": "cascade_exhausted", "detail": "all required fields missing"}
]
```

### `vendors.memory` shape

Structured learned-rules + cached per-vendor stats. Drives the prompt-hint
on Day 2, the corrections sidebar in beat 3, and the anomaly check:

```json
{
  "rules": [
    {
      "field": "invoice_date",
      "pattern_type": "date_format",
      "value": "DD/MM/YYYY",
      "source_correction_id": 47,
      "applied_count": 3,
      "first_learned_at": "2026-04-12T..."
    }
  ],
  "stats": { "total_seen": 6, "avg_total": 1180.00, "std_total": 142.50 }
}
```

Design notes:
- `predicted_triage_state` is **immutable** per extraction row — preserves the
  eval ground truth. Clerk action mutates `invoices.review_status` instead.
- `extractions` is 1:N to `invoices` to support re-extraction (active
  learning replay) and to store cascade-derived rows (Haiku and Sonnet on
  the same invoice when the cascade fires).
- `field_corrections` is the active-learning event surface; logged from
  Day 2 even though the active-learning feature ships only as a Day 5
  stretch.
- **An extraction row is created for every attempt — success or failure**
  (see ADR-0006). Failed extractions have `extracted_fields = {}` and
  carry an `extraction_failed` reason. This keeps the schema uniform
  and makes failure-rate queryable in EVAL.md.

## Reference

- Locked decisions: [docs/adr/0001](./docs/adr/0001-extraction-pipeline-no-docling.md), [docs/adr/0002](./docs/adr/0002-postgres-on-neon-over-sqlite.md), [docs/adr/0003](./docs/adr/0003-composite-confidence-scoring.md), [docs/adr/0004](./docs/adr/0004-nl-to-sql-structured-query.md), [docs/adr/0005](./docs/adr/0005-layered-architecture.md), [docs/adr/0006](./docs/adr/0006-failure-modes.md)
- Domain language: [CONTEXT.md](./CONTEXT.md)
- Memory: agentmemory `mem_mp32pdn4_49b2e6a3fcdc` (full architectural context, recallable from any session)
