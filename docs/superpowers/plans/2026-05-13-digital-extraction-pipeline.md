# Digital PDF Extraction Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upload a digital PDF and see extracted header fields rendered on the review screen — composite confidence + triage state from the full Day-1 happy-path pipeline.

**Architecture:** Four-layer hexagonal-ish (api → services → domain ← adapters) per ADR-0005. Pure domain functions (validators, scoring, triage) drive composite confidence and `predicted_triage_state` without any IO. PyMuPDF adapter reads digital PDFs; Anthropic SDK adapter calls Claude Haiku 4.5 with a versioned tool-use schema. `extraction_service` orchestrates `pdf-read → llm-extract → validate → score → triage → save`. Frontend uses TanStack Query for server state; chips/pills/badges are screen-agnostic primitives.

**Tech Stack:** FastAPI 0.115, SQLAlchemy 2.0 sync, Pydantic 2, Anthropic SDK 0.39, PyMuPDF 1.24, tenacity 9 (retry per ADR-0006), structlog 24, pytest 8. Frontend: React 18, TanStack Query 5, sonner, react-hook-form 7, zod, PDF.js 4.

**Reference docs (already locked):**
- `PLAN.md` — full 5-day plan, schema sketch, UX surface, code architecture
- `CONTEXT.md` — domain language (Invoice / Vendor / AP Clerk / Extraction / Confidence / Triage State / Anomaly / etc.)
- `docs/adr/0001` — extraction pipeline (PyMuPDF + Claude vision)
- `docs/adr/0003` — composite confidence scoring
- `docs/adr/0005` — layered architecture rules
- `docs/adr/0006` — failure modes

**Two non-negotiable anchors driving every choice:**
1. Messy documents → structured, queryable data.
2. UX and code quality are non-negotiable.

---

## File Structure

### Backend — new files

| File | Responsibility |
|---|---|
| `app/domain/validators.py` | Pure math + format + required-field validators → `structural_score` |
| `app/domain/scoring.py` | Composite confidence per ADR-0003 |
| `app/domain/triage.py` | Derive `predicted_triage_state` + typed reason list |
| `app/adapters/pdf_reader.py` | PyMuPDF wrapper — text + bboxes from digital PDFs |
| `app/adapters/llm_client.py` | Anthropic SDK wrapper — `extract_header()` with retry per ADR-0006 |
| `app/prompts/extraction_header_v1.md` | System + user prompt for header extraction (versioned, content-hashed) |
| `app/prompts/schemas/extraction_header_schema.json` | Tool-use JSON schema |
| `app/prompts/__init__.py` | Loader: read prompt files at startup, expose hash |
| `app/adapters/storage/invoice_repo.py` | Invoice CRUD + `find_by_file_hash` |
| `app/adapters/storage/extraction_repo.py` | Extraction CRUD + `mark_current` |
| `app/adapters/storage/vendor_repo.py` | Vendor upsert-by-normalized-name |
| `app/services/extraction_service.py` | Orchestrate pipeline |
| `app/api/invoices.py` | POST upload / GET list / GET one |
| `app/api/extractions.py` | GET current extraction for an invoice |

### Backend — tests + fixtures

| File | Coverage |
|---|---|
| `tests/unit/test_validators.py` | Math, format, required-field validators |
| `tests/unit/test_scoring.py` | Composite confidence per ADR-0003 |
| `tests/unit/test_triage.py` | State derivation across all reason types |
| `tests/integration/test_pdf_reader.py` | PyMuPDF against `tests/fixtures/*.pdf` |
| `tests/integration/test_llm_client.py` | LLM client with mocked Anthropic |
| `tests/integration/test_repos.py` | Repos against real Postgres |
| `tests/integration/test_extraction_service.py` | Full pipeline with mocked LLM, real PG |
| `tests/integration/test_invoices_api.py` | Upload + list + get via TestClient |
| `tests/fixtures/conftest.py` | Pytest fixtures: DB session, sample PDF |
| `tests/fixtures/digital_invoice_clean.pdf` | Hand-crafted clean digital invoice |
| `tests/fixtures/digital_invoice_math_error.pdf` | Subtotal+tax≠total |

### Frontend — new files

| File | Responsibility |
|---|---|
| `src/state/api.ts` | `fetch` wrapper + typed error |
| `src/state/invoices.ts` | TanStack Query hooks: `useInboxQuery`, `useInvoiceQuery`, `useUploadMutation` |
| `src/types/api.ts` | Manual API response types (until `pydantic-to-typescript` codegen catches up) |
| `src/components/primitives/TriagePill.tsx` | Pill rendering per `predicted_triage_state` |
| `src/components/primitives/ConfidenceBadge.tsx` | 0-100% confidence indicator |
| `src/components/primitives/SourceBadge.tsx` | Source provenance icon (model / memory / manual) |
| `src/components/primitives/FieldRow.tsx` | label · value · `ConfidenceBadge` · `SourceBadge` |
| `src/components/primitives/UploadDropzone.tsx` | Drag-and-drop PDF upload with sonner toast |
| `src/components/primitives/PdfViewer.tsx` | PDF.js render — no bbox overlay yet (Day 2) |

### Frontend — modified files

| File | Modification |
|---|---|
| `src/routes/InboxScreen.tsx` | Replace stub: dropzone + invoices table |
| `src/routes/ReviewScreen.tsx` | Replace stub: 2-col PDF + fields panel |

---

## Phase A — Pure domain (TDD)

These tasks are TDD-rigid. Pure functions, no IO. Tests are <10ms each. The `tests/unit/` suite stays under 1 second total.

### Task A.1: Math reconciliation validator

**Files:**
- Create: `backend/app/domain/validators.py`
- Test: `backend/tests/unit/test_validators.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/unit/test_validators.py
"""Validators per ADR-0003 — pure functions producing per-field structural_score.

If math validation fails on amount fields, structural_score on those fields drops
to 0.2 (hard floor). Per ADR-0003 the composite confidence will then pin those
fields to ≤0.2 regardless of vendor history — math-failing extractions can never
be marked `confident`.
"""
from __future__ import annotations

from app.domain.validators import math_reconciles


class TestMathReconciles:
    def test_exact_match(self) -> None:
        assert math_reconciles(subtotal=1000.0, tax=180.0, total=1180.0) is True

    def test_off_by_a_dollar(self) -> None:
        assert math_reconciles(subtotal=1000.0, tax=180.0, total=1181.0) is False

    def test_within_rounding_tolerance(self) -> None:
        # 2-cent tolerance for rounding in scanned/OCRd amounts.
        assert math_reconciles(subtotal=1000.0, tax=180.0, total=1180.01) is True

    def test_negative_amounts_rejected(self) -> None:
        assert math_reconciles(subtotal=-100.0, tax=18.0, total=-82.0) is False
```

- [ ] **Step 2: Run test, verify fails**

```bash
docker compose exec backend uv run pytest tests/unit/test_validators.py -v
```
Expected: `ImportError: cannot import name 'math_reconciles' from 'app.domain.validators'`

- [ ] **Step 3: Implement minimal**

```python
# backend/app/domain/validators.py
"""Pure validators for extracted fields.

Each validator returns a typed result that the scorer consumes. No IO,
no LLM calls, no DB. The eval harness sits on this seam.
"""
from __future__ import annotations

# Rounding tolerance for amount validators — accommodates 1-2 cent OCR drift
# without permitting real reconciliation errors through.
AMOUNT_TOLERANCE = 0.02


def math_reconciles(subtotal: float, tax: float, total: float) -> bool:
    """True if subtotal + tax ≈ total within AMOUNT_TOLERANCE.

    Rejects negative amounts (real invoices never have negative subtotals).
    """
    if subtotal < 0 or tax < 0 or total < 0:
        return False
    return abs((subtotal + tax) - total) <= AMOUNT_TOLERANCE
```

- [ ] **Step 4: Run test, verify passes**

```bash
docker compose exec backend uv run pytest tests/unit/test_validators.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/validators.py backend/tests/unit/test_validators.py
git commit -m "feat(domain): math reconciliation validator with 2-cent tolerance"
```

### Task A.2: Date format validator

**Files:**
- Modify: `backend/app/domain/validators.py`
- Test: `backend/tests/unit/test_validators.py`

- [ ] **Step 1: Write failing test (append to existing file)**

```python
# Add to backend/tests/unit/test_validators.py
from app.domain.validators import is_valid_date


class TestIsValidDate:
    def test_iso_date(self) -> None:
        assert is_valid_date("2026-05-13") is True

    def test_us_format(self) -> None:
        assert is_valid_date("05/13/2026") is True

    def test_uk_format(self) -> None:
        assert is_valid_date("13/05/2026") is True

    def test_garbage(self) -> None:
        assert is_valid_date("not a date") is False

    def test_empty(self) -> None:
        assert is_valid_date("") is False

    def test_none(self) -> None:
        assert is_valid_date(None) is False
```

- [ ] **Step 2: Run test, verify fails**

```bash
docker compose exec backend uv run pytest tests/unit/test_validators.py::TestIsValidDate -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# Add to backend/app/domain/validators.py
from datetime import datetime

DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%B %d, %Y",
    "%d %B %Y",
)


def is_valid_date(value: str | None) -> bool:
    """True if `value` parses as a date in any common invoice format.

    The validator does NOT pick a canonical format — that's the LLM's job and
    a per-vendor memory rule's job. This just answers: is the field
    structurally a date at all?
    """
    if not value:
        return False
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(value, fmt)
            return True
        except ValueError:
            continue
    return False
```

- [ ] **Step 4: Run test, verify passes**

```bash
docker compose exec backend uv run pytest tests/unit/test_validators.py -v
```
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/validators.py backend/tests/unit/test_validators.py
git commit -m "feat(domain): date format validator"
```

### Task A.3: Currency code validator

**Files:**
- Modify: `backend/app/domain/validators.py`
- Test: `backend/tests/unit/test_validators.py`

- [ ] **Step 1: Write failing test**

```python
# Add to backend/tests/unit/test_validators.py
from app.domain.validators import is_valid_currency_code


class TestIsValidCurrencyCode:
    def test_usd(self) -> None:
        assert is_valid_currency_code("USD") is True

    def test_eur(self) -> None:
        assert is_valid_currency_code("EUR") is True

    def test_inr(self) -> None:
        assert is_valid_currency_code("INR") is True

    def test_lowercase(self) -> None:
        assert is_valid_currency_code("usd") is True

    def test_invented(self) -> None:
        assert is_valid_currency_code("ZZZ") is False

    def test_empty(self) -> None:
        assert is_valid_currency_code("") is False
```

- [ ] **Step 2: Run test, verify fails**

Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# Add to backend/app/domain/validators.py
# Common invoice currencies — covers >95% of in-scope cases. Not the full
# ISO 4217 set; not worth the dependency.
COMMON_CURRENCIES = frozenset(
    {
        "USD", "EUR", "GBP", "INR", "CAD", "AUD", "JPY", "CHF", "CNY",
        "SEK", "NOK", "DKK", "SGD", "HKD", "MXN", "BRL", "ZAR",
    }
)


def is_valid_currency_code(value: str | None) -> bool:
    """True if `value` looks like a valid ISO-style currency code."""
    if not value:
        return False
    return value.strip().upper() in COMMON_CURRENCIES
```

- [ ] **Step 4: Run test, verify passes**

Expected: 16 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/validators.py backend/tests/unit/test_validators.py
git commit -m "feat(domain): currency code validator"
```

### Task A.4: Required-fields validator

**Files:**
- Modify: `backend/app/domain/validators.py`
- Test: `backend/tests/unit/test_validators.py`

- [ ] **Step 1: Write failing test**

```python
# Add to backend/tests/unit/test_validators.py
from app.domain.validators import find_missing_required


class TestFindMissingRequired:
    def test_all_present(self) -> None:
        fields = {
            "vendor_name": "Vega Logistics",
            "invoice_number": "INV-001",
            "invoice_date": "2026-05-13",
            "total": 1180.0,
            "currency": "USD",
        }
        assert find_missing_required(fields) == []

    def test_missing_total(self) -> None:
        fields = {
            "vendor_name": "Vega Logistics",
            "invoice_number": "INV-001",
            "invoice_date": "2026-05-13",
            "currency": "USD",
        }
        assert find_missing_required(fields) == ["total"]

    def test_blank_string_counts_as_missing(self) -> None:
        fields = {
            "vendor_name": "",
            "invoice_number": "INV-001",
            "invoice_date": "2026-05-13",
            "total": 1180.0,
            "currency": "USD",
        }
        assert find_missing_required(fields) == ["vendor_name"]

    def test_none_counts_as_missing(self) -> None:
        fields = {
            "vendor_name": "Vega Logistics",
            "invoice_number": None,
            "invoice_date": "2026-05-13",
            "total": 1180.0,
            "currency": "USD",
        }
        assert find_missing_required(fields) == ["invoice_number"]
```

- [ ] **Step 2: Run test, verify fails**

Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# Add to backend/app/domain/validators.py
# Required fields per the Day-1 happy-path extraction shape. Day-3 line-items
# and Day-4 tax_breakdown extend this list at their respective milestones.
REQUIRED_FIELDS = (
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "total",
    "currency",
)


def find_missing_required(fields: dict[str, object]) -> list[str]:
    """Names of required fields that are missing, None, or empty-string."""
    missing: list[str] = []
    for name in REQUIRED_FIELDS:
        value = fields.get(name)
        if value is None or value == "":
            missing.append(name)
    return missing
```

- [ ] **Step 4: Run test, verify passes**

Expected: 20 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/validators.py backend/tests/unit/test_validators.py
git commit -m "feat(domain): required-fields validator"
```

### Task A.5: Structural-score computation

This collapses all the validators into one function: given extracted_fields, return a per-field `structural_score` dict.

**Files:**
- Modify: `backend/app/domain/validators.py`
- Test: `backend/tests/unit/test_validators.py`

- [ ] **Step 1: Write failing test**

```python
# Add to backend/tests/unit/test_validators.py
from app.domain.validators import compute_structural_scores


class TestComputeStructuralScores:
    def test_clean_invoice_all_high(self) -> None:
        fields = {
            "vendor_name": "Vega Logistics",
            "invoice_number": "INV-001",
            "invoice_date": "2026-05-13",
            "subtotal": 1000.0,
            "tax": 180.0,
            "total": 1180.0,
            "currency": "USD",
        }
        scores = compute_structural_scores(fields)
        # Math reconciles → amount fields high.
        assert scores["total"] >= 0.99
        assert scores["subtotal"] >= 0.99
        # Date parses → date field high.
        assert scores["invoice_date"] >= 0.99
        # Currency valid → currency field high.
        assert scores["currency"] >= 0.99

    def test_math_failure_floors_amount_fields(self) -> None:
        fields = {
            "vendor_name": "Vega Logistics",
            "invoice_number": "INV-001",
            "invoice_date": "2026-05-13",
            "subtotal": 1000.0,
            "tax": 180.0,
            "total": 1181.0,  # off
            "currency": "USD",
        }
        scores = compute_structural_scores(fields)
        # Amount fields pinned to 0.2 per ADR-0003.
        assert scores["total"] == 0.2
        assert scores["subtotal"] == 0.2
        assert scores["tax"] == 0.2
        # Other fields unaffected.
        assert scores["invoice_date"] >= 0.99
        assert scores["currency"] >= 0.99

    def test_missing_field_floors_to_zero(self) -> None:
        fields = {
            "vendor_name": "Vega Logistics",
            "invoice_number": "INV-001",
            "invoice_date": "2026-05-13",
            "subtotal": 1000.0,
            "tax": 180.0,
            "total": 1180.0,
            # currency missing
        }
        scores = compute_structural_scores(fields)
        assert scores["currency"] == 0.0

    def test_bad_date_floors_to_zero(self) -> None:
        fields = {
            "vendor_name": "Vega Logistics",
            "invoice_number": "INV-001",
            "invoice_date": "not a date",
            "subtotal": 1000.0,
            "tax": 180.0,
            "total": 1180.0,
            "currency": "USD",
        }
        scores = compute_structural_scores(fields)
        assert scores["invoice_date"] == 0.0

    def test_neutral_ceiling_for_unstructurable_fields(self) -> None:
        # vendor_name has no structural rule that can validate it without
        # vendor history — per ADR-0003 it gets a neutral 0.9 ceiling.
        fields = {
            "vendor_name": "Vega Logistics",
            "invoice_number": "INV-001",
            "invoice_date": "2026-05-13",
            "subtotal": 1000.0,
            "tax": 180.0,
            "total": 1180.0,
            "currency": "USD",
        }
        scores = compute_structural_scores(fields)
        assert scores["vendor_name"] == 0.9
        assert scores["invoice_number"] == 0.9
```

- [ ] **Step 2: Run test, verify fails**

Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# Add to backend/app/domain/validators.py

# Per ADR-0003: fields without a structural rule get a neutral 0.9 ceiling
# so history_score governs them. Math-failing amount fields drop to 0.2.
NEUTRAL_SCORE = 0.9
MATH_FAIL_FLOOR = 0.2
MISSING_OR_INVALID = 0.0
HIGH_SCORE = 1.0

AMOUNT_FIELDS = ("subtotal", "tax", "total")


def compute_structural_scores(fields: dict[str, object]) -> dict[str, float]:
    """Map each known field to a structural_score per ADR-0003.

    Returns a score per REQUIRED_FIELDS entry plus `subtotal` and `tax`.
    """
    scores: dict[str, float] = {}

    # Missing fields → 0.0
    missing = set(find_missing_required(fields))

    # Math reconciliation check — drives amount-field scores.
    math_ok = False
    try:
        math_ok = math_reconciles(
            subtotal=float(fields.get("subtotal", 0) or 0),
            tax=float(fields.get("tax", 0) or 0),
            total=float(fields.get("total", 0) or 0),
        )
    except (TypeError, ValueError):
        math_ok = False

    for field in AMOUNT_FIELDS:
        if field in missing:
            scores[field] = MISSING_OR_INVALID
        elif math_ok:
            scores[field] = HIGH_SCORE
        else:
            scores[field] = MATH_FAIL_FLOOR

    # Date — format-validate.
    if "invoice_date" in missing:
        scores["invoice_date"] = MISSING_OR_INVALID
    else:
        scores["invoice_date"] = (
            HIGH_SCORE if is_valid_date(str(fields.get("invoice_date"))) else MISSING_OR_INVALID
        )

    # Currency — code-validate.
    if "currency" in missing:
        scores["currency"] = MISSING_OR_INVALID
    else:
        scores["currency"] = (
            HIGH_SCORE if is_valid_currency_code(str(fields.get("currency"))) else MISSING_OR_INVALID
        )

    # Fields without a structural rule (vendor_name, invoice_number) get the
    # neutral 0.9 ceiling per ADR-0003 unless missing.
    for field in ("vendor_name", "invoice_number"):
        scores[field] = MISSING_OR_INVALID if field in missing else NEUTRAL_SCORE

    return scores
```

- [ ] **Step 4: Run test, verify passes**

Expected: 25 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/validators.py backend/tests/unit/test_validators.py
git commit -m "feat(domain): composite structural_score per ADR-0003"
```

### Task A.6: Composite confidence scoring

`confidence = min(structural_score, history_score)`. Per ADR-0003, `history_score` defaults to 0.85 when vendor history is absent. This is the public interface the service layer uses.

**Files:**
- Create: `backend/app/domain/scoring.py`
- Test: `backend/tests/unit/test_scoring.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/unit/test_scoring.py
"""Composite confidence per ADR-0003: min(structural, history)."""
from __future__ import annotations

from app.domain.scoring import compute_composite_confidence


class TestCompositeConfidence:
    def test_no_history_falls_back_to_neutral(self) -> None:
        structural = {"total": 1.0, "vendor_name": 0.9}
        history: dict[str, float] = {}  # cold-start vendor
        out = compute_composite_confidence(structural, history)
        # min(1.0, 0.85) = 0.85; min(0.9, 0.85) = 0.85
        assert out["total"] == 0.85
        assert out["vendor_name"] == 0.85

    def test_history_present_takes_min(self) -> None:
        structural = {"total": 1.0}
        history = {"total": 0.6}  # vendor history says this total is unusual
        out = compute_composite_confidence(structural, history)
        assert out["total"] == 0.6

    def test_math_floor_dominates_even_with_perfect_history(self) -> None:
        structural = {"total": 0.2}  # math failed
        history = {"total": 1.0}     # vendor history says normal
        out = compute_composite_confidence(structural, history)
        # Math failure should never be overridden — pinned to 0.2.
        assert out["total"] == 0.2

    def test_missing_field_dominates(self) -> None:
        structural = {"currency": 0.0}
        history = {"currency": 1.0}
        out = compute_composite_confidence(structural, history)
        assert out["currency"] == 0.0
```

- [ ] **Step 2: Run test, verify fails**

```bash
docker compose exec backend uv run pytest tests/unit/test_scoring.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# backend/app/domain/scoring.py
"""Composite confidence per ADR-0003.

    confidence_per_field = min(structural_score, history_score)

`structural_score` comes from app.domain.validators.compute_structural_scores.
`history_score` comes from per-vendor Z-score computation against
vendors.memory.stats — that lives in services/vendor_memory_service.

When history is absent for a field (cold-start vendor, non-numeric field
without a rule), it defaults to 0.85 per ADR-0003.
"""
from __future__ import annotations

# Cold-start default per ADR-0003 — "slightly hedged" so structural_score
# dominates when no per-vendor history exists.
DEFAULT_HISTORY_SCORE = 0.85

# Cascade trigger threshold per ADR-0003.
CASCADE_THRESHOLD = 0.7


def compute_composite_confidence(
    structural: dict[str, float],
    history: dict[str, float],
) -> dict[str, float]:
    """Per-field composite confidence.

    For each field in `structural`, returns min(structural_score, history_score)
    where history_score defaults to DEFAULT_HISTORY_SCORE if not in `history`.
    """
    out: dict[str, float] = {}
    for field, s_score in structural.items():
        h_score = history.get(field, DEFAULT_HISTORY_SCORE)
        out[field] = min(s_score, h_score)
    return out


def should_trigger_cascade(
    confidence: dict[str, float],
    math_passed: bool,
    is_unseen_vendor: bool,
) -> bool:
    """Cascade fires when min_field_confidence < 0.7 OR math fails OR unseen vendor.

    Per ADR-0003. The disputed-field agreement-override logic lives in
    services/extraction_service when the cascade actually runs.
    """
    if not math_passed:
        return True
    if is_unseen_vendor:
        return True
    if not confidence:
        return False
    return min(confidence.values()) < CASCADE_THRESHOLD
```

- [ ] **Step 4: Run test, verify passes**

Expected: 4 passed.

- [ ] **Step 5: Add cascade trigger tests**

```python
# Add to backend/tests/unit/test_scoring.py
from app.domain.scoring import should_trigger_cascade


class TestCascadeTrigger:
    def test_all_confident_no_trigger(self) -> None:
        assert (
            should_trigger_cascade(
                confidence={"total": 0.95, "vendor_name": 0.85},
                math_passed=True,
                is_unseen_vendor=False,
            )
            is False
        )

    def test_low_confidence_triggers(self) -> None:
        assert (
            should_trigger_cascade(
                confidence={"total": 0.5, "vendor_name": 0.85},
                math_passed=True,
                is_unseen_vendor=False,
            )
            is True
        )

    def test_math_failure_always_triggers(self) -> None:
        assert (
            should_trigger_cascade(
                confidence={"total": 0.95},
                math_passed=False,
                is_unseen_vendor=False,
            )
            is True
        )

    def test_unseen_vendor_always_triggers(self) -> None:
        assert (
            should_trigger_cascade(
                confidence={"total": 0.95},
                math_passed=True,
                is_unseen_vendor=True,
            )
            is True
        )
```

- [ ] **Step 6: Run, verify passes**

Expected: 8 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/domain/scoring.py backend/tests/unit/test_scoring.py
git commit -m "feat(domain): composite confidence + cascade trigger per ADR-0003"
```

### Task A.7: Triage state derivation

Given extracted fields + composite confidence + duplicate match + anomaly stats, derive `predicted_triage_state` and the typed reason list.

**Files:**
- Create: `backend/app/domain/triage.py`
- Test: `backend/tests/unit/test_triage.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/unit/test_triage.py
"""Triage state derivation per ADR-0003 + PLAN.md schema sketch.

Output: (predicted_triage_state, predicted_triage_reasons) — both immutable
per extraction row, preserved as eval ground truth.
"""
from __future__ import annotations

from uuid import uuid4

from app.domain.triage import derive_triage


class TestDeriveTriage:
    def _clean_fields(self) -> dict[str, object]:
        return {
            "vendor_name": "Vega Logistics",
            "invoice_number": "INV-001",
            "invoice_date": "2026-05-13",
            "subtotal": 1000.0,
            "tax": 180.0,
            "total": 1180.0,
            "currency": "USD",
        }

    def test_clean_invoice_is_confident(self) -> None:
        state, reasons = derive_triage(
            extracted_fields=self._clean_fields(),
            confidence={"total": 0.95, "vendor_name": 0.85, "invoice_date": 0.99,
                        "currency": 0.99, "subtotal": 0.95, "tax": 0.95,
                        "invoice_number": 0.85},
            math_passed=True,
            is_unseen_vendor=False,
            duplicate_of=None,
        )
        assert state == "confident"
        assert reasons == []

    def test_math_failure_is_needs_review(self) -> None:
        fields = self._clean_fields()
        fields["total"] = 1181.0  # off
        state, reasons = derive_triage(
            extracted_fields=fields,
            confidence={"total": 0.2, "vendor_name": 0.85},
            math_passed=False,
            is_unseen_vendor=False,
            duplicate_of=None,
        )
        assert state == "needs_review"
        assert any(r["type"] == "math_fails" for r in reasons)
        math_reason = next(r for r in reasons if r["type"] == "math_fails")
        assert math_reason["subtotal"] == 1000.0
        assert math_reason["tax"] == 180.0
        assert math_reason["total"] == 1181.0
        assert math_reason["delta"] == 1.0

    def test_duplicate_is_likely_duplicate(self) -> None:
        original_id = uuid4()
        state, reasons = derive_triage(
            extracted_fields=self._clean_fields(),
            confidence={"total": 0.95},
            math_passed=True,
            is_unseen_vendor=False,
            duplicate_of={
                "invoice_id": original_id,
                "similarity": 0.98,
                "match_method": "perceptual_hash",
            },
        )
        assert state == "likely_duplicate"
        dup_reason = next(r for r in reasons if r["type"] == "duplicate_of")
        assert dup_reason["invoice_id"] == original_id
        assert dup_reason["similarity"] == 0.98

    def test_low_confidence_field_is_needs_review(self) -> None:
        state, reasons = derive_triage(
            extracted_fields=self._clean_fields(),
            confidence={"invoice_number": 0.5, "total": 0.95, "vendor_name": 0.85},
            math_passed=True,
            is_unseen_vendor=False,
            duplicate_of=None,
        )
        assert state == "needs_review"
        low = next(r for r in reasons if r["type"] == "low_confidence")
        assert low["field"] == "invoice_number"

    def test_missing_field_is_needs_review(self) -> None:
        fields = self._clean_fields()
        del fields["currency"]
        state, reasons = derive_triage(
            extracted_fields=fields,
            confidence={"currency": 0.0, "total": 0.95},
            math_passed=True,
            is_unseen_vendor=False,
            duplicate_of=None,
        )
        assert state == "needs_review"
        missing = next(r for r in reasons if r["type"] == "missing_field")
        assert missing["field"] == "currency"

    def test_unseen_vendor_attaches_reason_but_state_can_still_be_confident(self) -> None:
        # Per Q3: unseen_vendor is a reason that surfaces but doesn't by itself
        # demote a clean extraction to needs_review.
        state, reasons = derive_triage(
            extracted_fields=self._clean_fields(),
            confidence={"total": 0.95, "vendor_name": 0.85, "invoice_date": 0.99,
                        "currency": 0.99, "subtotal": 0.95, "tax": 0.95,
                        "invoice_number": 0.85},
            math_passed=True,
            is_unseen_vendor=True,
            duplicate_of=None,
        )
        assert state == "confident"
        assert any(r["type"] == "unseen_vendor" for r in reasons)
```

- [ ] **Step 2: Run test, verify fails**

Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# backend/app/domain/triage.py
"""Triage state + reason derivation per PLAN.md schema sketch.

Outputs are written to extractions.predicted_triage_state and
extractions.predicted_triage_reasons (JSONB). Both are immutable per row.

This module is pure: no IO. Anomaly + duplicate detection live in
adjacent domain modules (anomalies.py, duplicates.py); this module only
consumes their results.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.domain.scoring import CASCADE_THRESHOLD


def derive_triage(
    *,
    extracted_fields: dict[str, object],
    confidence: dict[str, float],
    math_passed: bool,
    is_unseen_vendor: bool,
    duplicate_of: dict[str, Any] | None,
    anomalies: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Derive (predicted_triage_state, predicted_triage_reasons).

    Reason types are the discriminated union from app.domain.models:
      math_fails | anomaly | duplicate_of | low_confidence |
      missing_field | unseen_vendor | extraction_failed
    """
    reasons: list[dict[str, Any]] = []

    # 1) Duplicate — strongest signal, supersedes everything else.
    if duplicate_of:
        reasons.append({"type": "duplicate_of", **duplicate_of})
        return "likely_duplicate", reasons

    # 2) Math failure → math_fails reason
    if not math_passed:
        try:
            subtotal = float(extracted_fields.get("subtotal", 0) or 0)
            tax = float(extracted_fields.get("tax", 0) or 0)
            total = float(extracted_fields.get("total", 0) or 0)
            reasons.append(
                {
                    "type": "math_fails",
                    "subtotal": subtotal,
                    "tax": tax,
                    "total": total,
                    "delta": round(abs((subtotal + tax) - total), 2),
                }
            )
        except (TypeError, ValueError):
            pass

    # 3) Anomalies (passed in from caller)
    if anomalies:
        for a in anomalies:
            reasons.append({"type": "anomaly", **a})

    # 4) Missing fields → one reason each
    for field, value in extracted_fields.items():
        if value is None or value == "":
            reasons.append({"type": "missing_field", "field": field})

    # 5) Low confidence fields (below cascade threshold, not zero — zero is "missing")
    for field, score in confidence.items():
        if 0.0 < score < CASCADE_THRESHOLD:
            reasons.append(
                {
                    "type": "low_confidence",
                    "field": field,
                    "score": round(score, 3),
                    "reason": "below_threshold",
                }
            )

    # 6) Unseen vendor — reason only, doesn't gate the state alone.
    if is_unseen_vendor:
        reasons.append(
            {
                "type": "unseen_vendor",
                "vendor_name": str(extracted_fields.get("vendor_name", "")),
            }
        )

    # State derivation: anything in {math_fails, anomaly, missing_field,
    # low_confidence} demotes to needs_review. unseen_vendor alone doesn't.
    blocking_types = {"math_fails", "anomaly", "missing_field", "low_confidence"}
    if any(r["type"] in blocking_types for r in reasons):
        return "needs_review", reasons

    return "confident", reasons
```

- [ ] **Step 4: Run test, verify passes**

```bash
docker compose exec backend uv run pytest tests/unit/test_triage.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Run the full unit suite to confirm no regressions**

```bash
docker compose exec backend uv run pytest tests/unit -q
```
Expected: ~33 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/triage.py backend/tests/unit/test_triage.py
git commit -m "feat(domain): triage state + reason derivation per schema sketch"
```

---

## Phase B — Adapters

### Task B.1: PDF reader (digital path)

**Files:**
- Create: `backend/app/adapters/pdf_reader.py`
- Test: `backend/tests/integration/test_pdf_reader.py`
- Test fixture: `backend/tests/fixtures/digital_invoice_clean.pdf`

- [ ] **Step 1: Generate a fixture PDF via reportlab**

(reportlab is dev-only; we'll add it as a dev dep just for fixture generation.)

```bash
docker compose exec backend uv add --group dev reportlab
```

- [ ] **Step 2: Create a script that generates the fixture (one-shot)**

```python
# backend/tests/fixtures/generate_clean.py
"""One-shot fixture generator. Run: uv run python tests/fixtures/generate_clean.py
The output PDF is checked into the repo; this script just regenerates it.
"""
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

OUT = Path(__file__).with_name("digital_invoice_clean.pdf")


def main() -> None:
    c = canvas.Canvas(str(OUT), pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 720, "Vega Logistics")
    c.setFont("Helvetica", 11)
    c.drawString(72, 700, "Invoice")
    c.drawString(72, 680, "Invoice #: INV-2026-0042")
    c.drawString(72, 660, "Date: 2026-05-13")
    c.drawString(72, 600, "Description: Freight services, April 2026")
    c.drawString(72, 540, "Subtotal: USD 1,000.00")
    c.drawString(72, 520, "Tax (18%): USD 180.00")
    c.drawString(72, 500, "Total: USD 1,180.00")
    c.save()
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
```

```bash
docker compose exec backend uv run python tests/fixtures/generate_clean.py
ls -la backend/tests/fixtures/digital_invoice_clean.pdf
```

- [ ] **Step 3: Write failing test**

```python
# backend/tests/integration/test_pdf_reader.py
"""PDF reader integration test — real PyMuPDF, real fixture PDF.

The adapter has two responsibilities:
1. has_text() — branch logic for path selection per ADR-0001
2. read_digital() — returns text + per-word bboxes for the digital path
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.pdf_reader import has_text, read_digital

FIXTURES = Path(__file__).parents[1] / "fixtures"
CLEAN_PDF = FIXTURES / "digital_invoice_clean.pdf"


@pytest.mark.skipif(not CLEAN_PDF.exists(), reason="run generate_clean.py first")
class TestPdfReader:
    def test_has_text_on_digital(self) -> None:
        assert has_text(CLEAN_PDF) is True

    def test_read_digital_returns_text(self) -> None:
        result = read_digital(CLEAN_PDF)
        assert "Vega Logistics" in result.full_text
        assert "INV-2026-0042" in result.full_text
        assert "1,180.00" in result.full_text or "1180.00" in result.full_text

    def test_read_digital_returns_word_boxes(self) -> None:
        result = read_digital(CLEAN_PDF)
        # At least one word box for "Vega"
        vega_boxes = [w for w in result.words if w.text == "Vega"]
        assert len(vega_boxes) >= 1
        box = vega_boxes[0]
        assert box.bbox[0] < box.bbox[2]  # x0 < x1
        assert box.bbox[1] < box.bbox[3]  # y0 < y1
        assert box.page == 0
```

- [ ] **Step 4: Run test, verify fails**

```bash
docker compose exec backend uv run pytest tests/integration/test_pdf_reader.py -v
```
Expected: `ImportError`.

- [ ] **Step 5: Implement**

```python
# backend/app/adapters/pdf_reader.py
"""Digital-path PDF reader per ADR-0001.

PyMuPDF (`fitz`) extracts text and per-word bounding boxes. The vision path
(`pdf2image` + Claude Sonnet) lives in a sibling adapter, added Day 2.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF


@dataclass(frozen=True, slots=True)
class WordBox:
    text: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1
    page: int


@dataclass(frozen=True, slots=True)
class DigitalRead:
    full_text: str
    words: list[WordBox]
    page_count: int


def has_text(pdf_path: Path) -> bool:
    """True if the PDF has any extractable text on any page.

    Used by extraction_service for path selection: text path vs vision path.
    """
    with fitz.open(pdf_path) as doc:
        for page in doc:
            if page.get_text("text").strip():
                return True
    return False


def read_digital(pdf_path: Path) -> DigitalRead:
    """Extract full text + per-word bboxes from a digital PDF.

    Each word entry is `(x0, y0, x1, y1, text, block_no, line_no, word_no)` —
    we keep just the text + bbox + page index for downstream consumption.
    """
    words: list[WordBox] = []
    full_text_chunks: list[str] = []

    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc):
            full_text_chunks.append(page.get_text("text"))
            for w in page.get_text("words"):
                x0, y0, x1, y1, text, *_ = w
                if text:
                    words.append(
                        WordBox(
                            text=text,
                            bbox=(float(x0), float(y0), float(x1), float(y1)),
                            page=page_index,
                        )
                    )
        page_count = len(doc)

    return DigitalRead(
        full_text="\n".join(full_text_chunks),
        words=words,
        page_count=page_count,
    )
```

- [ ] **Step 6: Run test, verify passes**

Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/adapters/pdf_reader.py backend/tests/integration/test_pdf_reader.py \
    backend/tests/fixtures/generate_clean.py backend/tests/fixtures/digital_invoice_clean.pdf \
    backend/pyproject.toml backend/uv.lock
git commit -m "feat(adapters): PyMuPDF digital path reader with bbox extraction"
```

### Task B.2: Prompt + tool-use schema files

These are versioned files per ADR-0005 rule 3. Content-hashed; hash logged with every LLM call.

**Files:**
- Create: `backend/app/prompts/__init__.py`
- Create: `backend/app/prompts/extraction_header_v1.md`
- Create: `backend/app/prompts/schemas/extraction_header_schema.json`

- [ ] **Step 1: Write the prompt file**

```markdown
<!-- backend/app/prompts/extraction_header_v1.md -->
You are an extraction model for vendor invoices in an accounts-payable workflow.

You receive the full text of one invoice. Extract the **header fields** into the structured tool call. Do **not** extract line items or per-jurisdiction tax breakdowns — those are separate calls in later versions.

Rules:
- If a field is not legibly present in the source, return null. Do not guess.
- Normalize amounts to numbers (no currency symbols, no thousand-separators).
- Normalize currency to its 3-letter ISO code (USD, EUR, GBP, INR, ...).
- Return the original date string exactly as it appears — do not reformat.
- `confidence` is your self-reported per-field certainty (0.0-1.0). It is logged for evaluation but **never trusted** as a triage input by the system.

If the document is clearly not an invoice (resume, contract, blank page, photo), still attempt the extraction so the system can flag it as low-confidence / missing-fields, then mark `extraction_failed: true` at the top level with a brief reason.
```

- [ ] **Step 2: Write the tool-use schema**

```json
{
  "name": "extract_invoice_header",
  "description": "Extract header fields from a single vendor invoice.",
  "input_schema": {
    "type": "object",
    "properties": {
      "vendor_name": { "type": ["string", "null"], "description": "Name of the vendor issuing the invoice." },
      "invoice_number": { "type": ["string", "null"], "description": "Vendor's invoice identifier." },
      "invoice_date": { "type": ["string", "null"], "description": "Date of the invoice, as it appears in the document." },
      "subtotal": { "type": ["number", "null"] },
      "tax": { "type": ["number", "null"] },
      "total": { "type": ["number", "null"] },
      "currency": { "type": ["string", "null"], "description": "3-letter ISO currency code (USD, EUR, ...)." },
      "confidence": {
        "type": "object",
        "description": "Self-reported per-field confidence — LOGGED, NEVER TRUSTED for triage.",
        "additionalProperties": { "type": "number", "minimum": 0, "maximum": 1 }
      },
      "extraction_failed": { "type": "boolean", "default": false },
      "extraction_failure_reason": { "type": ["string", "null"] }
    },
    "required": ["vendor_name", "invoice_number", "invoice_date", "subtotal", "tax", "total", "currency"]
  }
}
```

- [ ] **Step 3: Implement the loader**

```python
# backend/app/prompts/__init__.py
"""Versioned prompt loader per ADR-0005 rule 3.

Content-hashed at startup; the hash is included in every LLM call log so
EVAL.md numbers correlate to specific prompt versions.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).parent
SCHEMA_DIR = PROMPT_DIR / "schemas"


@dataclass(frozen=True, slots=True)
class LoadedPrompt:
    name: str
    body: str
    body_hash: str
    schema: dict
    schema_hash: str


def _hash(s: str | bytes) -> str:
    data = s.encode() if isinstance(s, str) else s
    return hashlib.sha256(data).hexdigest()[:16]


@lru_cache(maxsize=8)
def load(name: str) -> LoadedPrompt:
    """Load a versioned prompt + its tool-use schema.

    Example: load("extraction_header_v1") returns the prompt body and the
    extraction_header_schema.json contents (schema filename is canonical:
    `<base>_schema.json` where base strips the `_v\\d+` suffix).
    """
    prompt_path = PROMPT_DIR / f"{name}.md"
    body = prompt_path.read_text()

    base = name.rsplit("_v", 1)[0]
    schema_path = SCHEMA_DIR / f"{base}_schema.json"
    schema_text = schema_path.read_text()
    schema = json.loads(schema_text)

    return LoadedPrompt(
        name=name,
        body=body,
        body_hash=_hash(body),
        schema=schema,
        schema_hash=_hash(schema_text),
    )
```

- [ ] **Step 4: Add a smoke test for the loader**

```python
# backend/tests/unit/test_prompts.py
from app.prompts import load


def test_extraction_header_v1_loads() -> None:
    p = load("extraction_header_v1")
    assert p.name == "extraction_header_v1"
    assert "vendor invoices" in p.body.lower()
    assert p.schema["name"] == "extract_invoice_header"
    assert len(p.body_hash) == 16
    assert len(p.schema_hash) == 16


def test_load_is_cached() -> None:
    a = load("extraction_header_v1")
    b = load("extraction_header_v1")
    assert a is b  # same cached object
```

- [ ] **Step 5: Run test, verify passes**

```bash
docker compose exec backend uv run pytest tests/unit/test_prompts.py -v
```
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/prompts/ backend/tests/unit/test_prompts.py
git commit -m "feat(prompts): versioned + content-hashed extraction_header_v1"
```

### Task B.3: LLM client adapter

Adapter wraps Anthropic SDK. Exposes one method per use case (`extract_header`) — never a generic `call_claude`. Service-layer auto-retry per ADR-0006 (tenacity, transient errors only). Prompt-caching on the system block.

**Files:**
- Create: `backend/app/adapters/llm_client.py`
- Test: `backend/tests/integration/test_llm_client.py`

- [ ] **Step 1: Write failing test (with Anthropic SDK mocked)**

```python
# backend/tests/integration/test_llm_client.py
"""LLM client adapter — tests with Anthropic SDK mocked.

Live LLM calls are run by the eval harness, not the unit/integration suite.
This test verifies:
- Tool-use is correctly assembled from the versioned prompt + schema
- Prompt caching is enabled on the system block
- The extracted fields are returned cleanly
- Retry fires on transient errors per ADR-0006
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.adapters.llm_client import ExtractionResult, LLMClient


@pytest.fixture
def fake_tool_response() -> dict:
    return {
        "vendor_name": "Vega Logistics",
        "invoice_number": "INV-2026-0042",
        "invoice_date": "2026-05-13",
        "subtotal": 1000.0,
        "tax": 180.0,
        "total": 1180.0,
        "currency": "USD",
        "confidence": {
            "vendor_name": 0.95,
            "invoice_number": 0.99,
            "invoice_date": 0.98,
            "subtotal": 0.99,
            "tax": 0.99,
            "total": 0.99,
            "currency": 0.95,
        },
        "extraction_failed": False,
    }


def _make_messages_mock(tool_input: dict) -> MagicMock:
    """Build a MagicMock that mimics anthropic.Anthropic().messages.create."""
    response = MagicMock()
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.name = "extract_invoice_header"
    tool_use_block.input = tool_input
    response.content = [tool_use_block]
    response.usage = MagicMock(input_tokens=500, output_tokens=80,
                               cache_creation_input_tokens=400,
                               cache_read_input_tokens=0)
    response.stop_reason = "tool_use"
    response.model = "claude-haiku-4-5"
    return response


class TestLLMClientExtractHeader:
    def test_extract_header_happy_path(self, fake_tool_response: dict) -> None:
        client_mock = MagicMock()
        client_mock.messages.create.return_value = _make_messages_mock(fake_tool_response)

        with patch("app.adapters.llm_client.Anthropic", return_value=client_mock):
            client = LLMClient(api_key="test")
            result = client.extract_header(invoice_text="any text", model="claude-haiku-4-5")

        assert isinstance(result, ExtractionResult)
        assert result.fields["vendor_name"] == "Vega Logistics"
        assert result.fields["total"] == 1180.0
        assert result.self_reported_confidence["total"] == 0.99
        assert result.model == "claude-haiku-4-5"
        assert result.prompt_hash != ""

    def test_prompt_caching_on_system_block(self, fake_tool_response: dict) -> None:
        client_mock = MagicMock()
        client_mock.messages.create.return_value = _make_messages_mock(fake_tool_response)

        with patch("app.adapters.llm_client.Anthropic", return_value=client_mock):
            client = LLMClient(api_key="test")
            client.extract_header(invoice_text="text", model="claude-haiku-4-5")

        kwargs = client_mock.messages.create.call_args.kwargs
        system = kwargs["system"]
        # System is a list of blocks; the cached block has cache_control.
        assert isinstance(system, list)
        assert any(b.get("cache_control") == {"type": "ephemeral"} for b in system)

    def test_retry_on_transient_error(self, fake_tool_response: dict) -> None:
        from anthropic import APITimeoutError

        client_mock = MagicMock()
        client_mock.messages.create.side_effect = [
            APITimeoutError(request=MagicMock()),
            _make_messages_mock(fake_tool_response),
        ]

        with patch("app.adapters.llm_client.Anthropic", return_value=client_mock):
            client = LLMClient(api_key="test")
            result = client.extract_header(invoice_text="text", model="claude-haiku-4-5")

        assert result.fields["vendor_name"] == "Vega Logistics"
        assert client_mock.messages.create.call_count == 2
```

- [ ] **Step 2: Run test, verify fails**

Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# backend/app/adapters/llm_client.py
"""Anthropic SDK wrapper per ADR-0005.

One method per use case — never a generic call_claude. Prompt + tool-use
schema come from app.prompts (versioned, content-hashed). Service-layer
auto-retry on transient errors per ADR-0006.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from anthropic import (
    Anthropic,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    RateLimitError,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.prompts import LoadedPrompt, load

log = structlog.get_logger(__name__)

TRANSIENT = (APITimeoutError, APIConnectionError, RateLimitError)


def _is_transient_status(exc: BaseException) -> bool:
    """True for 5xx, false otherwise — APIStatusError covers HTTP errors."""
    return isinstance(exc, APIStatusError) and 500 <= exc.status_code < 600


_retry_decorator = retry(
    retry=retry_if_exception_type(TRANSIENT) | retry_if_exception_type(APIStatusError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    fields: dict[str, Any]
    self_reported_confidence: dict[str, float]
    extraction_failed: bool
    extraction_failure_reason: str | None
    model: str
    prompt_hash: str
    schema_hash: str
    usage: dict[str, int]


class LLMClient:
    """Adapter for Anthropic SDK. Imported only from services."""

    def __init__(self, api_key: str) -> None:
        self._client = Anthropic(api_key=api_key)

    @_retry_decorator
    def extract_header(
        self,
        *,
        invoice_text: str,
        model: str,
        prompt_name: str = "extraction_header_v1",
    ) -> ExtractionResult:
        """Extract header fields via tool-use. Prompt-cached system block.

        Per ADR-0006: tenacity retries on transient errors (timeout, 429, 5xx)
        — up to 3 attempts, exponential backoff.
        """
        prompt: LoadedPrompt = load(prompt_name)

        system = [
            {
                "type": "text",
                "text": prompt.body,
                "cache_control": {"type": "ephemeral"},  # prompt-cache the system block
            }
        ]

        tool = {
            "name": prompt.schema["name"],
            "description": prompt.schema["description"],
            "input_schema": prompt.schema["input_schema"],
        }

        log.info(
            "llm.extract_header.start",
            model=model,
            prompt_hash=prompt.body_hash,
            schema_hash=prompt.schema_hash,
            input_chars=len(invoice_text),
        )

        response = self._client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": invoice_text}],
        )

        tool_input: dict[str, Any] | None = None
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool["name"]:
                tool_input = block.input
                break

        if tool_input is None:
            raise RuntimeError("LLM did not emit the extract_invoice_header tool call")

        confidence = tool_input.pop("confidence", {}) or {}
        failed = bool(tool_input.pop("extraction_failed", False))
        failure_reason = tool_input.pop("extraction_failure_reason", None)

        usage_obj = getattr(response, "usage", None)
        usage = {
            "input_tokens": getattr(usage_obj, "input_tokens", 0),
            "output_tokens": getattr(usage_obj, "output_tokens", 0),
            "cache_creation_input_tokens": getattr(
                usage_obj, "cache_creation_input_tokens", 0
            ),
            "cache_read_input_tokens": getattr(
                usage_obj, "cache_read_input_tokens", 0
            ),
        }

        log.info(
            "llm.extract_header.done",
            model=model,
            prompt_hash=prompt.body_hash,
            usage=usage,
            extraction_failed=failed,
        )

        return ExtractionResult(
            fields=tool_input,
            self_reported_confidence=confidence,
            extraction_failed=failed,
            extraction_failure_reason=failure_reason,
            model=response.model,
            prompt_hash=prompt.body_hash,
            schema_hash=prompt.schema_hash,
            usage=usage,
        )
```

- [ ] **Step 4: Run test, verify passes**

```bash
docker compose exec backend uv run pytest tests/integration/test_llm_client.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/adapters/llm_client.py backend/tests/integration/test_llm_client.py
git commit -m "feat(adapters): LLMClient.extract_header with prompt-cache + tenacity retry"
```

---

## Phase C — Storage repos

Repos talk to SQLAlchemy. Tests run against the real Postgres container (via the `db` fixture, which uses a per-test transaction that rolls back).

### Task C.1: Test fixtures + DB session

**Files:**
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Write the conftest**

```python
# backend/tests/conftest.py
"""Shared pytest fixtures.

`db_session` opens a SQLAlchemy session bound to the running Postgres
container and rolls back at the end of each test — so tests can write
freely without polluting state.
"""
from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from app.db.session import SessionLocal


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()
```

- [ ] **Step 2: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test: shared db_session fixture with per-test rollback"
```

### Task C.2: Vendor repo (upsert by normalized name)

**Files:**
- Create: `backend/app/adapters/storage/vendor_repo.py`
- Test: `backend/tests/integration/test_repos.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/integration/test_repos.py
"""Storage repo tests — against real Postgres."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.adapters.storage.vendor_repo import upsert_by_normalized_name


class TestVendorRepo:
    def test_upsert_creates_when_absent(self, db_session: Session) -> None:
        v = upsert_by_normalized_name(db_session, name="Vega Logistics")
        assert v.id is not None
        assert v.name == "Vega Logistics"
        assert v.normalized_name == "vega logistics"
        assert v.memory == {}  # default empty per schema

    def test_upsert_returns_existing(self, db_session: Session) -> None:
        v1 = upsert_by_normalized_name(db_session, name="Vega Logistics")
        v2 = upsert_by_normalized_name(db_session, name="vega logistics ")  # different case+space
        assert v1.id == v2.id

    def test_normalize_strips_punctuation(self, db_session: Session) -> None:
        v1 = upsert_by_normalized_name(db_session, name="Acme, Inc.")
        v2 = upsert_by_normalized_name(db_session, name="Acme Inc")
        assert v1.id == v2.id
```

- [ ] **Step 2: Run test, verify fails**

```bash
docker compose exec backend uv run pytest tests/integration/test_repos.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# backend/app/adapters/storage/vendor_repo.py
"""Vendor repository. Imported by services, not by api directly."""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Vendor

_PUNCT_RE = re.compile(r"[^\w\s]+")
_SPACES_RE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Lowercase + strip punctuation + collapse whitespace.

    The normalized form is the join key for upsert. The original is preserved
    in `vendors.name` (display value).
    """
    n = name.strip().lower()
    n = _PUNCT_RE.sub("", n)
    n = _SPACES_RE.sub(" ", n).strip()
    return n


def upsert_by_normalized_name(session: Session, *, name: str, tax_id: str | None = None) -> Vendor:
    """Insert if absent, return existing otherwise. Match by normalized_name."""
    normalized = normalize_name(name)
    existing = session.execute(
        select(Vendor).where(Vendor.normalized_name == normalized)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    vendor = Vendor(name=name, normalized_name=normalized, tax_id=tax_id)
    session.add(vendor)
    session.flush()
    return vendor
```

- [ ] **Step 4: Run test, verify passes**

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/adapters/storage/vendor_repo.py backend/tests/integration/test_repos.py
git commit -m "feat(repo): vendor upsert by normalized name"
```

### Task C.3: Invoice repo

**Files:**
- Create: `backend/app/adapters/storage/invoice_repo.py`
- Test: append to `backend/tests/integration/test_repos.py`

- [ ] **Step 1: Write failing test**

```python
# Append to backend/tests/integration/test_repos.py
from app.adapters.storage.invoice_repo import (
    create_invoice,
    find_by_file_hash,
    list_invoices,
)


class TestInvoiceRepo:
    def test_create_and_fetch(self, db_session: Session) -> None:
        v = upsert_by_normalized_name(db_session, name="Vega Logistics")
        inv = create_invoice(
            db_session,
            file_path="/data/uploads/abc.pdf",
            file_hash="hash-abc",
            vendor_id=v.id,
        )
        assert inv.id is not None
        assert inv.review_status == "pending"

        found = find_by_file_hash(db_session, "hash-abc")
        assert found is not None
        assert found.id == inv.id

    def test_find_by_file_hash_returns_none_when_absent(self, db_session: Session) -> None:
        assert find_by_file_hash(db_session, "nope") is None

    def test_list_invoices_orders_by_uploaded_desc(self, db_session: Session) -> None:
        v = upsert_by_normalized_name(db_session, name="Vega Logistics")
        a = create_invoice(db_session, file_path="/a", file_hash="ha", vendor_id=v.id)
        b = create_invoice(db_session, file_path="/b", file_hash="hb", vendor_id=v.id)
        invoices = list_invoices(db_session, limit=10)
        # b is newer, should be first
        assert invoices[0].id == b.id
        assert invoices[1].id == a.id
```

- [ ] **Step 2: Run test, verify fails**

Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# backend/app/adapters/storage/invoice_repo.py
"""Invoice repository."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Invoice


def create_invoice(
    session: Session,
    *,
    file_path: str,
    file_hash: str,
    vendor_id: UUID | None,
    perceptual_hash: str | None = None,
) -> Invoice:
    inv = Invoice(
        file_path=file_path,
        file_hash=file_hash,
        vendor_id=vendor_id,
        perceptual_hash=perceptual_hash,
        review_status="pending",
    )
    session.add(inv)
    session.flush()
    return inv


def find_by_file_hash(session: Session, file_hash: str) -> Invoice | None:
    return session.execute(
        select(Invoice).where(Invoice.file_hash == file_hash)
    ).scalar_one_or_none()


def get_invoice(session: Session, invoice_id: UUID) -> Invoice | None:
    return session.get(Invoice, invoice_id)


def list_invoices(session: Session, *, limit: int = 100) -> list[Invoice]:
    """Newest first — drives the Inbox view ordering."""
    return list(
        session.execute(
            select(Invoice).order_by(Invoice.uploaded_at.desc()).limit(limit)
        ).scalars()
    )
```

- [ ] **Step 4: Run test, verify passes**

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/adapters/storage/invoice_repo.py backend/tests/integration/test_repos.py
git commit -m "feat(repo): invoice CRUD + find_by_file_hash + list"
```

### Task C.4: Extraction repo

**Files:**
- Create: `backend/app/adapters/storage/extraction_repo.py`
- Test: append to `backend/tests/integration/test_repos.py`

- [ ] **Step 1: Write failing test**

```python
# Append to backend/tests/integration/test_repos.py
from app.adapters.storage.extraction_repo import (
    create_extraction,
    get_current_extraction,
    mark_current,
)


class TestExtractionRepo:
    def test_create_and_get_current(self, db_session: Session) -> None:
        v = upsert_by_normalized_name(db_session, name="Vega Logistics")
        inv = create_invoice(db_session, file_path="/x", file_hash="hx", vendor_id=v.id)
        ext = create_extraction(
            db_session,
            invoice_id=inv.id,
            model="claude-haiku-4-5",
            extracted_fields={"vendor_name": {"value": "Vega", "confidence": 0.95, "source": "pymupdf+haiku"}},
            confidence_per_field={"vendor_name": 0.85},
            predicted_triage_state="confident",
            predicted_triage_reasons=[],
            cascade_trace={},
        )
        current = get_current_extraction(db_session, invoice_id=inv.id)
        assert current is not None
        assert current.id == ext.id

    def test_mark_current_demotes_previous(self, db_session: Session) -> None:
        v = upsert_by_normalized_name(db_session, name="Vega Logistics")
        inv = create_invoice(db_session, file_path="/y", file_hash="hy", vendor_id=v.id)
        first = create_extraction(
            db_session,
            invoice_id=inv.id,
            model="claude-haiku-4-5",
            extracted_fields={},
            confidence_per_field={},
            predicted_triage_state="confident",
            predicted_triage_reasons=[],
            cascade_trace={},
        )
        second = create_extraction(
            db_session,
            invoice_id=inv.id,
            model="claude-sonnet-4-6",
            extracted_fields={},
            confidence_per_field={},
            predicted_triage_state="confident",
            predicted_triage_reasons=[],
            cascade_trace={},
        )
        # Second is now current; first should be demoted.
        db_session.refresh(first)
        db_session.refresh(second)
        assert first.is_current is False
        assert second.is_current is True
```

- [ ] **Step 2: Run test, verify fails**

Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# backend/app/adapters/storage/extraction_repo.py
"""Extraction repository.

Per Q3: extractions is 1:N. The partial unique index in the DB enforces
"at most one current per invoice"; this module's `create_extraction`
demotes any prior current row in the same transaction.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Extraction


def create_extraction(
    session: Session,
    *,
    invoice_id: UUID,
    model: str,
    extracted_fields: dict[str, Any],
    confidence_per_field: dict[str, float],
    predicted_triage_state: str,
    predicted_triage_reasons: list[dict[str, Any]],
    cascade_trace: dict[str, Any],
) -> Extraction:
    """Create a new extraction and mark it `is_current=True`.

    Demotes any previously-current extraction for the same invoice in the
    same flush — preserves the partial-unique constraint without races.
    """
    # Demote previous current (if any).
    session.execute(
        update(Extraction)
        .where(Extraction.invoice_id == invoice_id, Extraction.is_current.is_(True))
        .values(is_current=False)
    )

    ext = Extraction(
        invoice_id=invoice_id,
        model=model,
        extracted_fields=extracted_fields,
        confidence_per_field=confidence_per_field,
        predicted_triage_state=predicted_triage_state,
        predicted_triage_reasons=predicted_triage_reasons,
        cascade_trace=cascade_trace,
        is_current=True,
    )
    session.add(ext)
    session.flush()
    return ext


def get_current_extraction(session: Session, *, invoice_id: UUID) -> Extraction | None:
    return session.execute(
        select(Extraction).where(
            Extraction.invoice_id == invoice_id, Extraction.is_current.is_(True)
        )
    ).scalar_one_or_none()


def mark_current(session: Session, *, extraction_id: UUID) -> None:
    """Manual override — promote a specific row, demoting siblings."""
    ext = session.get(Extraction, extraction_id)
    if ext is None:
        raise LookupError(f"extraction {extraction_id} not found")
    session.execute(
        update(Extraction)
        .where(Extraction.invoice_id == ext.invoice_id)
        .values(is_current=False)
    )
    ext.is_current = True
    session.flush()
```

- [ ] **Step 4: Run test, verify passes**

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/adapters/storage/extraction_repo.py backend/tests/integration/test_repos.py
git commit -m "feat(repo): extraction CRUD + atomic mark_current"
```

---

## Phase D — Service orchestration

### Task D.1: Extraction service — digital path

Composes pdf_reader + llm_client + validators + scoring + triage + repos. Service-level integration test mocks the LLM but exercises everything else.

**Files:**
- Create: `backend/app/services/extraction_service.py`
- Test: `backend/tests/integration/test_extraction_service.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/integration/test_extraction_service.py
"""Extraction service — full pipeline with mocked LLM, real DB."""
from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.adapters.llm_client import ExtractionResult
from app.services.extraction_service import extract_from_pdf

FIXTURES = Path(__file__).parents[1] / "fixtures"
CLEAN_PDF = FIXTURES / "digital_invoice_clean.pdf"


def _fake_llm_result() -> ExtractionResult:
    return ExtractionResult(
        fields={
            "vendor_name": "Vega Logistics",
            "invoice_number": "INV-2026-0042",
            "invoice_date": "2026-05-13",
            "subtotal": 1000.0,
            "tax": 180.0,
            "total": 1180.0,
            "currency": "USD",
        },
        self_reported_confidence={"total": 0.99, "vendor_name": 0.95},
        extraction_failed=False,
        extraction_failure_reason=None,
        model="claude-haiku-4-5",
        prompt_hash="hashabc",
        schema_hash="hashdef",
        usage={"input_tokens": 500, "output_tokens": 80, "cache_creation_input_tokens": 400, "cache_read_input_tokens": 0},
    )


class TestExtractFromPdf:
    def test_happy_path_creates_invoice_and_confident_extraction(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        # Copy the fixture into the test's temp dir so file_path is unique.
        test_pdf = tmp_path / "test.pdf"
        test_pdf.write_bytes(CLEAN_PDF.read_bytes())

        with patch(
            "app.services.extraction_service.LLMClient.extract_header",
            return_value=_fake_llm_result(),
        ):
            result = extract_from_pdf(db_session, pdf_path=test_pdf)

        # Returns the invoice + current extraction
        assert result.invoice.review_status == "pending"
        assert result.extraction.predicted_triage_state == "confident"
        assert result.extraction.is_current is True
        # Composite confidence applied (history default 0.85 on cold-start vendor)
        assert result.extraction.confidence_per_field["total"] == 0.85

    def test_duplicate_file_returns_existing_invoice(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        test_pdf = tmp_path / "dup.pdf"
        test_pdf.write_bytes(CLEAN_PDF.read_bytes())

        with patch(
            "app.services.extraction_service.LLMClient.extract_header",
            return_value=_fake_llm_result(),
        ):
            r1 = extract_from_pdf(db_session, pdf_path=test_pdf)
            r2 = extract_from_pdf(db_session, pdf_path=test_pdf)
        # Same file → same invoice (file_hash dedup).
        assert r1.invoice.id == r2.invoice.id
```

- [ ] **Step 2: Run test, verify fails**

```bash
docker compose exec backend uv run pytest tests/integration/test_extraction_service.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement**

```python
# backend/app/services/extraction_service.py
"""Extraction service — orchestrates the digital happy path.

Pipeline: hash + dedupe → pdf-read → llm-extract → validate → score →
triage → save. The vision path lands Day 2; the cascade lands Day 2.

Per ADR-0005, this module imports from domain + adapters + db.session.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import structlog
from sqlalchemy.orm import Session

from app.adapters.llm_client import LLMClient
from app.adapters.pdf_reader import has_text, read_digital
from app.adapters.storage import extraction_repo, invoice_repo, vendor_repo
from app.config import get_settings
from app.db.models import Extraction, Invoice
from app.domain.scoring import compute_composite_confidence
from app.domain.triage import derive_triage
from app.domain.validators import compute_structural_scores, math_reconciles

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ExtractResult:
    invoice: Invoice
    extraction: Extraction


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _build_extracted_fields(
    raw: dict, structural: dict[str, float], confidence: dict[str, float], model: str
) -> dict:
    """Build the per-field ExtractedField shape from raw LLM output.

    Bbox is left None on the digital happy path for now; Day-2 bbox-follow
    wires the fuzzy-match from word boxes.
    """
    source = f"pymupdf+{model.split('-')[1] if '-' in model else model}"
    return {
        field: {
            "value": raw.get(field),
            "bbox": None,
            "page": 0,
            "confidence": confidence.get(field, 0.0),
            "source": source,
        }
        for field in (
            "vendor_name",
            "invoice_number",
            "invoice_date",
            "subtotal",
            "tax",
            "total",
            "currency",
        )
    }


def extract_from_pdf(session: Session, *, pdf_path: Path) -> ExtractResult:
    """Run the full Day-1 happy-path pipeline on a single digital PDF."""
    settings = get_settings()

    # 1. Hash + dedupe
    file_hash = _hash_file(pdf_path)
    existing = invoice_repo.find_by_file_hash(session, file_hash)
    if existing is not None:
        current = extraction_repo.get_current_extraction(session, invoice_id=existing.id)
        if current is not None:
            log.info("extraction.dedup_hit", invoice_id=str(existing.id))
            return ExtractResult(invoice=existing, extraction=current)

    # 2. PDF path branch — Day 1 digital path only.
    if not has_text(pdf_path):
        raise NotImplementedError("Vision path lands Day 2 — this PDF has no embedded text")
    pdf = read_digital(pdf_path)

    # 3. LLM extract.
    llm = LLMClient(api_key=settings.anthropic_api_key)
    llm_result = llm.extract_header(
        invoice_text=pdf.full_text, model=settings.model_tier_1
    )

    # 4. Validate + score.
    structural = compute_structural_scores(llm_result.fields)
    math_ok = math_reconciles(
        subtotal=float(llm_result.fields.get("subtotal") or 0),
        tax=float(llm_result.fields.get("tax") or 0),
        total=float(llm_result.fields.get("total") or 0),
    )
    # Day 1 has no per-vendor history yet, so history scores are all default.
    confidence = compute_composite_confidence(structural, history={})

    # 5. Upsert vendor.
    vendor_name = llm_result.fields.get("vendor_name") or "Unknown"
    vendor = vendor_repo.upsert_by_normalized_name(session, name=vendor_name)
    is_unseen = vendor.memory == {}  # cold-start

    # 6. Triage state + reasons.
    state, reasons = derive_triage(
        extracted_fields=llm_result.fields,
        confidence=confidence,
        math_passed=math_ok,
        is_unseen_vendor=is_unseen,
        duplicate_of=None,  # Day 2 wires duplicate detection
    )

    # 7. Save invoice + extraction.
    invoice = invoice_repo.create_invoice(
        session,
        file_path=str(pdf_path),
        file_hash=file_hash,
        vendor_id=vendor.id,
    )
    extracted_fields_shape = _build_extracted_fields(
        llm_result.fields, structural, confidence, llm_result.model
    )
    extraction = extraction_repo.create_extraction(
        session,
        invoice_id=invoice.id,
        model=llm_result.model,
        extracted_fields=extracted_fields_shape,
        confidence_per_field=confidence,
        predicted_triage_state=state,
        predicted_triage_reasons=reasons,
        cascade_trace={
            "tiers": [
                {
                    "model": llm_result.model,
                    "prompt_hash": llm_result.prompt_hash,
                    "schema_hash": llm_result.schema_hash,
                    "usage": llm_result.usage,
                    "llm_self_confidence": llm_result.self_reported_confidence,
                }
            ]
        },
    )
    session.commit()

    log.info(
        "extraction.complete",
        invoice_id=str(invoice.id),
        triage_state=state,
        n_reasons=len(reasons),
    )
    return ExtractResult(invoice=invoice, extraction=extraction)
```

- [ ] **Step 4: Run test, verify passes**

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/extraction_service.py backend/tests/integration/test_extraction_service.py
git commit -m "feat(service): extract_from_pdf pipeline (digital, no cascade yet)"
```

---

## Phase E — API

### Task E.1: Upload + list + get-invoice endpoints

**Files:**
- Create: `backend/app/api/invoices.py`
- Test: `backend/tests/integration/test_invoices_api.py`
- Modify: `backend/app/main.py` to mount the router

- [ ] **Step 1: Write failing test**

```python
# backend/tests/integration/test_invoices_api.py
"""API integration tests via FastAPI TestClient.

These exercise the route → service → repo → DB stack. The LLM client is
patched at the import site in services/extraction_service.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.adapters.llm_client import ExtractionResult
from app.main import app

FIXTURES = Path(__file__).parents[1] / "fixtures"
CLEAN_PDF = FIXTURES / "digital_invoice_clean.pdf"


def _fake_llm_result() -> ExtractionResult:
    return ExtractionResult(
        fields={
            "vendor_name": "Vega Logistics",
            "invoice_number": "INV-2026-0042",
            "invoice_date": "2026-05-13",
            "subtotal": 1000.0,
            "tax": 180.0,
            "total": 1180.0,
            "currency": "USD",
        },
        self_reported_confidence={"total": 0.99},
        extraction_failed=False,
        extraction_failure_reason=None,
        model="claude-haiku-4-5",
        prompt_hash="hash",
        schema_hash="hash",
        usage={"input_tokens": 500, "output_tokens": 80, "cache_creation_input_tokens": 400, "cache_read_input_tokens": 0},
    )


@pytest.fixture
def client(db_session) -> TestClient:
    # db_session fixture is unused here; TestClient drives its own session.
    return TestClient(app)


class TestUploadInvoice:
    def test_upload_returns_invoice_with_extraction(self, client: TestClient) -> None:
        with patch(
            "app.services.extraction_service.LLMClient.extract_header",
            return_value=_fake_llm_result(),
        ):
            with CLEAN_PDF.open("rb") as fh:
                res = client.post(
                    "/api/invoices",
                    files={"file": ("clean.pdf", fh, "application/pdf")},
                )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["review_status"] == "pending"
        assert body["current_extraction"]["predicted_triage_state"] == "confident"
        assert "Vega Logistics" in str(body["current_extraction"]["extracted_fields"])

    def test_upload_rejects_non_pdf(self, client: TestClient) -> None:
        res = client.post(
            "/api/invoices",
            files={"file": ("oops.txt", b"hello", "text/plain")},
        )
        assert res.status_code == 415

    def test_list_returns_uploaded(self, client: TestClient) -> None:
        with patch(
            "app.services.extraction_service.LLMClient.extract_header",
            return_value=_fake_llm_result(),
        ):
            with CLEAN_PDF.open("rb") as fh:
                client.post(
                    "/api/invoices",
                    files={"file": ("clean2.pdf", fh, "application/pdf")},
                )
        res = client.get("/api/invoices")
        assert res.status_code == 200
        body = res.json()
        assert len(body) >= 1
```

- [ ] **Step 2: Run test, verify fails**

```bash
docker compose exec backend uv run pytest tests/integration/test_invoices_api.py -v
```
Expected: 404 (route not mounted).

- [ ] **Step 3: Implement the router**

```python
# backend/app/api/invoices.py
"""POST /api/invoices  — upload + extract
GET  /api/invoices       — list newest-first
GET  /api/invoices/{id} — single invoice + current extraction

Thin route handlers per ADR-0005 — parse request, call one service method,
serialize response.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.adapters.storage import extraction_repo, invoice_repo
from app.config import get_settings
from app.db.models import Invoice
from app.db.session import get_session
from app.domain.models import ExtractionOut, InvoiceOut
from app.services.extraction_service import extract_from_pdf

router = APIRouter()


def _serialize(invoice: Invoice, session: Session) -> InvoiceOut:
    current = extraction_repo.get_current_extraction(session, invoice_id=invoice.id)
    current_out: ExtractionOut | None = None
    if current is not None:
        current_out = ExtractionOut.model_validate(
            {
                "id": current.id,
                "invoice_id": current.invoice_id,
                "model": current.model,
                "cascade_trace": current.cascade_trace,
                "extracted_fields": current.extracted_fields,
                "confidence_per_field": current.confidence_per_field,
                "predicted_triage_state": current.predicted_triage_state,
                "predicted_triage_reasons": current.predicted_triage_reasons,
                "is_current": current.is_current,
                "created_at": current.created_at,
            }
        )
    return InvoiceOut(
        id=invoice.id,
        file_path=invoice.file_path,
        file_hash=invoice.file_hash,
        perceptual_hash=invoice.perceptual_hash,
        vendor_id=invoice.vendor_id,
        uploaded_at=invoice.uploaded_at,
        review_status=invoice.review_status,  # type: ignore[arg-type]
        current_extraction=current_out,
    )


@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def upload_invoice(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> InvoiceOut:
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="only application/pdf is accepted",
        )

    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    raw = file.file.read()
    file_hash = hashlib.sha256(raw).hexdigest()
    target = settings.upload_dir / f"{file_hash}.pdf"
    if not target.exists():
        target.write_bytes(raw)

    result = extract_from_pdf(session, pdf_path=target)
    return _serialize(result.invoice, session)


@router.get("", response_model=list[InvoiceOut])
def list_invoices_endpoint(session: Session = Depends(get_session)) -> list[InvoiceOut]:
    invoices = invoice_repo.list_invoices(session, limit=200)
    return [_serialize(inv, session) for inv in invoices]


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice_endpoint(
    invoice_id: UUID, session: Session = Depends(get_session)
) -> InvoiceOut:
    inv = invoice_repo.get_invoice(session, invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="not found")
    return _serialize(inv, session)
```

- [ ] **Step 4: Mount the router**

```python
# Modify backend/app/main.py — replace the commented-out section
    # Routers will be mounted here as they come online:
    from app.api import invoices
    app.include_router(invoices.router, prefix="/api/invoices", tags=["invoices"])
```

- [ ] **Step 5: Run test, verify passes**

```bash
docker compose exec backend uv run pytest tests/integration/test_invoices_api.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Run the full backend suite**

```bash
docker compose exec backend uv run pytest -q
```
Expected: ~25+ passed.

- [ ] **Step 7: Verify import-linter still passes**

```bash
docker compose exec backend uv run lint-imports
```
Expected: contracts kept.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/invoices.py backend/app/main.py backend/tests/integration/test_invoices_api.py
git commit -m "feat(api): POST/GET /api/invoices with file-hash dedup"
```

### Task E.2: Generate frontend TypeScript types

Per ADR-0005 rule 3, the frontend types are generated from backend Pydantic. Run the script and verify the output.

**Files:**
- Modify: `frontend/src/types/generated/domain.ts` (generated)

- [ ] **Step 1: Run the generator**

```bash
docker compose exec backend uv run python /app/../scripts/generate_types.py
```
Expected: writes `frontend/src/types/generated/domain.ts`.

- [ ] **Step 2: Verify the file exists and has expected exports**

```bash
grep "InvoiceOut\|ExtractionOut\|TriageReason" frontend/src/types/generated/domain.ts | head
```
Expected: matches found.

- [ ] **Step 3: Commit (the generated file is checked in so CI can diff for freshness)**

```bash
git add frontend/src/types/generated/domain.ts
git commit -m "build: generated frontend TS types from backend Pydantic"
```

---

## Phase F — Frontend wiring

### Task F.1: TanStack Query state hooks

**Files:**
- Create: `frontend/src/state/api.ts`
- Create: `frontend/src/state/invoices.ts`

- [ ] **Step 1: Implement the fetch helper**

```typescript
// frontend/src/state/api.ts
/**
 * Base fetch wrapper. Throws `ApiError` on non-2xx; JSON-decodes the body.
 */

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly body?: unknown
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function api<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    let body: unknown
    try {
      body = await res.json()
    } catch {
      body = await res.text().catch(() => undefined)
    }
    throw new ApiError(res.status, `${init?.method ?? 'GET'} ${path} → ${res.status}`, body)
  }
  return res.json() as Promise<T>
}
```

- [ ] **Step 2: Implement the invoice query hooks**

```typescript
// frontend/src/state/invoices.ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type { InvoiceOut } from '@/types/generated/domain'

import { api } from './api'

const KEYS = {
  inbox: ['invoices'] as const,
  invoice: (id: string) => ['invoices', id] as const,
}

export function useInboxQuery() {
  return useQuery({
    queryKey: KEYS.inbox,
    queryFn: () => api<InvoiceOut[]>('/api/invoices'),
  })
}

export function useInvoiceQuery(id: string | undefined) {
  return useQuery({
    queryKey: id ? KEYS.invoice(id) : ['invoices', '__none__'],
    queryFn: () => api<InvoiceOut>(`/api/invoices/${id}`),
    enabled: !!id,
  })
}

export function useUploadMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api<InvoiceOut>('/api/invoices', { method: 'POST', body: form })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.inbox })
    },
  })
}
```

- [ ] **Step 3: Type-check**

```bash
docker compose exec frontend pnpm tsc --noEmit
```
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/state/api.ts frontend/src/state/invoices.ts
git commit -m "feat(state): TanStack Query hooks for invoices + upload"
```

### Task F.2: Primitives — TriagePill, ConfidenceBadge, SourceBadge, FieldRow

**Files:**
- Create: `frontend/src/components/primitives/TriagePill.tsx`
- Create: `frontend/src/components/primitives/ConfidenceBadge.tsx`
- Create: `frontend/src/components/primitives/SourceBadge.tsx`
- Create: `frontend/src/components/primitives/FieldRow.tsx`

- [ ] **Step 1: TriagePill (4 styles per ADR-0006)**

```typescript
// frontend/src/components/primitives/TriagePill.tsx
import { cn } from '@/utils/cn'

type Variant = 'confident' | 'needs_review' | 'likely_duplicate' | 'unprocessable'

const LABELS: Record<Variant, string> = {
  confident: 'Confident',
  needs_review: 'Needs review',
  likely_duplicate: 'Likely duplicate',
  unprocessable: 'Unprocessable',
}

const COLORS: Record<Variant, string> = {
  confident: 'bg-triage-confident/15 text-triage-confident',
  needs_review: 'bg-triage-needs-review/15 text-triage-needs-review',
  likely_duplicate: 'bg-triage-duplicate/15 text-triage-duplicate',
  unprocessable: 'bg-triage-unprocessable/15 text-triage-unprocessable',
}

export function TriagePill({ variant }: { variant: Variant }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        COLORS[variant]
      )}
    >
      {LABELS[variant]}
    </span>
  )
}
```

- [ ] **Step 2: ConfidenceBadge**

```typescript
// frontend/src/components/primitives/ConfidenceBadge.tsx
import { cn } from '@/utils/cn'

export function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const tone =
    pct >= 85 ? 'text-triage-confident'
    : pct >= 60 ? 'text-triage-needs-review'
    : 'text-destructive'
  return (
    <span className={cn('inline-flex items-center text-xs tabular-nums', tone)}>
      {pct}%
    </span>
  )
}
```

- [ ] **Step 3: SourceBadge**

```typescript
// frontend/src/components/primitives/SourceBadge.tsx
import { Bot, Brain, PenLine, Sparkles } from 'lucide-react'

import { cn } from '@/utils/cn'

const CONFIG: Record<
  string,
  { Icon: typeof Bot; label: string; tone: string }
> = {
  'pymupdf+haiku': { Icon: Bot, label: 'Haiku 4.5', tone: 'text-muted-foreground' },
  'claude-vision': { Icon: Sparkles, label: 'Sonnet 4.6', tone: 'text-muted-foreground' },
  'memory-applied': { Icon: Brain, label: 'From vendor memory', tone: 'text-primary' },
  'manual-correction': { Icon: PenLine, label: 'Clerk-corrected', tone: 'text-primary' },
  'manual-entry': { Icon: PenLine, label: 'Manually entered', tone: 'text-primary' },
}

export function SourceBadge({ source }: { source: string }) {
  const cfg = CONFIG[source] ?? CONFIG['pymupdf+haiku']
  const { Icon, label, tone } = cfg
  return (
    <span
      title={label}
      className={cn('inline-flex items-center gap-1 text-xs', tone)}
    >
      <Icon className="h-3 w-3" />
      <span className="sr-only">{label}</span>
    </span>
  )
}
```

- [ ] **Step 4: FieldRow**

```typescript
// frontend/src/components/primitives/FieldRow.tsx
import type { ExtractedField } from '@/types/generated/domain'

import { ConfidenceBadge } from './ConfidenceBadge'
import { SourceBadge } from './SourceBadge'

export function FieldRow({
  label,
  field,
}: {
  label: string
  field: ExtractedField | null | undefined
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b py-2 last:border-b-0">
      <div className="text-sm font-medium text-muted-foreground">{label}</div>
      <div className="flex items-center gap-3">
        <div className="text-sm tabular-nums">
          {field?.value !== null && field?.value !== undefined ? String(field.value) : '—'}
        </div>
        {field && <ConfidenceBadge value={field.confidence} />}
        {field && <SourceBadge source={field.source} />}
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Add a smoke test for TriagePill**

```typescript
// frontend/src/components/primitives/TriagePill.test.tsx
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TriagePill } from './TriagePill'

describe('TriagePill', () => {
  it('renders the unprocessable variant', () => {
    const { getByText } = render(<TriagePill variant="unprocessable" />)
    expect(getByText('Unprocessable')).toBeInTheDocument()
  })

  it('renders the confident variant', () => {
    const { getByText } = render(<TriagePill variant="confident" />)
    expect(getByText('Confident')).toBeInTheDocument()
  })
})
```

- [ ] **Step 6: Run frontend tests**

```bash
docker compose exec frontend pnpm vitest run
```
Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/primitives/
git commit -m "feat(primitives): TriagePill, ConfidenceBadge, SourceBadge, FieldRow"
```

### Task F.3: UploadDropzone

**Files:**
- Create: `frontend/src/components/primitives/UploadDropzone.tsx`

- [ ] **Step 1: Implement**

```typescript
// frontend/src/components/primitives/UploadDropzone.tsx
import { useCallback, useRef, useState } from 'react'
import { Upload } from 'lucide-react'
import { toast } from 'sonner'

import { useUploadMutation } from '@/state/invoices'
import { cn } from '@/utils/cn'

export function UploadDropzone() {
  const upload = useUploadMutation()
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files?.length) return
      const file = files[0]
      if (file.type !== 'application/pdf') {
        toast.error('Only PDFs are accepted right now.')
        return
      }
      const id = toast.loading(`Extracting ${file.name}…`)
      try {
        const inv = await upload.mutateAsync(file)
        toast.success(
          `Extracted ${inv.current_extraction?.extracted_fields?.vendor_name?.value ?? 'invoice'}`,
          { id }
        )
      } catch (e) {
        toast.error(`Upload failed: ${(e as Error).message}`, { id })
      }
    },
    [upload]
  )

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        void handleFiles(e.dataTransfer.files)
      }}
      onClick={() => fileInput.current?.click()}
      className={cn(
        'flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors',
        dragging ? 'border-primary bg-accent' : 'border-border hover:bg-accent/40'
      )}
    >
      <Upload className="h-8 w-8 text-muted-foreground" />
      <p className="mt-2 text-sm">
        <span className="font-medium">Drop a PDF</span>{' '}
        <span className="text-muted-foreground">or click to upload</span>
      </p>
      <input
        ref={fileInput}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={(e) => void handleFiles(e.target.files)}
      />
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/primitives/UploadDropzone.tsx
git commit -m "feat(primitives): drag-and-drop UploadDropzone with sonner feedback"
```

### Task F.4: Inbox screen — dropzone + table

**Files:**
- Modify: `frontend/src/routes/InboxScreen.tsx`

- [ ] **Step 1: Replace stub with real screen**

```typescript
// frontend/src/routes/InboxScreen.tsx
import { Link } from 'react-router-dom'

import { TriagePill } from '@/components/primitives/TriagePill'
import { UploadDropzone } from '@/components/primitives/UploadDropzone'
import { useInboxQuery } from '@/state/invoices'

export function InboxScreen() {
  const { data, isLoading, error } = useInboxQuery()
  return (
    <div className="container py-8">
      <h1 className="text-2xl font-semibold">Inbox</h1>

      <div className="mt-4">
        <UploadDropzone />
      </div>

      <div className="mt-8 overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Triage</th>
              <th className="px-4 py-2">Vendor</th>
              <th className="px-4 py-2">Invoice #</th>
              <th className="px-4 py-2">Date</th>
              <th className="px-4 py-2 text-right">Total</th>
              <th className="px-4 py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {error && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-destructive">
                  Failed to load invoices.
                </td>
              </tr>
            )}
            {data?.length === 0 && !isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted-foreground">
                  No invoices yet — drop one above to get started.
                </td>
              </tr>
            )}
            {data?.map((inv) => {
              const fields = inv.current_extraction?.extracted_fields ?? {}
              const isUnprocessable = inv.review_status === 'unprocessable'
              const variant = isUnprocessable
                ? 'unprocessable'
                : inv.current_extraction?.predicted_triage_state ?? 'needs_review'
              return (
                <tr key={inv.id} className="border-t hover:bg-accent/30">
                  <td className="px-4 py-2">
                    <TriagePill variant={variant as never} />
                  </td>
                  <td className="px-4 py-2">
                    <Link
                      to={`/invoice/${inv.id}`}
                      className="font-medium hover:underline"
                    >
                      {fields.vendor_name?.value ?? '—'}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {fields.invoice_number?.value ?? '—'}
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {fields.invoice_date?.value ?? '—'}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {fields.total?.value !== undefined
                      ? `${fields.currency?.value ?? ''} ${fields.total.value}`
                      : '—'}
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {inv.review_status}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

```bash
docker compose exec frontend pnpm tsc --noEmit
```
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/InboxScreen.tsx
git commit -m "feat(inbox): dropzone + invoices table wired to API"
```

### Task F.5: Review screen — PDF viewer + fields panel

**Files:**
- Create: `frontend/src/components/primitives/PdfViewer.tsx`
- Modify: `frontend/src/routes/ReviewScreen.tsx`

- [ ] **Step 1: PdfViewer — minimal PDF.js render**

```typescript
// frontend/src/components/primitives/PdfViewer.tsx
import { useEffect, useRef } from 'react'
import * as pdfjs from 'pdfjs-dist'

// Configure worker URL — Vite resolves the module URL at build time.
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

export function PdfViewer({ src }: { src: string }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const container = containerRef.current
    container.innerHTML = ''
    let cancelled = false

    void (async () => {
      const doc = await pdfjs.getDocument(src).promise
      const page = await doc.getPage(1)
      const viewport = page.getViewport({ scale: 1.5 })
      const canvas = document.createElement('canvas')
      const context = canvas.getContext('2d')!
      canvas.width = viewport.width
      canvas.height = viewport.height
      canvas.className = 'max-w-full shadow'
      container.appendChild(canvas)
      if (cancelled) return
      await page.render({ canvasContext: context, viewport }).promise
    })()

    return () => {
      cancelled = true
    }
  }, [src])

  return <div ref={containerRef} className="flex justify-center bg-muted/20 p-4" />
}
```

- [ ] **Step 2: Review screen wiring**

```typescript
// frontend/src/routes/ReviewScreen.tsx
import { useParams } from 'react-router-dom'

import { FieldRow } from '@/components/primitives/FieldRow'
import { PdfViewer } from '@/components/primitives/PdfViewer'
import { TriagePill } from '@/components/primitives/TriagePill'
import { useInvoiceQuery } from '@/state/invoices'

const FIELD_LABELS: { key: string; label: string }[] = [
  { key: 'vendor_name', label: 'Vendor' },
  { key: 'invoice_number', label: 'Invoice #' },
  { key: 'invoice_date', label: 'Date' },
  { key: 'subtotal', label: 'Subtotal' },
  { key: 'tax', label: 'Tax' },
  { key: 'total', label: 'Total' },
  { key: 'currency', label: 'Currency' },
]

export function ReviewScreen() {
  const { id } = useParams<{ id: string }>()
  const { data: invoice, isLoading } = useInvoiceQuery(id)

  if (isLoading || !invoice) {
    return (
      <div className="container py-8 text-muted-foreground">Loading…</div>
    )
  }

  const ext = invoice.current_extraction
  const fields = ext?.extracted_fields ?? {}
  const pdfSrc = `/api/invoices/${invoice.id}/file`  // Day-2 file serving — for now this 404s gracefully

  return (
    <div className="grid h-full grid-cols-1 lg:grid-cols-2 gap-4 overflow-hidden p-4">
      <div className="overflow-y-auto">
        <PdfViewer src={pdfSrc} />
      </div>
      <div className="overflow-y-auto">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">
            {fields.vendor_name?.value ?? 'Invoice'}
          </h2>
          {ext && (
            <TriagePill
              variant={
                invoice.review_status === 'unprocessable'
                  ? ('unprocessable' as never)
                  : (ext.predicted_triage_state as never)
              }
            />
          )}
        </div>
        <div className="mt-4 rounded-lg border bg-card p-4">
          {FIELD_LABELS.map(({ key, label }) => (
            <FieldRow key={key} label={label} field={fields[key] ?? null} />
          ))}
        </div>
        {ext?.predicted_triage_reasons.length ? (
          <div className="mt-4 rounded-lg border bg-card p-4">
            <h3 className="text-sm font-medium">Why</h3>
            <ul className="mt-2 list-disc pl-5 text-sm text-muted-foreground">
              {ext.predicted_triage_reasons.map((r, i) => (
                <li key={i}>{r.type}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Add file-serving endpoint so PdfViewer can render**

```python
# Add to backend/app/api/invoices.py — append to the file
from fastapi.responses import FileResponse


@router.get("/{invoice_id}/file")
def serve_invoice_pdf(
    invoice_id: UUID, session: Session = Depends(get_session)
) -> FileResponse:
    inv = invoice_repo.get_invoice(session, invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="not found")
    path = Path(inv.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="file missing")
    return FileResponse(path, media_type="application/pdf")
```

- [ ] **Step 4: Type-check + run frontend tests**

```bash
docker compose exec frontend pnpm tsc --noEmit
docker compose exec frontend pnpm vitest run
```
Expected: clean + 5 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/primitives/PdfViewer.tsx \
        frontend/src/routes/ReviewScreen.tsx \
        backend/app/api/invoices.py
git commit -m "feat(review): PDF viewer + fields panel + file-serving endpoint"
```

---

## Phase G — End-to-end smoke

### Task G.1: Manual smoke + verification

The first time a real PDF flows through the system end-to-end. Requires a valid `ANTHROPIC_API_KEY` in `.env`.

- [ ] **Step 1: Ensure `.env` has a real API key**

```bash
grep '^ANTHROPIC_API_KEY=' .env
```
Expected: a non-empty key (not the placeholder).

- [ ] **Step 2: Restart backend to pick up env**

```bash
docker compose restart backend
sleep 3
curl -s http://localhost:8000/health
```
Expected: `{"status":"ok","version":"0.1.0"}`.

- [ ] **Step 3: Upload the fixture via curl**

```bash
curl -s -X POST http://localhost:8000/api/invoices \
  -F "file=@backend/tests/fixtures/digital_invoice_clean.pdf" | jq
```
Expected: a 201-ish JSON body with `review_status: pending`, `current_extraction.predicted_triage_state: confident`, and `extracted_fields.vendor_name.value: "Vega Logistics"`.

- [ ] **Step 4: Browser smoke — http://localhost:5173/inbox**

Open the URL in a browser. Confirm:
- Upload zone renders
- The invoice from step 3 appears in the table
- Click into it — review screen shows PDF on left, fields panel on right with `Vega Logistics`, confidence badges, source badges

- [ ] **Step 5: Run the full test suite**

```bash
make test
make lint
```
Expected: all green; import-linter contracts kept.

- [ ] **Step 6: Final commit (if anything changed)**

```bash
git status
# if no changes, skip
git add -A && git commit -m "chore: Day-1 happy-path verified end-to-end"
```

---

## What's NOT in this plan (intentionally deferred)

- **Vision path** (scanned PDFs via pdf2image + Claude Sonnet) — Day 2
- **Tiered cascade** with agreement-override — Day 2
- **Anomaly detection** (per-vendor Z-score) — Day 2
- **Duplicate detection** (perceptual hash + content fingerprint) — Day 2
- **bbox-following highlight UI** — Day 2 (we store `bbox: null` for now)
- **Triage actions in the UI** (Confirm / Dismiss / Mark unprocessable + bulk-confirm with undo) — Day 2
- **Why-column typed reason cards** — Day 2 (we render `reason.type` as plain text on the review screen for now)
- **Search + chip filters + NL→StructuredQuery** — Day 4
- **Line items + tax breakdown** — Day 3 / Day 4
- **Deploy to Fly** — separate plan once happy-path is verified locally

---

## Definition of Done

When all checkboxes are ticked:
- ☑ A digital PDF uploaded via the inbox dropzone produces a `confident` extraction visible on the review screen
- ☑ The full unit suite (`tests/unit/`) runs in <1s with ~35+ tests
- ☑ The integration suite passes against the docker Postgres
- ☑ `make lint` is green (ruff + import-linter + tsc)
- ☑ The `cascade_trace` JSONB column carries the prompt-hash + schema-hash + token usage for every extraction (eval reproducibility per ADR-0005)
- ☑ The `predicted_triage_state` and `predicted_triage_reasons` are immutable per row, ready for active learning and eval
- ☑ The four UX-surface primitives (`TriagePill`, `ConfidenceBadge`, `SourceBadge`, `FieldRow`) are reusable across Day-2 surfaces
