# TRIAGE-EVAL.md — synthetic triage corpus

Day 2's depth bet was triage intelligence: a clerk should be able to tell *why* an invoice needs review without reading the PDF, because the system already wrote the reason card. This doc evaluates that contract.

## Methodology

**Corpus.** A slice of the same 55-invoice synthetic corpus that EVAL.md uses, but the slice focuses on the four triage outcomes most-load-bearing for the demo narrative:

| group | n | what's tested |
|---|---:|---|
| clean | 15 | confident state · vendor history accumulates correctly across the 5 vendors |
| anomaly | 20 | 3-invoice history per vendor seeds vendor stats, then a 4th outlier should fire `anomaly` reason with the right z-score |
| duplicate | 10 | 5 visually-identical pairs — second of each pair must phash-match the first and emit `duplicate_of` |
| unprocessable | 5 | `[stub:fail]` triggers extraction_failed; row goes to `review_status=unprocessable` |

The math-error group is in the corpus but doesn't fire `math_fails` in stub mode (the stub always returns reconciling totals once cascade settles). Real anthropic-mode runs would exercise math_fails properly — the reason path is tested via the unit tests in `backend/tests/unit/test_validators.py`.

**What's correct.** A row passes when:
- `predicted_triage_state` matches expected
- Every expected reason type is present in `predicted_triage_reasons`

Reasons carry typed payloads (z-score, vendor_mean, vendor_std, similarity, match_method, etc.); their *shape* is verified in unit tests, and the eval just checks the reason *types* present.

## Stub-mode results (latest run)

| expected state | n | triage matched | reasons recalled |
|---|---:|---:|---:|
| confident | 40 | 100% | 100% |
| likely_duplicate | 5 | 100% | 100% |
| needs_review | 10 | 100% | 100% |

Confusion matrix:

| expected \ predicted | confident | likely_duplicate | needs_review |
|---|---|---|---|
| **confident** | 40 | 0 | 0 |
| **likely_duplicate** | 0 | 5 | 0 |
| **needs_review** | 0 | 0 | 10 |

55/55 cases pass — the triage code paths (cascade orchestration → composite confidence → anomaly check → duplicate check → derive_triage) compose correctly, end-to-end, against the synthetic corpus.

## What the eval surfaces about the pipeline

**Vendor-history accumulation works.** Anomaly detection requires `total_seen >= 3` per the validator. The eval seeds 3 confirmed invoices per anomaly-vendor before the outlier; the outlier reliably fires `anomaly` with `z_score >> 3` and the right `vendor_mean` / `vendor_std`. That's a strong signal the Welford-style running stats in `vendor_memory_service.update_stats_from_extraction` are correctly populated on confirm.

**Duplicate detection is sensitive enough but not too sensitive.** The 5 pairs share a deterministic visual identity (PDF rendered with same colored rectangles at the same positions). They phash-match. The 40 non-duplicate clean cases use distinct visual identities (per-key hashed positions + colors + glyphs) and do NOT phash-match across pairs. An earlier corpus revision used weaker visual variation and produced 12 false-positive duplicates — fixing the corpus revealed the pipeline was correct; the corpus was too uniform. That's a useful lesson for the real-data eval: visual diversity matters as much as structural diversity.

**Extraction-failed has its own code path.** All 5 unprocessable cases get `extraction_failed` reason at `stage=llm_call` and end up with `review_status=unprocessable` after the eval calls `mark_unprocessable`. The pipeline doesn't try to derive other reasons on top — short-circuit per ADR-0006.

## How to reproduce

```bash
make eval        # writes backend/eval/extraction.md
```

The triage breakdown is in the "Per-triage-state accuracy" and "Triage confusion matrix" sections of the generated report.

## What's missing

- **Math-fails coverage** in stub mode. The stub provider always emits reconciling totals once cascade lands, so the `math_fails` reason path doesn't fire on synthetic data. It IS exercised in unit tests (`backend/tests/unit/test_validators.py::test_math_reconciles`) and integration tests (`backend/tests/integration/test_extraction_service.py::TestExtractFromPdfCascade`). Anthropic-mode eval on real data with crafted math errors would close the loop.
- **Low-confidence-only cases.** Currently the eval doesn't have a row where the cascade ends with a borderline-low composite confidence on a single field but everything else is fine. Worth adding when anthropic-mode eval data shows what real low-confidence looks like.
- **Multiple-reason rows.** Some real invoices stack reasons (anomaly + low_confidence + missing_field). The eval has rows that produce one or two reasons but doesn't isolate "three reasons on the same row" as a category.

The harness scales by adding `EvalCase` entries to `backend/scripts/seed_eval.py`. The reason taxonomy lives in `backend/app/domain/models.py` (`TriageReason` discriminated union).
