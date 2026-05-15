# Sift search eval (end-to-end)

Corpus: **15** natural-language queries · runs full pipeline (NL → translate → SQL builder → executor → invoice set).

Ground truth derived from `eval/groundtruth.json` predicates, not hardcoded IDs.

## Headline numbers

| metric | value |
|---|---|
| exact-set-match rate | **66.7%** (10 / 15) |
| set precision (avg) | **83.7%** |
| set recall (avg) | **97.3%** |

## Per-case results

| nl | expected | actual | precision | recall | match |
|---|---:|---:|---:|---:|:-:|
| duplicates | 5 | 4 | 100.0% | 80.0% | ✗ |
| show me likely duplicates | 5 | 4 | 100.0% | 80.0% | ✗ |
| needs review | 10 | 50 | 20.0% | 100.0% | ✗ |
| anomalies | 5 | 5 | 100.0% | 100.0% | ✓ |
| flagged invoices | 5 | 50 | 10.0% | 100.0% | ✗ |
| confirmed | 30 | 30 | 100.0% | 100.0% | ✓ |
| unprocessable | 5 | 5 | 100.0% | 100.0% | ✓ |
| failed to extract | 5 | 5 | 100.0% | 100.0% | ✓ |
| over $5000 | 5 | 5 | 100.0% | 100.0% | ✓ |
| invoices above $1,000 | 30 | 30 | 100.0% | 100.0% | ✓ |
| under $200 | 0 | 0 | 100.0% | 100.0% | ✓ |
| from Atlas Freight | 3 | 3 | 100.0% | 100.0% | ✓ |
| from Fjord Services | 4 | 4 | 100.0% | 100.0% | ✓ |
| anomalies from Fjord Services | 1 | 4 | 25.0% | 100.0% | ✗ |
| confirmed over $1000 | 20 | 20 | 100.0% | 100.0% | ✓ |

## Errors (5 of 15)

| nl | description | false positives | false negatives | error |
|---|---|---|---|---|
| duplicates | triage_state = likely_duplicate | — | `dup-04-near` | — |
| show me likely duplicates | triage_state = likely_duplicate | — | `dup-04-near` | — |
| needs review | triage_state = needs_review | `anom-FJO-h1`, `anom-FJO-h2`, `anom-FJO-h3`, `anom-GIL-h1`, `anom-GIL-h2` _+35_ | — | — |
| flagged invoices | has_anomaly = True | `anom-FJO-h1`, `anom-FJO-h2`, `anom-FJO-h3`, `anom-GIL-h1`, `anom-GIL-h2` _+40_ | — | — |
| anomalies from Fjord Services | has_anomaly = True AND vendor_name = Fjord Services | `anom-FJO-h1`, `anom-FJO-h2`, `anom-FJO-h3` | — | — |

## How to reproduce

```bash
make reset-db
make seed-eval     # seeds the synthetic corpus + ground truth
make eval-search
```

_Stub provider runs offline. To eval the Anthropic translator + SQL executor end-to-end, set `SIFT_LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY=...` and re-run._