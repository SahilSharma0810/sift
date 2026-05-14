# EVAL.md — extraction accuracy

Sift ships with a reproducible evaluation harness. Numbers below come from the same scripts a reviewer can re-run on their own machine.

## Methodology

**Corpus.** A synthetic 55-invoice corpus exercises every code path: clean / anomaly / math-fail / duplicate / unprocessable. Each invoice carries ground-truth metadata (expected vendor, total, triage state, expected reason types). Synthetic-only is deliberate — we generate the PDFs so we can attach ground truth without an annotator. DocILE numbers belong on a later run with real data and per-row human review.

**Pipeline-end-to-end.** Each case is rendered to a real PDF, written to the upload directory, and passed through `extract_from_pdf`. The eval reads back the resulting Extraction row from the DB and diffs it against ground truth. So the numbers measure the *full pipeline*, not just the LLM call: file hashing, has_text branching, header extraction, cascade decisions, bbox resolution, perceptual hashing, vendor history accumulation, duplicate detection, anomaly detection, triage derivation.

**Stub vs anthropic mode.** In stub mode the LLM behaviour is deterministic (regex-keyed scenarios + tier-based variation in `StubLLMClient`), so the numbers tell you whether the *non-LLM* parts of the pipeline correctly assemble the LLM output into the right triage state with the right reasons. In anthropic mode the same corpus would tell you the LLM's accuracy. The corpus is unchanged across modes; the provider switch flips behind the `LLMClient` Protocol.

**What "correct" means per row.** A case passes when:
- `vendor_name` exact-matches expected vendor (or vendor is `Unknown` / null on extraction_failed rows)
- `total` matches within ±$0.50
- `predicted_triage_state` exact-matches expected state
- Every expected reason type is present in `predicted_triage_reasons` (extras don't penalize — the system can emit more detail without being wrong)

## Stub-mode results (latest run)

| metric | value |
|---|---|
| vendor_name exact-match | **100.0%** |
| total exact-match (±$0.50) | **100.0%** |
| triage_state exact-match | **100.0%** |
| expected reasons recall | **100.0%** |

55/55 cases pass. Full per-row detail in [`backend/eval/extraction.md`](./backend/eval/extraction.md); calibration plot in [`backend/eval/calibration.png`](./backend/eval/calibration.png).

The 100% number isn't the headline — what matters is that the *pipeline* is deterministic and reproducible. In stub mode, an unchanged corpus + an unchanged pipeline should produce identical numbers every run. That's the bar Anthropic-mode results have to clear: not "100%", but "the same accuracy on the same corpus run-to-run."

## Calibration

`scripts/eval_extraction.py` writes a calibration plot to `backend/eval/calibration.png`. Bucketed composite-confidence vs. ground-truth correctness — the dashed line is perfect calibration; the solid line is the actual per-bucket correctness rate. In stub mode the composite scorer is very conservative (history defaults to 0.85 for unseen vendors), so most rows cluster in the 0.7–0.9 confidence band.

The composite confidence model (ADR-0003) is `min(structural_score, history_score)` with cascade-agreement override. Its job is to be *more calibrated* than raw LLM self-reported confidence — the calibration plot is how we'd see that materializing once anthropic-mode results come in.

## How to reproduce

```bash
make eval            # = reset-db + seed-eval + eval-extraction + eval-nl
```

The full pipeline takes <30 seconds in stub mode (no API calls). Output lands in `backend/eval/`:

- `groundtruth.json` — the 55-row corpus with expected values
- `extraction.md` — full per-row report
- `calibration.png` — composite-confidence calibration plot
- `nl.md` — NL→SQL translator report (see [NL_EVAL.md](./NL_EVAL.md))

### Anthropic-mode rerun

```bash
SIFT_LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-ant-... make eval
```

Burns ~$0.50–$2.00 in API credits depending on cascade depth across the corpus. The corpus and metrics are unchanged from stub mode; only the LLM behind `LLMClient.extract_header` differs.

## What's not measured here

- **Line items + tax breakdown.** Both Day-3/4 features run through their own LLM methods. Stub mode returns canned items so accuracy in stub mode is uninformative — left for anthropic-mode eval on DocILE.
- **Bounding-box overlay correctness.** Visual fidelity is checked manually during demo recording.
- **Latency / cost.** The cascade trace logged on every extraction has per-tier token usage; aggregate cost reporting is a future addition.

## Honest cuts

PLAN.md gates Day-3 line items and Day-4 tax breakdown on real-LLM accuracy. Both ship as opt-in surfaces (display only, no triage impact) so a graceful cut on bad anthropic-mode numbers is one config flip away. The cut decision plus failure analysis would live here in the next revision.
