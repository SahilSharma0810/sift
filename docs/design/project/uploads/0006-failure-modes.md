---
status: accepted
date: 2026-05-13
---

# Failure-mode design — always-create-extraction-rows, auto/manual `unprocessable` split, graceful-degradation via manual entry

## Context

Sift's failure surface has at least seven distinct cases:

1. PDF corrupted / encrypted / password-protected
2. Vision LLM API timeout / rate-limit / 5xx
3. LLM returns valid tool-use but `extracted_fields` is empty
4. LLM extracts but all required fields fail validation
5. Not actually an invoice (resume, contract, photo)
6. Cascade ran all three tiers and they disagreed badly
7. Partial extraction on scan (total readable, vendor unreadable)

The schema has `review_status = unprocessable` but no designed path to
reach it. Anchor 2 (UX non-negotiable) requires that failure modes are
first-class, not afterthoughts. Anchor 1 (queryable structured data)
requires that failures are inspectable and queryable.

## Decision

**Schema: always create an extraction row, even on failure.**

Failed extractions get a row with `extracted_fields = {}` and a typed
reason in `predicted_triage_reasons`:

```json
{
  "type": "extraction_failed",
  "stage": "pdf_read" | "llm_call" | "validation" | "cascade_exhausted",
  "detail": "encrypted PDF" | "API timeout after retries" | "all required fields missing" | "..."
}
```

`extraction_failed` is added to the discriminated union in
`predicted_triage_reasons` (PLAN.md schema sketch) and to the
reason-card dispatch on the frontend.

**Auto vs manual `unprocessable`:**

- Auto-set `review_status = unprocessable` on hard cases only:
  - `pdf_read` failure (corrupted / encrypted / password-protected)
  - `cascade_exhausted` — all three tiers returned empty or invalid
  - `validation` — all required fields missing AND no readable text on
    the page
- Soft cases surface as `needs_review` with the `extraction_failed`
  reason. The clerk decides whether to retry, enter manually, or mark
  unprocessable.

**Retry semantics:**

- **Service-layer auto-retry** on `llm_client` calls for transient
  errors only (timeout, 429, 5xx). Three attempts, exponential backoff.
  Logged with the retry-count attached to the extraction row.
  Invisible to the clerk on success.
- **Manual retry button** on `ReviewScreen` — creates a new
  `extractions` row (1:N pattern already supports it), runs the full
  pipeline again.
- **No cascade-on-retry by default.** Clerk forces a higher tier via
  the Cmd+K palette: "Force Sonnet" / "Force Opus". Depth signal for
  the demo — the clerk *sees* the cascade is real and controllable.

**UX:**

- Same `ReviewScreen` route. Fields panel renders an
  `ExtractionFailedCard` with:
  - Failure stage + plain-English detail
  - Buttons: **Retry · Mark unprocessable · Manually enter fields**
- **"Manually enter fields"** — fields panel switches to manual-entry
  mode reusing the same `FieldRow` primitives. Values are written as
  `source: "manual-entry"` on `extracted_fields`. Invoice transitions
  to `confirmed`. **Also acts as active-learning seed** for the
  vendor — the next invoice from this vendor benefits from the manual
  values via `vendors.memory`.
- **Inbox: 4th pill style for `unprocessable`** — gray, distinct from
  the three `predicted_triage_state` pills (which only apply to
  successful extractions). Why column shows the `extraction_failed`
  reason.

## Considered Options

- **(a) No extraction row on full failure; set
  `invoices.review_status = unprocessable` directly.** Rejected: messy
  for re-extraction (retry would have to create the first row);
  eval-unfriendly (can't query "what failed where").
- **(b) Always create extraction row (chosen).** Schema is uniform;
  retry is just a new row; eval computes extraction failure rate
  trivially.
- **(c) Auto-detect "not an invoice" via a pre-extraction LLM check.**
  Rejected: scope creep; the existing pipeline already handles this
  softly (all fields fail validation → cascade exhausts →
  auto-unprocessable).
- **(d) Skip "Manually enter fields" — clerks mark unprocessable and
  move on.** Rejected: dead-ends the user, forces an external tool,
  contradicts Anchor 1 ("structured data from messy docs" — manual
  entry *is* structuring with Sift as the substrate).
- **(e) Overload one of the three existing pills with the
  extraction_failed reason; no 4th style.** Defensible — saves visual
  surface — but the failure case has a fundamentally different action
  set (Retry/Mark/Manually-enter vs Confirm/Dismiss) and merging them
  creates a "what can I do here?" cognitive cost. Rejected on Anchor 2.

## Consequences

- One new reason type in the discriminated union + one reason card.
- One new service method (`retry_extraction`) + Cmd+K palette entries
  for force-cascade.
- One new inbox pill style for `unprocessable` (4th visual).
- "Manually enter fields" mode in the fields panel — non-trivial UX
  but bounded; reuses `FieldRow` primitives in edit mode.
- Auto-retry rate becomes a useful EVAL.md metric ("LLM client retried
  N% of calls, succeeded on retry M% of the time" — depth signal).
- Always-create-rows means failed extractions have an audit trail.
  Useful for the active-learning stretch and for EVAL.md's
  "what fails most" breakdown.
- Graceful-degradation floor: Sift is always at least as good as a
  manual data-entry tool with a PDF viewer next to it. The product
  doesn't break, even when the LLM does.
