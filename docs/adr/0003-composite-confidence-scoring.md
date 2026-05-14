---
status: accepted
date: 2026-05-13
---

# Composite confidence scoring (validator + vendor-history + cascade agreement)

## Context

Confidence per extracted field is the load-bearing concept of Sift's triage
layer:

- It drives the **Triage State** (`confident` / `needs_review` /
  `likely_duplicate`) the AP Clerk sees in the inbox.
- It gates the **tiered model cascade** (Haiku → Sonnet → Opus).
- It is the x-axis of the **calibration plot** in `EVAL.md`.

Naively trusting the LLM's self-reported confidence (a `confidence: float`
field in the tool-use schema) is the easy path and the wrong one. LLMs are
systematically overconfident on plausible-but-wrong extractions — which is
the *exact* failure mode an AP clerk needs to catch. A calibration plot
built on self-reported confidence collapses to a high-confidence wall and
tells no useful story.

## Decision

**Composite confidence per field:**

```
confidence = min(structural_score, history_score)
```

- **`structural_score`** — rule-derived from validators with hard
  floors/ceilings:
  - Math reconciles (subtotal + tax = total) → 1.0 on amount fields, 0.2 if it fails.
  - Required field present and format-valid (date parses, currency in ISO 4217,
    invoice number non-empty) → 1.0, 0.0 if absent or malformed.
  - Fields without a structural rule (vendor name, line-item description)
    inherit a neutral 0.9 ceiling so the history score governs them.
- **`history_score`** — per-vendor Z-score on numeric fields against the
  vendor's prior invoices:
  - `|z| < 1` → 1.0, `|z| < 2` → 0.85, `|z| < 3` → 0.6, else 0.3.
  - Defaults to 0.85 for fields/vendors where history is absent
    (cold-start vendors, non-numeric fields).
- **Cascade-agreement override** — the tiered model cascade
  (Haiku → Sonnet → Opus) triggers on
  `min_field_confidence < 0.7` OR math fails OR unseen vendor. When the
  cascade fires, the disputed fields' confidence is **replaced** by an
  agreement score between the upstream and downstream model outputs (exact
  match → 1.0, mismatch → 0.3). The cascade is not run
  preemptively — it only runs on extractions the composite has already
  flagged.

  > **Note (Day-2 update):** The 0.7 fuzzy-match bucket was evaluated during
  > Day-2 planning and dropped. Two-bucket scoring (1.0 / 0.3) with a Decimal
  > 1-cent tolerance handles the realistic near-match case for amount fields
  > without introducing string-fuzzy heuristics that can't be calibrated
  > cheaply. Revisit if EVAL.md surfaces a class of "almost agrees" that the
  > current logic misclassifies.

LLM self-reported confidence stays in the tool-use schema but is **logged
only**, never used as a triage input. `EVAL.md` plots both curves on the
calibration chart to make the miscalibration story visible.

## Considered Options

- **(a) LLM self-reported confidence only.** Trivially easy. Miscalibrated;
  calibration plot is uninformative; "needs_review reason" surface becomes
  "model uncertain" rather than a specific actionable signal.
- **(b) Validator-derived only.** Calibrated by construction but coarse.
  No per-field signal where validators can't fire (invoice number, vendor
  name, line-item descriptions).
- **(c) Cascaded agreement only.** Real signal, but ~2× cost and latency
  per invoice — must call both models every time, even when the first looked
  confident. Inverts the cascade's purpose.
- **(d) Self-consistency sampling (N samples, temperature > 0).** Strong
  calibrated signal in the literature, but doesn't compose with
  temperature-0 tool-use and only meaningful on free-form fields.
- **(e) Per-vendor Z-score only.** Plays nicely with anomaly detection but
  only works on numeric fields and only for repeat vendors. Cold-start
  invoices get no signal.

The chosen **composite of (b) + (e), with (c) reserved for the cascade
trigger**, combines hard-floor structural calibration with a soft
per-vendor signal, and uses cascaded agreement only where it's needed to
disambiguate.

## Consequences

- Triage reasons surface the **specific** validator or score that fired
  ("subtotal + tax ≠ total (off by $0.40)") rather than a generic "model
  uncertain." Stronger UX signal and a stronger interview story.
- A class of demo failure is eliminated: math-failing extractions are
  **never** marked `confident` — there is no path through the composite
  that allows it.
- Cold-start vendors fall back to a 0.85 default `history_score`, so
  `structural_score` dominates for first-time vendors. Acceptable for v1;
  surfaces in the UI as a "no history yet" badge on the review screen.
- Implementation adds ~100-150 LOC across a validator module and a scorer
  module. Both are pure functions, easy to unit-test, and the test
  fixtures double as the synthetic triage corpus on Day 5.
- The same vendor-history table feeds both `history_score` and anomaly
  detection. Single source of truth, single migration.
