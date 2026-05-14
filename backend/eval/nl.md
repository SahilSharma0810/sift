# Sift NL→SQL translator eval

Corpus: **22** hand-curated natural-language queries.

## Headline numbers

| metric | value |
|---|---|
| exact-match accuracy | **90.9%** |
| filter-clause precision (avg) | **98.5%** |
| filter-clause recall (avg) | **98.5%** |
| untranslated_intent classification | **95.5%** |

## Per-field translation recall

| field | expected | recalled | rate |
|---|---:|---:|---:|
| `has_anomaly` | 3 | 3 | 100.0% |
| `review_status` | 4 | 4 | 100.0% |
| `total` | 5 | 5 | 100.0% |
| `triage_state` | 6 | 6 | 100.0% |
| `vendor_name` | 4 | 3 | 75.0% |

## Per-case detail

| nl | match | expected → actual |
|---|:-:|---|
| duplicates | ✓ | `triage_state eq likely_duplicate` → `triage_state eq likely_duplicate` |
| show me likely duplicates | ✗ | `triage_state eq likely_duplicate` → `triage_state eq likely_duplicate` |
| anomalies | ✓ | `has_anomaly eq True` → `has_anomaly eq True` |
| flagged invoices | ✓ | `has_anomaly eq True` → `has_anomaly eq True` |
| needs review | ✓ | `triage_state eq needs_review` → `triage_state eq needs_review` |
| pending review | ✓ | `triage_state eq needs_review` → `triage_state eq needs_review` |
| confirmed | ✓ | `review_status eq confirmed` → `review_status eq confirmed` |
| encrypted invoices | ✓ | `review_status eq unprocessable` → `review_status eq unprocessable` |
| unprocessable | ✓ | `review_status eq unprocessable` → `review_status eq unprocessable` |
| failed to extract | ✓ | `review_status eq unprocessable` → `review_status eq unprocessable` |
| over $5000 | ✓ | `total gt 5000.0` → `total gt 5000.0` |
| invoices above $1,000 | ✓ | `total gt 1000.0` → `total gt 1000.0` |
| under $200 | ✓ | `total lt 200.0` → `total lt 200.0` |
| less than 50 | ✓ | `total lt 50.0` → `total lt 50.0` |
| from Vega Logistics | ✓ | `vendor_name eq Vega Logistics` → `vendor_name eq Vega Logistics` |
| from Halcyon Software | ✓ | `vendor_name eq Halcyon Software` → `vendor_name eq Halcyon Software` |
| anomalies from Halcyon Software | ✓ | `has_anomaly eq True, vendor_name eq Halcyon Software` → `has_anomaly eq True, vendor_name eq Halcyon Software` |
| duplicates from Vega over $1000 | ✗ | `total gt 1000.0, triage_state eq likely_duplicate, vendor_name eq Vega` → `total gt 1000.0, triage_state eq likely_duplicate, vendor_name eq Vega over` |
| _(empty)_ | ✓ | `—` → `—` |
| show me | ✓ | `—` → `—` |
| duplicates this month | ✓ | `triage_state eq likely_duplicate` → `triage_state eq likely_duplicate` |
| invoices in October | ✓ | `—` → `—` |

## How to reproduce

```bash
make eval-nl
```

_Stub provider runs offline. To eval the Anthropic translator, set `SIFT_LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY=...` and re-run._