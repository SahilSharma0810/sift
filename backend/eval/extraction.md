# Sift extraction eval

Corpus size: **55** invoices (synthetic).

## Headline numbers

| metric | value |
|---|---|
| vendor_name exact-match | **100.0%** |
| total exact-match (±$0.50) | **100.0%** |
| triage_state exact-match | **100.0%** |
| expected reasons recall | **100.0%** |

## Per-triage-state accuracy

| expected state | n | triage matched | reasons recalled |
|---|---:|---:|---:|
| confident | 40 | 100.0% | 100.0% |
| likely_duplicate | 5 | 100.0% | 100.0% |
| needs_review | 10 | 100.0% | 100.0% |

## Triage confusion matrix

| expected \\ predicted | confident | likely_duplicate | needs_review |
|---|---|---|---|
| **confident** | 40 | 0 | 0 |
| **likely_duplicate** | 0 | 5 | 0 |
| **needs_review** | 0 | 0 | 10 |

## Errors

None. Every case matched ground truth.

## How to reproduce

```bash
make reset-db
make seed-eval     # seeds the synthetic corpus + ground truth
make eval-extraction
```