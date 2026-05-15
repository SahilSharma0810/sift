# Anomalies — Phase 1 design

**Status:** approved (brainstorming)
**Date:** 2026-05-15
**Scope:** Replace the dead "Anomalies" sidebar entry with a working screen
that surfaces statistical (`amount`-type) anomalies, lets clerks
acknowledge them, and updates the vendor memory so similar values don't
re-flag. Design fidelity per the Claude Design bundle (`anomalies.jsx`).
Other anomaly types — `frequency`, `terms_changed`, `new_line_item` — are
explicit empty states in this phase; each ships in a later phase with its
own spec.

## Why

The `Anomalies` sidebar item in
[`Shell.tsx:111-115`](../../../frontend/src/components/shell/Shell.tsx)
is a stub `<div>` with no link, and the count next to it currently
displays `counts.likely_duplicate` (the wrong number — that's duplicates,
not anomalies). The backend already emits `anomaly`-type triage reasons
([`domain/anomalies.py`](../../../backend/app/domain/anomalies.py),
Z-score ≥ 3σ on `total` per vendor history), but they're only visible
mixed in with other "needs_review" reasons in the inbox. The Anomalies
screen separates them into their own surface with rich evidence
(vendor-history sparkline, severity badge, per-anomaly acknowledgment).

## Decision

Build a dedicated `/anomalies` route with an all-in-one backend endpoint
that returns the cards, the filter counts, and the stat-strip aggregates
in one round trip. Acknowledgment is a per-anomaly action that both
records the ack and appends the value to
`vendor.memory.acknowledged_outliers`, which the detection logic checks
before emitting anomalies on the next extraction.

Phase 1 emits only `subtype="amount"`. The Frequency and Pattern filter
tabs render but always return zero items, with copy that's accurate
about future work.

## Anomaly identity

An anomaly is identified by `(invoice_id, anomaly_subtype, anomaly_field)`.
URL / DTO encoding: `"{invoice_id}:{subtype}:{field}"` —
e.g. `b28480f1-…:amount:total`. UUIDs don't contain colons, so the parse
via `split(":", 2)` is unambiguous.

The reason payload in `extractions.predicted_triage_reasons` currently
uses a flat `type="anomaly"` discriminator. The DTO layer maps that to
the design's more granular `subtype` field; for Phase 1 every anomaly
reason maps to `subtype="amount"`. Phases 2–4 will start emitting
`subtype="frequency"`, `"terms_changed"`, `"new_line_item"` directly
into the reason payload, and the mapping becomes 1:1.

## Data model

### New table `anomaly_acks`

| column | type | notes |
| --- | --- | --- |
| `id` | `uuid` PK | |
| `invoice_id` | `uuid` FK invoices(id) ON DELETE CASCADE | indexed |
| `anomaly_subtype` | `text` | `"amount"` in Phase 1 |
| `anomaly_field` | `text` | e.g. `"total"` |
| `acknowledged_at` | `timestamptz` | server default `now()` |
| `acknowledged_by_user_id` | `uuid` FK users(id) | |
| `notes` | `text` | nullable; reserved for future per-ack annotations |

`UNIQUE(invoice_id, anomaly_subtype, anomaly_field)` prevents duplicate
acks; the acknowledge endpoint is idempotent on conflict (returns the
existing row).

### `vendor.memory.acknowledged_outliers` (JSONB, append-only)

Shape:

```json
{
  "total": [
    {"value": 34062.50, "acked_at": "2026-05-15T15:30:00Z", "invoice_id": "..."}
  ]
}
```

`vendor.memory` is already a JSONB column on `vendors`; the migration
does not need to alter the schema. The service layer writes the new key
when first needed.

## Detection skip logic

`domain/anomalies.py:detect_anomalies` extended with an optional
`acknowledged_outliers: dict[str, list[dict]] | None` kwarg. Before
emitting an anomaly for `(field, value)`, the function checks the acked
list for that field and skips if
`abs(value - acked.value) / max(acked.value, 1.0) < ACK_TOLERANCE_FRAC`
for any entry. The default of `None` preserves existing call sites.

`services/extraction_service.py` reads
`vendor.memory.get("acknowledged_outliers", {})` and passes it in when
calling `detect_anomalies`.

`ACK_TOLERANCE_FRAC = 0.10` is a module-level constant in
`domain/anomalies.py` with a one-line comment explaining the choice. A
vendor that occasionally bills $34K isn't the same as one that suddenly
bills $50K — 10% gives clerks enough latitude that a near-identical
recurring outlier isn't re-flagged, but flags a genuine new outlier.

## API surface

All three endpoints behind `get_current_clerk` (the dependency from the
login backend). `api/anomalies.py -> app.db.session` added to the third
import-linter contract's `ignore_imports` list, matching the pattern
used by `api/invoices.py`, `api/search.py`, and `api/auth.py`.

### `GET /api/anomalies`

Returns:

```python
class AnomaliesResponse(BaseModel):
    anomalies: list[AnomalyOut]
    counts: AnomalyCounts
    aggregates: AnomalyAggregates

class AnomalyOut(BaseModel):
    id: str                              # composite key
    type: Literal["amount"]              # Phase 1 only
    status: Literal["unreviewed", "acknowledged"]
    vendor: str
    invoice_id: UUID
    detected_at: datetime                # = invoice.uploaded_at
    headline: str                        # "$34,062.50 invoice"
    sub: str                             # "4.2σ above rolling average of $7,900"
    z_score: float
    severity: Literal["high", "medium", "low"]
    metric: AnomalyMetric
    history: list[AnomalyHistoryPoint]   # up to 12 points
    avg: float
    diff: None                           # reserved for new_line_item (Phase 4)
    acknowledged_at: datetime | None
    acknowledged_by: str | None          # email

class AnomalyMetric(BaseModel):
    value: float
    currency: str
    unit: str                            # "$" for amount

class AnomalyHistoryPoint(BaseModel):
    value: float
    current: bool = False                # the anomalous data point itself

class AnomalyCounts(BaseModel):
    all: int
    unreviewed: int
    amount: int                          # Phase 1: equals unreviewed
    frequency: int                       # Phase 1: 0
    pattern: int                         # Phase 1: 0
    acknowledged: int

class AnomalyAggregates(BaseModel):
    total_flagged_amount: float          # dominant-currency bucket sum
    total_flagged_currency: str          # ISO code of dominant bucket
    vendors_affected: int                # currency-agnostic
    highest_severity_z: float | None
    highest_severity_vendor: str | None
```

Severity bands:
- `z ≥ 4.0` → `"high"`
- `2.5 ≤ z < 4.0` → `"medium"`
- `1.5 ≤ z < 2.5` → `"low"`

(Current detection threshold is `Z_THRESHOLD = 3.0σ`, so in Phase 1 every
emitted anomaly is at least medium. The wider bands accommodate future
threshold relaxation without an API change.)

### `POST /api/anomalies/{anomaly_id}/acknowledge`

- Path param: composite id `"{invoice_id}:{subtype}:{field}"`.
- Body: `{"notes": "..."}` — optional, persisted, no UI surface in Phase 1.
- Returns: updated `AnomalyOut`.
- Side effects, in one DB transaction:
  1. Insert into `anomaly_acks` (idempotent on UNIQUE conflict: returns existing row).
  2. Append `{"value": ..., "acked_at": ..., "invoice_id": ...}` to
     `vendor.memory.acknowledged_outliers[field]` (creating the list if absent).

Errors:
- 401 if no session.
- 404 if the id doesn't match an active anomaly on the current extraction.
- 422 if the composite id is malformed.

### `POST /api/anomalies/acknowledge-bulk`

- Body: `{"anomaly_ids": [...]}`. Pydantic enforces `min_length=1` and
  `max_length=200`; oversize requests get 422 before any work runs.
- Returns: `{"acknowledged": [AnomalyOut], "failed": [{"id": str, "error": str}]}`.
- Each ack runs independently — one bad id does not roll back the others.
  Each successful ack updates the matching vendor.memory.

### What the list endpoint returns by status

`GET /api/anomalies` returns BOTH unreviewed and acknowledged anomalies
in `anomalies[]`, each with its `status` field. The frontend filters by
status client-side to render each tab. This keeps the API a single
round-trip — the design's tab counter requires knowing about
acknowledged items even when the user is on the Unreviewed tab.

## Dominant-currency aggregate logic

For the stat-strip "Total $ flagged" tile:

1. Group all unreviewed anomalies by currency (from
   `extraction.extracted_fields.currency.value`).
2. Sum `metric.value` within each bucket.
3. Pick the bucket with the largest sum.
4. Return that sum + its currency code.

Buckets that aren't the dominant one are silently dropped from
`total_flagged_amount`. The anomaly cards still surface individually
with their actual currency. `vendors_affected` is computed across ALL
unreviewed anomalies (currency-agnostic).

Edge cases:
- No unreviewed anomalies: `total_flagged_amount=0`,
  `total_flagged_currency="USD"` (harmless default).
- Tie between buckets: sort by currency code ascending and pick the
  first (deterministic).

## Sparkline data source

For each amount anomaly on invoice X for vendor V:

```sql
SELECT
  (e.extracted_fields->'total'->>'value')::float AS total,
  i.uploaded_at
FROM invoices i
JOIN extractions e
  ON e.invoice_id = i.id AND e.is_current = true
WHERE i.vendor_id = :vendor_id
  AND i.review_status = 'confirmed'
  AND i.id != :current_invoice_id
ORDER BY i.uploaded_at DESC
LIMIT 11
```

Result is reversed to chronological order, then the current invoice's
total is appended with `current=true`. So `history` length is at most 12.

If the vendor has fewer than 11 prior confirmed invoices, return what's
available — the SVG sparkline renders a shorter list without padding.
Empty history is possible but unusual: anomaly detection only fires
when `MIN_VENDOR_HISTORY = 3` confirmed invoices already exist.

## Headline + sub copy

Generated in the service layer for consistency across all anomaly
cards:

- For `currency == "USD"`: `headline = f"${value:,.2f} invoice"`
- For other ISO codes: `headline = f"{currency} {value:,.2f} invoice"`
  (e.g. `"EUR 1,250.00 invoice"`)
- `sub = f"{z:.1f}σ above rolling average of {symbol}{avg:,.0f}"`,
  where `symbol = "$"` if USD else `f"{currency} "`.

The design copy says "6-month rolling average". The backend doesn't
restrict by time window (`detect_anomalies` uses all confirmed history),
so the copy stays simply "rolling average" to be accurate. The bundle's
"6-month" was a design-time assumption; we honor the actual backend
behavior.

## Frontend

### New files

- `frontend/src/routes/AnomaliesScreen.tsx` — page composition
- `frontend/src/state/anomalies.ts` — hooks:
  - `useAnomaliesQuery()` — fetches the full response
  - `useAnomalyCountQuery()` — same query, `select: d => d.counts.unreviewed`,
    used by Shell to avoid re-rendering on every mutation
  - `useAcknowledgeAnomaly()` — single
  - `useBulkAcknowledgeAnomalies()` — bulk
- `frontend/src/components/anomalies/AnomalyCard.tsx`
- `frontend/src/components/anomalies/Sparkline.tsx` — SVG; bars for
  `amount`, lines+dots for other types (reserved for Phase 2+)
- `frontend/src/components/anomalies/TypePill.tsx`

### Modified files

- `frontend/src/routes/router.tsx` — add `/anomalies` route under the
  existing `<Shell />` parent (alongside `/inbox`, `/search`, etc.)
- `frontend/src/components/shell/Shell.tsx` — convert the Anomalies
  `<div>` to `<Link to="/anomalies">`; replace
  `counts.likely_duplicate` next to it with
  `useAnomalyCountQuery().data ?? 0`
- `frontend/src/types/generated/domain.ts` — regenerated
- `frontend/tailwind.config.ts` — extend theme with type-pill tokens:

  ```ts
  // semantic, not per-anomaly-type-specific
  'anomaly-amount-fg':    'oklch(0.45 0.13 25)',
  'anomaly-amount-bg':    'oklch(0.96 0.04 25)',
  'anomaly-amount-ring':  'oklch(0.88 0.07 25)',
  'anomaly-frequency-fg': 'oklch(0.42 0.13 290)',
  'anomaly-frequency-bg': 'oklch(0.96 0.04 290)',
  'anomaly-frequency-ring':'oklch(0.88 0.07 290)',
  // reuse existing triage tokens for terms_changed (blue) and
  // new_line_item (amber)
  ```

The design bundle's inline-style JSX is translated to Tailwind utilities
honoring the user's standing rule on Sift (Tailwind-only, declared
theme tokens, no per-screen CSS files).

### Sidebar count strategy

`useAnomalyCountQuery` is the same TanStack Query as
`useAnomaliesQuery` (same `queryKey`) but uses `select` to extract just
the unreviewed count. React Query caches the full response once; Shell
re-renders only when the selected slice changes. No extra round trip.

## Empty states (accurate to capability)

- **Unreviewed / Amount tab, empty:** "Nothing to flag. New anomalies
  surface here as invoices arrive."
- **Frequency tab:** "Sift doesn't yet flag frequency anomalies — coming
  next."
- **Pattern tab:** "Pattern anomalies (terms changed, new line items)
  ship in a later iteration."
- **Acknowledged tab, empty:** "Nothing acknowledged yet."

These are real strings rendered for accurate empty results. The
Frequency/Pattern empty states aren't mocks of a coming feature —
they're honest about what Phase 1 does and doesn't compute.

## Layer placement (ADR-0005)

```
backend/app/
├── domain/
│   ├── anomalies.py            # + acknowledged_outliers skip + ACK_TOLERANCE_FRAC
│   └── anomalies_models.py     # NEW — Pydantic DTOs
├── services/
│   └── anomaly_service.py      # NEW — list, acknowledge, acknowledge_bulk
├── adapters/storage/
│   └── anomaly_repo.py         # NEW — create_ack, vendor_history, acks_lookup
├── api/
│   └── anomalies.py            # NEW — 3 endpoints
├── db/models.py                # + AnomalyAck ORM
└── alembic/versions/           # NEW — anomaly_acks migration
```

All new files respect `api → services → domain ← adapters`. The DTOs go
in `domain/anomalies_models.py` (separate from
`domain/anomalies.py`) to keep detection logic untangled from API
shape. Re-export from `domain/models.py` so
`scripts/generate_types.py` picks them up — same pattern used for
`ClerkOut` / `LoginIn` in the login backend.

## Migration

New Alembic revision: `add_anomaly_acks.py`. Creates `anomaly_acks`,
its FK indexes, and the unique constraint. Downgrade drops cleanly.
`vendor.memory` JSONB is mutated by service-layer writes — no schema
migration there.

## Code style — comments

Match the codebase rule (`feedback_minimal_comments.md`): default to
no comments. Add only when the *why* is non-obvious — e.g. the
`ACK_TOLERANCE_FRAC = 0.10` constant gets a one-line comment because
the chosen tolerance is a design decision a future reader would
question. Most other code has self-documenting names; don't narrate.

## Code style — imports

Alias / absolute only. No relative imports anywhere:

- Frontend TS: `import { Btn } from '@/components/primitives/Btn'`,
  **not** `import { Btn } from '../../components/primitives/Btn'`.
- Backend Python: `from app.adapters.storage.anomaly_repo import create_ack`,
  **not** `from ..adapters.storage.anomaly_repo import create_ack` and
  **not** `from .anomaly_repo import create_ack`.

A repo-wide check both before and after this feature lands:
```bash
grep -rn "from '\.\." frontend/src    # must be empty
grep -rn "^from \." backend/app       # must be empty
```

## Testing

### Unit (`tests/unit/`)

- `test_anomalies.py` (existing) — extend with:
  - acked outlier within tolerance → no anomaly emitted
  - acked outlier outside tolerance → anomaly still emitted
  - empty `acknowledged_outliers` dict → identical to prior behavior
- DTO round-trip tests for AnomalyOut, AnomalyCounts, AnomalyAggregates

### Integration (`tests/integration/`)

- `test_anomaly_repo.py`:
  - `create_ack` inserts; second identical call returns the same row
    (idempotent on UNIQUE conflict)
  - `vendor_history_query` returns up to 11 confirmed invoices ordered
    DESC
  - `acks_lookup` joins correctly

- `test_anomaly_service.py`:
  - `list_anomalies` returns expected counts and aggregates across
    seeded data (multi-vendor, multi-currency)
  - `acknowledge` appends to `vendor.memory.acknowledged_outliers`
    AND inserts ack row in one transaction
  - `acknowledge_bulk` with one bad id returns partial success
  - Aggregate dominant-currency tie-breaking (sort by code)

- `test_anomaly_api.py`:
  - `GET /api/anomalies` without auth → 401
  - `GET /api/anomalies` with auth on empty corpus → empty arrays,
    zero counts
  - `POST /api/anomalies/{id}/acknowledge` round-trip via authed
    TestClient cookie
  - `POST /api/anomalies/acknowledge-bulk` partial success path

## Out of scope (deliberate)

- Anomaly types other than `amount` — Phase 2 (frequency), Phase 3
  (new_line_item), Phase 4 (terms_changed, includes payment-terms
  extraction change)
- Snooze 30d action
- Keyboard shortcuts (A acknowledge / I investigate / S snooze)
- Per-anomaly notes UI (the column exists for forward-compat but no
  input surface in Phase 1)
- Real-time SSE / live anomaly stream
- Audit log of acks or undo
- Per-vendor "always-ack-above-X" auto-ack policies
- Re-extraction effect on existing acks: acks are anchored by
  `(invoice_id, subtype, field)`. If a future re-extraction no longer
  emits the same anomaly key, the ack row stays but becomes orphaned
  (harmless). No cleanup job in Phase 1.
- FX conversion across currencies (Sift's
  [CONTEXT.md](../../../CONTEXT.md) explicitly cuts multi-currency
  reconciliation from scope)
