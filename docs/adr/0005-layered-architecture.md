---
status: accepted
date: 2026-05-13
---

# Hexagonal-ish layered architecture (domain / services / adapters / api)

## Context

Sift is LLM-heavy: extraction, NL → `StructuredQuery`, plus the
active-learning stretch. Anchor 2 (code quality non-negotiable) sets
the bar, and the codebase will be heavily written-by-LLM with human
review. Two failure modes are pre-emptively in play if we don't impose
a layering discipline:

1. **Sprinkled LLM calls.** Without discipline, `anthropic.Anthropic()`
   gets instantiated wherever convenient. Tests can't run without
   network. Provider swap (ADR-0001 flags Gemini as next-optimization)
   becomes a codebase-wide grep. Prompt drift between routes goes
   silent.
2. **Untestable business logic.** Without a pure domain layer,
   validators / scoring / triage / NL schema get entangled with HTTP
   request objects and DB sessions. Unit tests need a full app context,
   get slow, get skipped, coverage rots.

LLMs are great at writing code *inside* named layers and bad at
deciding the layers in the first place. The layering decision is the
single highest-leverage code-quality investment in the build.

## Decision

Four-layer architecture with strict one-way dependency direction:

```
api ──→ services ──→ domain ←── adapters
```

- **`domain/`** — pure: no IO, no LLM calls, no DB. Pydantic models,
  validators, composite confidence scoring, triage derivation,
  anomaly + duplicate logic, NL → `StructuredQuery` schema and
  validators.
- **`services/`** — orchestration: imports from `domain` and
  `adapters`. No HTTP, no raw SQL. One method per use case
  (`extract_invoice`, `translate_nl_query`, `bulk_confirm_invoices`,
  …).
- **`adapters/`** — the only modules that talk outside the process:
  LLM client, PDF reader, repositories.
- **`api/`** — thin route handlers: parse request → call one service
  method → serialize response. No business logic.

Three load-bearing rules enforced from Day 1:

1. **One-way dependency direction.** Enforced by `import-linter` in
   CI; build fails if `domain/*.py` imports from `services/` or
   `adapters/`, or if `adapters/*.py` imports from `services/`.
2. **LLM client lives in `adapters/llm_client.py`.** Never imported
   from `domain/`. Always imported from `services/`. Exposes one method
   per use case (`extract_header`, `extract_line_items`,
   `translate_nl_query`) — never a generic `call_claude`.
3. **Prompts and tool-use schemas are versioned files** in
   `app/prompts/` and `app/prompts/schemas/`. Loaded once at startup,
   content-hashed, hash logged with every LLM call. Pydantic models in
   `domain/models.py` are validated against the JSON schemas at
   startup — single source of truth between "what we ask the LLM for"
   and "what we validate."

Frontend mirrors with parallel discipline:

- `routes/` for sub-screens.
- `components/primitives/` for screen-agnostic composables
  (FieldRow, PdfViewerWithBbox, ChipFilter, …).
- `components/reason-cards/` for typed reason-card dispatch.
- `hooks/` for shared logic (`useKeyboardShortcuts`, `useUrlState`).
- `state/` for TanStack Query keys + mutations.
- `types/` **generated** from backend Pydantic via
  `pydantic-to-typescript` at build time — eliminates the "model
  changed, TS type didn't" bug class.

## Considered Options

- **(A) Single-file pragma.** `app/extraction.py`, `app/api.py`,
  `app/db.py`. Faster to start; unmaintainable by Day 3; untestable
  at the unit level. Rejected as an explicit Anchor 2 violation.
- **(B) Layered hexagonal-ish (chosen).** Four layers, one-way deps,
  versioned prompts.
- **(C) Full hexagonal/DDD with ports and interfaces for every
  adapter.** Over-engineered for a 5-day demo. Adapter interfaces
  inferred from one consumer; the indirection cost isn't earned.
- **(D) Layered without repository pattern (services do ORM
  directly).** Defensible — collapses ~5 files into `db.py`. Rejected
  because the eval harness specifically benefits from a
  `extraction_repo.save_for_eval(...)` seam; reaching into the ORM
  from test fixtures is messier.
- **(E) Hand-maintained TypeScript types.** Defensible if the type
  surface stays small. Rejected because the surface grows quickly
  (StructuredQuery + FilterClause + ExtractedField + reason union +
  Confidence + triage state + review status…), and the drift-bug
  class shows up by Day 2.

## Consequences

- **~10-12 backend modules of 50-150 LOC each**, not 3 files of 300+.
  Reviewer reads the whole backend in 15 minutes.
- **Unit-test layer is fast and real.** `tests/unit/` against
  `domain/` runs in <1s; covers validators, scoring, triage
  derivation, NL schema validation. The eval harness sits on this
  seam.
- **LLM provider is swappable.** ADR-0001's "Gemini as next
  optimization" becomes one file change in `adapters/llm_client.py`.
- **Prompt versioning gives eval reproducibility.** Every LLM call
  logs prompt-hash + model + temperature. EVAL.md numbers correlate
  to prompt versions, not "whatever was on disk when I ran it."
- **CI cost:** 2 new checks (import-linter for dep direction,
  pydantic-to-typescript build step). Both run in <5s.
- **Slight onboarding cost** for anyone reading the codebase — must
  understand the four layers — but the README's architecture diagram
  on Day 5 makes the shape obvious.
