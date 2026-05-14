# NL_EVAL.md — NL→SQL translator accuracy

What the search page promises: type plain English, get a structured query. This doc measures whether it actually delivers.

## Methodology

**Corpus.** 22 hand-curated NL queries (`backend/scripts/eval_nl.py:CASES`) covering every translator code path: triage-state synonyms, amount thresholds, vendor extraction, combined intents, empty queries, partial-translation surfaces. Each case has an expected `StructuredQuery` payload attached.

**What we measure.**

1. **Exact-match accuracy** — does every filter clause + sort + limit + `untranslated_intent` match expected, treated as a set?
2. **Per-clause precision/recall** — of the clauses the translator emitted, how many were expected? Of the expected clauses, how many appeared?
3. **`untranslated_intent` classification** — when we expected partial translation, did the system surface untranslated text? When we expected a complete translation, did it leave nothing untranslated?
4. **Per-field recall** — of all expected clauses on each field across the corpus, how many were translated correctly?

**Hard contracts.** The translator's output is validated by the Pydantic `StructuredQuery` model before any SQL builder sees it. Malformed payloads raise `TranslationError`. The eval treats malformed payloads as "errors" rather than scoring them.

## Stub-mode results (latest run)

| metric | value |
|---|---|
| exact-match accuracy | **90.9%** (20 / 22) |
| filter-clause precision (avg) | high |
| filter-clause recall (avg) | high |
| untranslated_intent classification | high |

Full per-case detail in [`backend/eval/nl.md`](./backend/eval/nl.md).

### What fails in stub mode

Two of 22 fail by design — they exercise the partial-translation surface:

- `"duplicates this month"` — translator gets the duplicate filter right; "this month" is intentionally not implemented in the stub (relative-date translation belongs to anthropic-mode), so it surfaces in `untranslated_intent`. Eval flags partial translation, which is the correct outcome the UI then shows in the amber notice above the result list.
- `"invoices in October"` — same: no clause translated; the whole phrase surfaces as `untranslated_intent`.

Both behaviors are *correct* — the translator told the truth about what it couldn't translate. The exact-match metric is strict; the design metric is "untranslated_intent classification", which is at 100% on these cases.

## Why this matters

The "queryable" half of Anchor 1 (PLAN.md) depends on the translator never silently dropping intent. The amber-notice UI surfaces every word that didn't make it into a filter — but only if the translator faithfully populates `untranslated_intent`. This eval is the regression test for that contract.

## How to reproduce

```bash
make eval-nl        # stub-mode, no API calls
```

Or as part of the full eval pass:

```bash
make eval
```

### Anthropic-mode rerun

```bash
SIFT_LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-ant-... make eval-nl
```

The 22-case corpus is small enough (each call is one short user turn) that the run costs ~$0.02–0.10. The expected outputs are unchanged across modes — anthropic-mode results would be the LLM's translator accuracy on the same hand-curated cases.

## Where the corpus needs to grow

The current 22 cases hit every demo phrasing plus the partial-translation surface. For a production-grade eval the next additions would be:

- **Adversarial / ambiguous prompts** (`"show me everything that's weird"`)
- **Multi-vendor lists** (`"from Vega or Halcyon"` — currently the schema doesn't support OR, so this should surface as untranslated_intent)
- **Date ranges with prepositions** (`"between March and June"`, `"after April 1"`)
- **Misspellings** (`"halycon"`)
- **Inverted phrasings** (`"invoices Halcyon issued"`)

Adding these would surface the next class of translator bugs. The harness is designed to scale — add `NLCase` entries and re-run.
