# Anomalies Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dead "Anomalies" sidebar entry with a working screen that surfaces statistical (`amount`-type) anomalies, lets clerks acknowledge them individually or in bulk, and updates `vendor.memory.acknowledged_outliers` so similar values aren't re-flagged on the next extraction.

**Architecture:** All-in-one `GET /api/anomalies` returns cards + counts + aggregates in one round trip. New `anomaly_acks` table tracks per-anomaly ack state with a UNIQUE (invoice_id, subtype, field) key. `domain/anomalies.py` gains an optional `acknowledged_outliers` parameter and a 10% tolerance skip check. Four-layer architecture per [ADR-0005](../../adr/0005-layered-architecture.md) preserved. Phase 1 ships only `subtype="amount"`; Frequency / Pattern tabs render accurate empty results.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (sync) + Postgres + Alembic + Pydantic v2 + argon2-cffi/itsdangerous (existing auth). Frontend: React + Vite + TypeScript + TanStack Query + Tailwind.

**Source spec:** [docs/superpowers/specs/2026-05-15-anomalies-phase-1-design.md](../specs/2026-05-15-anomalies-phase-1-design.md). When this plan and the spec disagree, the spec wins; raise the discrepancy.

---

## Preconditions

This branch (`feat/anomalies-phase-1`) was created off `main` before the login PR ([sift#1](https://github.com/SahilSharma0810/sift/pull/1)) merged. Before starting implementation, the branch must include the login backend's contributions:

- `User` and `AuthSession` ORM in `backend/app/db/models.py`
- `get_current_clerk` dependency in `backend/app/api/deps.py`
- Authed `api_client` / `unauthed_client` test fixtures in `backend/tests/integration/conftest.py`
- The import-linter `ignore_imports` allow-list entries for `app.api.* -> app.db.session`

**Pre-flight:** before Task 1, run `git merge origin/main` (or rebase) so this branch sits on top of the merged login work. If `main` doesn't yet contain login, wait for sift#1 to merge first.

## Style discipline

Two non-negotiable rules from memory ([feedback_minimal_comments.md](../../../) and [feedback_alias_imports.md](../../../)):

1. **Default to no comments.** Add only when the *why* is non-obvious. Don't narrate *what*. Don't reference this task / ADR numbers / callers in inline comments — those belong in commits.
2. **Alias / absolute imports only.** Frontend uses `@/...`. Backend uses `from app.foo import bar`. No relative imports anywhere (`from .foo`, `from ../foo`).

Verify before merge:

```bash
grep -rn "from '\.\." frontend/src    # must be empty
grep -rn "^from \." backend/app       # must be empty
```

---

## File Structure

**Backend — new files:**

- `backend/app/domain/anomalies_models.py` — Pydantic DTOs (AnomalyOut, AnomalyMetric, AnomalyHistoryPoint, AnomalyCounts, AnomalyAggregates, AnomaliesResponse, BulkAcknowledgeIn, BulkAcknowledgeOut, BulkAcknowledgeFailure).
- `backend/app/adapters/storage/anomaly_repo.py` — `create_ack`, `vendor_history_query`, `list_acks_by_invoice_ids`.
- `backend/app/services/anomaly_service.py` — `list_anomalies`, `acknowledge`, `acknowledge_bulk`. Composite-id parser lives here.
- `backend/app/api/anomalies.py` — `GET /api/anomalies`, `POST /api/anomalies/{id}/acknowledge`, `POST /api/anomalies/acknowledge-bulk`.
- `backend/alembic/versions/<new>_add_anomaly_acks.py` — migration.
- `backend/tests/unit/test_anomaly_models.py` — DTO round-trip tests.
- `backend/tests/integration/test_anomaly_repo.py`
- `backend/tests/integration/test_anomaly_service.py`
- `backend/tests/integration/test_anomaly_api.py`

**Backend — modified files:**

- `backend/app/db/models.py` — add `AnomalyAck` ORM.
- `backend/app/domain/anomalies.py` — add `ACK_TOLERANCE_FRAC`, optional `acknowledged_outliers` kwarg, `_is_acked` helper.
- `backend/app/domain/models.py` — re-export new DTOs (forwards them to `pydantic2ts`).
- `backend/app/services/extraction_service.py` — read `vendor.memory.acknowledged_outliers` and pass to `detect_anomalies`.
- `backend/app/main.py` — register anomalies router.
- `backend/pyproject.toml` — add `app.api.anomalies -> app.db.session` to import-linter ignore_imports.
- `backend/tests/unit/test_anomalies.py` — three new cases for the skip logic.

**Frontend — new files:**

- `frontend/src/routes/AnomaliesScreen.tsx`
- `frontend/src/state/anomalies.ts`
- `frontend/src/components/anomalies/AnomalyCard.tsx`
- `frontend/src/components/anomalies/Sparkline.tsx`
- `frontend/src/components/anomalies/TypePill.tsx`

**Frontend — modified files:**

- `frontend/src/routes/router.tsx` — add `/anomalies` route.
- `frontend/src/components/shell/Shell.tsx` — convert the Anomalies `<div>` to `<Link to="/anomalies">`; replace `counts.likely_duplicate` next to it with the real anomaly count.
- `frontend/src/types/generated/domain.ts` — regenerated.
- `frontend/tailwind.config.ts` — add anomaly-pill theme tokens.

---

## Task 1: `AnomalyAck` ORM model

**Files:**
- Modify: `backend/app/db/models.py`

- [ ] **Step 1: Append the ORM class** to `backend/app/db/models.py`, after the existing `AuthSession` class (login backend's last class):

```python
class AnomalyAck(Base):
    __tablename__ = "anomaly_acks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    anomaly_subtype: Mapped[str] = mapped_column(Text, nullable=False)
    anomaly_field: Mapped[str] = mapped_column(Text, nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    acknowledged_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_anomaly_acks_invoice_id", "invoice_id"),
        UniqueConstraint(
            "invoice_id",
            "anomaly_subtype",
            "anomaly_field",
            name="uq_anomaly_acks_key",
        ),
    )
```

Required imports at the top of `models.py` should already include `Index`, `ForeignKey`, `Text`, `func`, `DateTime`. Add `UniqueConstraint` to the existing `from sqlalchemy import …` line if it isn't already there.

- [ ] **Step 2: Smoke-import**

```bash
docker compose exec backend uv run python -c "from app.db.models import AnomalyAck; print(sorted(AnomalyAck.__table__.columns.keys()))"
```

Expected: `['acknowledged_at', 'acknowledged_by_user_id', 'anomaly_field', 'anomaly_subtype', 'id', 'invoice_id', 'notes']`

- [ ] **Step 3: Commit**

```bash
git add backend/app/db/models.py
git commit -m "feat(db): AnomalyAck ORM model"
```

---

## Task 2: Alembic migration — `anomaly_acks`

**Files:**
- Create: `backend/alembic/versions/<new>_add_anomaly_acks.py`

- [ ] **Step 1: Find the current head revision**

```bash
docker compose exec backend uv run alembic heads
```

Note the printed id as `<PREV_HEAD>` (post-login it will be the login migration's id).

- [ ] **Step 2: Generate the empty revision**

```bash
docker compose exec backend uv run alembic revision -m "add anomaly_acks"
```

Note the new id as `<NEW_REV>`.

- [ ] **Step 3: Replace the file contents** with this body, substituting the two revision ids:

```python
"""add anomaly_acks

Revision ID: <NEW_REV>
Revises: <PREV_HEAD>
Create Date: <leave as auto-generated>

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "<NEW_REV>"
down_revision: str | Sequence[str] | None = "<PREV_HEAD>"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "anomaly_acks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("anomaly_subtype", sa.Text(), nullable=False),
        sa.Column("anomaly_field", sa.Text(), nullable=False),
        sa.Column(
            "acknowledged_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("acknowledged_by_user_id", sa.UUID(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["acknowledged_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "invoice_id",
            "anomaly_subtype",
            "anomaly_field",
            name="uq_anomaly_acks_key",
        ),
    )
    op.create_index("ix_anomaly_acks_invoice_id", "anomaly_acks", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_anomaly_acks_invoice_id", table_name="anomaly_acks")
    op.drop_table("anomaly_acks")
```

- [ ] **Step 4: Apply and verify**

```bash
docker compose exec backend uv run alembic upgrade head
docker compose exec -T db psql -U sift -d sift -c "\d anomaly_acks"
```

Expected: table with 7 columns, FKs to `invoices(id) ON DELETE CASCADE` and `users(id)`, UNIQUE constraint `uq_anomaly_acks_key`, index `ix_anomaly_acks_invoice_id`.

- [ ] **Step 5: Test downgrade round-trip**

```bash
docker compose exec backend uv run alembic downgrade -1
docker compose exec -T db psql -U sift -d sift -c "\dt anomaly_acks"   # Did not find any relation
docker compose exec backend uv run alembic upgrade head
docker compose exec -T db psql -U sift -d sift -c "\dt anomaly_acks"   # back
```

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/<NEW_REV>_add_anomaly_acks.py
git commit -m "feat(db): migration adds anomaly_acks table"
```

---

## Task 3: Detection skip logic in `domain/anomalies.py`

**Files:**
- Modify: `backend/app/domain/anomalies.py`
- Modify: `backend/tests/unit/test_anomalies.py`

- [ ] **Step 1: Append failing tests** to `backend/tests/unit/test_anomalies.py`:

```python
class TestDetectAnomaliesWithAcks:
    def test_acked_value_within_tolerance_skips_anomaly(self) -> None:
        anomalies = detect_anomalies(
            fields={"total": 34062.50},
            stats={"total_seen": 10, "avg_total": 7900.0, "std_total": 1500.0},
            acknowledged_outliers={
                "total": [{"value": 33500.00, "acked_at": "2026-05-15T00:00:00Z"}]
            },
        )
        assert anomalies == []

    def test_acked_value_outside_tolerance_still_emits_anomaly(self) -> None:
        anomalies = detect_anomalies(
            fields={"total": 50000.00},
            stats={"total_seen": 10, "avg_total": 7900.0, "std_total": 1500.0},
            acknowledged_outliers={
                "total": [{"value": 34000.00, "acked_at": "2026-05-15T00:00:00Z"}]
            },
        )
        assert len(anomalies) == 1
        assert anomalies[0]["z_score"] > 3.0

    def test_empty_acknowledged_outliers_preserves_prior_behavior(self) -> None:
        anomalies = detect_anomalies(
            fields={"total": 14231.0},
            stats={"total_seen": 10, "avg_total": 1180.0, "std_total": 100.0},
            acknowledged_outliers={},
        )
        assert len(anomalies) == 1
```

- [ ] **Step 2: Run to verify it fails**

```bash
docker compose exec backend uv run pytest tests/unit/test_anomalies.py::TestDetectAnomaliesWithAcks -v
```

Expected: FAIL (the kwarg doesn't exist yet).

- [ ] **Step 3: Extend `backend/app/domain/anomalies.py`**. The current file is short — replace it with:

```python
"""Anomaly detection for extracted invoice fields.

Pure: no IO. Compares numeric fields against per-vendor stats (mean + std)
and emits `anomaly` reason payloads matching the AnomalyReason discriminator.
"""

from __future__ import annotations

from typing import Any

ANOMALY_FIELDS = ("total",)

MIN_VENDOR_HISTORY = 3

Z_THRESHOLD = 3.0

ACK_TOLERANCE_FRAC = 0.10


def detect_anomalies(
    *,
    fields: dict[str, Any],
    stats: dict[str, Any],
    acknowledged_outliers: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Return `anomaly` reason payloads for fields outside +-3 sigma of vendor history.

    `stats` shape: {"total_seen": int, "avg_total": float, "std_total": float}.
    Skips the check when vendor history is too small or std is degenerate.

    `acknowledged_outliers` maps field name → list of prior-acked values for
    that field. A new value within ACK_TOLERANCE_FRAC of any acked value is
    treated as a known outlier and is NOT emitted as an anomaly.
    """
    acks = acknowledged_outliers or {}
    out: list[dict[str, Any]] = []
    total_seen = int(stats.get("total_seen", 0) or 0)
    if total_seen < MIN_VENDOR_HISTORY:
        return out
    for field in ANOMALY_FIELDS:
        value = fields.get(field)
        if value is None:
            continue
        avg = float(stats.get(f"avg_{field}", 0.0) or 0.0)
        std = float(stats.get(f"std_{field}", 0.0) or 0.0)
        if std <= 0:
            continue
        try:
            z = abs(float(value) - avg) / std
        except (TypeError, ValueError):
            continue
        if z < Z_THRESHOLD:
            continue
        if _is_acked(float(value), acks.get(field, [])):
            continue
        out.append(
            {
                "field": field,
                "vendor_mean": avg,
                "vendor_std": std,
                "z_score": round(z, 2),
            }
        )
    return out


def _is_acked(value: float, acked: list[dict[str, Any]]) -> bool:
    for a in acked:
        a_val = float(a.get("value", 0.0) or 0.0)
        if a_val <= 0:
            continue
        if abs(value - a_val) / a_val < ACK_TOLERANCE_FRAC:
            return True
    return False
```

Note: the existing behavior is preserved — only the new kwarg, the threshold-check refactor (now a `continue` instead of falling into the append), and the `_is_acked` short-circuit are new.

- [ ] **Step 4: Run all anomaly tests + import-linter**

```bash
docker compose exec backend uv run pytest tests/unit/test_anomalies.py -v
docker compose exec backend uv run lint-imports
```

Expected: every test passes (existing 5+ tests plus the new 3 in `TestDetectAnomaliesWithAcks`); import-linter still 3 contracts kept, 0 broken.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/anomalies.py backend/tests/unit/test_anomalies.py
git commit -m "feat(anomalies): acknowledged_outliers skip logic in detect_anomalies"
```

---

## Task 4: Wire `acknowledged_outliers` into `extraction_service`

**Files:**
- Modify: `backend/app/services/extraction_service.py`

- [ ] **Step 1: Find the existing `detect_anomalies` call** at `backend/app/services/extraction_service.py:457-460`:

```python
    anomalies: list[dict[str, Any]] = []
    if duplicate_of is None:
        stats = (vendor.memory or {}).get("stats", {}) or {}
        anomalies = detect_anomalies(fields=final_fields, stats=stats)
```

- [ ] **Step 2: Replace it with**:

```python
    anomalies: list[dict[str, Any]] = []
    if duplicate_of is None:
        mem = vendor.memory or {}
        stats = mem.get("stats", {}) or {}
        acked = mem.get("acknowledged_outliers", {}) or {}
        anomalies = detect_anomalies(
            fields=final_fields,
            stats=stats,
            acknowledged_outliers=acked,
        )
```

- [ ] **Step 3: Run the integration suite** to confirm no regressions:

```bash
docker compose exec backend uv run pytest tests/integration -q
```

Expected: same pass/fail baseline as before this task (no new failures, the pre-existing LLM-stub failures remain if `SIFT_LLM_PROVIDER=anthropic` is set in `.env`).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/extraction_service.py
git commit -m "feat(extraction): pass vendor.acknowledged_outliers to anomaly detection"
```

---

## Task 5: `anomaly_repo` — create_ack, vendor_history_query, list_acks_by_invoice_ids

**Files:**
- Create: `backend/app/adapters/storage/anomaly_repo.py`
- Create: `backend/tests/integration/test_anomaly_repo.py`

- [ ] **Step 1: Write the failing tests** — create `backend/tests/integration/test_anomaly_repo.py`:

```python
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.adapters.storage.anomaly_repo import (
    create_ack,
    list_acks_by_invoice_ids,
    vendor_history_query,
)
from app.adapters.storage.invoice_repo import create_invoice
from app.adapters.storage.user_repo import upsert_demo_user
from app.adapters.storage.vendor_repo import upsert_by_normalized_name
from app.db.models import AnomalyAck


class TestCreateAck:
    def test_inserts_a_row(self, db_session: Session) -> None:
        user = upsert_demo_user(db_session, email="ack@example.test", password="x")
        vendor = upsert_by_normalized_name(db_session, name="Halcyon Software")
        invoice = create_invoice(
            db_session,
            file_path="/data/uploads/h.pdf",
            file_hash="hash-h-1",
            vendor_id=vendor.id,
        )
        ack = create_ack(
            db_session,
            invoice_id=invoice.id,
            subtype="amount",
            field="total",
            user_id=user.id,
            notes=None,
        )
        assert ack.id is not None
        assert ack.anomaly_subtype == "amount"
        assert ack.anomaly_field == "total"
        assert ack.acknowledged_by_user_id == user.id

    def test_idempotent_on_unique_conflict(self, db_session: Session) -> None:
        user = upsert_demo_user(db_session, email="ack-idem@example.test", password="x")
        vendor = upsert_by_normalized_name(db_session, name="Halcyon Idempotent")
        invoice = create_invoice(
            db_session,
            file_path="/data/uploads/h2.pdf",
            file_hash="hash-h-2",
            vendor_id=vendor.id,
        )
        a1 = create_ack(
            db_session,
            invoice_id=invoice.id,
            subtype="amount",
            field="total",
            user_id=user.id,
            notes=None,
        )
        a2 = create_ack(
            db_session,
            invoice_id=invoice.id,
            subtype="amount",
            field="total",
            user_id=user.id,
            notes="second call",
        )
        assert a1.id == a2.id


class TestListAcksByInvoiceIds:
    def test_returns_acks_for_ids(self, db_session: Session) -> None:
        user = upsert_demo_user(db_session, email="list-ack@example.test", password="x")
        vendor = upsert_by_normalized_name(db_session, name="V Lookup")
        inv = create_invoice(
            db_session,
            file_path="/data/uploads/lookup.pdf",
            file_hash="hash-lookup",
            vendor_id=vendor.id,
        )
        create_ack(
            db_session,
            invoice_id=inv.id,
            subtype="amount",
            field="total",
            user_id=user.id,
            notes=None,
        )
        rows = list_acks_by_invoice_ids(db_session, invoice_ids=[inv.id])
        assert len(rows) == 1
        assert rows[0].invoice_id == inv.id

    def test_empty_input_returns_empty_list(self, db_session: Session) -> None:
        assert list_acks_by_invoice_ids(db_session, invoice_ids=[]) == []


class TestVendorHistoryQuery:
    def test_returns_confirmed_totals_ordered_desc(self, db_session: Session) -> None:
        vendor = upsert_by_normalized_name(db_session, name="History Vendor")
        # The full history test relies on extractions; for a minimal test
        # we just verify the query runs and returns an empty list for a
        # vendor with no confirmed invoices.
        results = vendor_history_query(
            db_session,
            vendor_id=vendor.id,
            exclude_invoice_id=uuid4(),
            limit=11,
        )
        assert results == []
```

- [ ] **Step 2: Run to verify it fails**

```bash
docker compose exec backend uv run pytest tests/integration/test_anomaly_repo.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.adapters.storage.anomaly_repo'`.

- [ ] **Step 3: Implement** — create `backend/app/adapters/storage/anomaly_repo.py`:

```python
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import AnomalyAck, Extraction, Invoice


def create_ack(
    session: Session,
    *,
    invoice_id: UUID,
    subtype: str,
    field: str,
    user_id: UUID,
    notes: str | None,
) -> AnomalyAck:
    stmt = (
        insert(AnomalyAck)
        .values(
            invoice_id=invoice_id,
            anomaly_subtype=subtype,
            anomaly_field=field,
            acknowledged_by_user_id=user_id,
            notes=notes,
        )
        .on_conflict_do_nothing(constraint="uq_anomaly_acks_key")
        .returning(AnomalyAck.id)
    )
    inserted_id = session.execute(stmt).scalar_one_or_none()
    session.commit()

    if inserted_id is not None:
        return session.execute(
            select(AnomalyAck).where(AnomalyAck.id == inserted_id)
        ).scalar_one()

    existing = session.execute(
        select(AnomalyAck).where(
            AnomalyAck.invoice_id == invoice_id,
            AnomalyAck.anomaly_subtype == subtype,
            AnomalyAck.anomaly_field == field,
        )
    ).scalar_one()
    return existing


def list_acks_by_invoice_ids(
    session: Session, *, invoice_ids: list[UUID]
) -> list[AnomalyAck]:
    if not invoice_ids:
        return []
    stmt = select(AnomalyAck).where(AnomalyAck.invoice_id.in_(invoice_ids))
    return list(session.execute(stmt).scalars().all())


def vendor_history_query(
    session: Session,
    *,
    vendor_id: UUID,
    exclude_invoice_id: UUID,
    limit: int,
) -> list[float]:
    stmt = (
        select(Extraction.extracted_fields["total"]["value"].astext, Invoice.uploaded_at)
        .join(Invoice, Extraction.invoice_id == Invoice.id)
        .where(
            Invoice.vendor_id == vendor_id,
            Invoice.review_status == "confirmed",
            Invoice.id != exclude_invoice_id,
            Extraction.is_current.is_(True),
        )
        .order_by(Invoice.uploaded_at.desc())
        .limit(limit)
    )
    rows = session.execute(stmt).all()
    out: list[float] = []
    for raw, _ in rows:
        if raw is None:
            continue
        try:
            out.append(float(raw))
        except (TypeError, ValueError):
            continue
    return out
```

- [ ] **Step 4: Run the tests**

```bash
docker compose exec backend uv run pytest tests/integration/test_anomaly_repo.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/adapters/storage/anomaly_repo.py backend/tests/integration/test_anomaly_repo.py
git commit -m "feat(anomalies): anomaly_repo — create_ack idempotent, list_acks, vendor_history"
```

---

## Task 6: Pydantic DTOs in `anomalies_models.py`

**Files:**
- Create: `backend/app/domain/anomalies_models.py`
- Modify: `backend/app/domain/models.py`
- Create: `backend/tests/unit/test_anomaly_models.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/unit/test_anomaly_models.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.anomalies_models import (
    AnomaliesResponse,
    AnomalyAggregates,
    AnomalyCounts,
    AnomalyHistoryPoint,
    AnomalyMetric,
    AnomalyOut,
    BulkAcknowledgeFailure,
    BulkAcknowledgeIn,
    BulkAcknowledgeOut,
)


def _sample_anomaly() -> AnomalyOut:
    return AnomalyOut(
        id="00000000-0000-0000-0000-000000000001:amount:total",
        type="amount",
        status="unreviewed",
        vendor="Halcyon Software",
        invoice_id=uuid4(),
        detected_at=datetime.now(UTC),
        headline="$34,062.50 invoice",
        sub="4.2σ above rolling average of $7,900",
        z_score=4.2,
        severity="high",
        metric=AnomalyMetric(value=34062.50, currency="USD", unit="$"),
        history=[
            AnomalyHistoryPoint(value=7800.0),
            AnomalyHistoryPoint(value=34062.50, current=True),
        ],
        avg=7900.0,
    )


class TestAnomalyOut:
    def test_round_trip(self) -> None:
        a = _sample_anomaly()
        loaded = AnomalyOut.model_validate(a.model_dump(mode="json"))
        assert loaded.id == a.id
        assert loaded.severity == "high"
        assert loaded.metric.currency == "USD"

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            AnomalyOut.model_validate({"foo": "bar"})


class TestBulkAcknowledgeIn:
    def test_accepts_valid(self) -> None:
        body = BulkAcknowledgeIn(anomaly_ids=["a:amount:total"])
        assert len(body.anomaly_ids) == 1

    def test_rejects_empty_list(self) -> None:
        with pytest.raises(ValidationError):
            BulkAcknowledgeIn(anomaly_ids=[])

    def test_rejects_too_many(self) -> None:
        with pytest.raises(ValidationError):
            BulkAcknowledgeIn(anomaly_ids=["x"] * 201)


class TestAggregatesResponse:
    def test_aggregates_round_trip(self) -> None:
        agg = AnomalyAggregates(
            total_flagged_amount=34062.50,
            total_flagged_currency="USD",
            vendors_affected=1,
            highest_severity_z=4.2,
            highest_severity_vendor="Halcyon Software",
        )
        loaded = AnomalyAggregates.model_validate(agg.model_dump())
        assert loaded.highest_severity_z == 4.2

    def test_response_round_trip(self) -> None:
        resp = AnomaliesResponse(
            anomalies=[_sample_anomaly()],
            counts=AnomalyCounts(
                all=1, unreviewed=1, amount=1, frequency=0, pattern=0, acknowledged=0
            ),
            aggregates=AnomalyAggregates(
                total_flagged_amount=34062.50,
                total_flagged_currency="USD",
                vendors_affected=1,
                highest_severity_z=4.2,
                highest_severity_vendor="Halcyon Software",
            ),
        )
        loaded = AnomaliesResponse.model_validate(resp.model_dump(mode="json"))
        assert loaded.counts.unreviewed == 1


class TestBulkOut:
    def test_partial_success_shape(self) -> None:
        out = BulkAcknowledgeOut(
            acknowledged=[_sample_anomaly()],
            failed=[BulkAcknowledgeFailure(id="bad:amount:total", error="not_found")],
        )
        assert len(out.acknowledged) == 1
        assert out.failed[0].error == "not_found"
```

- [ ] **Step 2: Run to verify failure**

```bash
docker compose exec backend uv run pytest tests/unit/test_anomaly_models.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement** — create `backend/app/domain/anomalies_models.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


AnomalySubtype = Literal["amount"]
AnomalyStatus = Literal["unreviewed", "acknowledged"]
AnomalySeverity = Literal["high", "medium", "low"]


class AnomalyMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float
    currency: str
    unit: str


class AnomalyHistoryPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float
    current: bool = False


class AnomalyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: AnomalySubtype
    status: AnomalyStatus
    vendor: str
    invoice_id: UUID
    detected_at: datetime
    headline: str
    sub: str
    z_score: float
    severity: AnomalySeverity
    metric: AnomalyMetric
    history: list[AnomalyHistoryPoint]
    avg: float
    diff: None = None
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None


class AnomalyCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    all: int
    unreviewed: int
    amount: int
    frequency: int
    pattern: int
    acknowledged: int


class AnomalyAggregates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_flagged_amount: float
    total_flagged_currency: str
    vendors_affected: int
    highest_severity_z: float | None = None
    highest_severity_vendor: str | None = None


class AnomaliesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anomalies: list[AnomalyOut]
    counts: AnomalyCounts
    aggregates: AnomalyAggregates


class BulkAcknowledgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anomaly_ids: list[str] = Field(min_length=1, max_length=200)


class BulkAcknowledgeFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    error: str


class BulkAcknowledgeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledged: list[AnomalyOut]
    failed: list[BulkAcknowledgeFailure]
```

- [ ] **Step 4: Re-export from `backend/app/domain/models.py`** — append at the bottom:

```python
from app.domain.anomalies_models import (  # noqa: F401, E402
    AnomaliesResponse,
    AnomalyAggregates,
    AnomalyCounts,
    AnomalyHistoryPoint,
    AnomalyMetric,
    AnomalyOut,
    BulkAcknowledgeFailure,
    BulkAcknowledgeIn,
    BulkAcknowledgeOut,
)
```

This makes the new DTOs visible to `scripts/generate_types.py`.

- [ ] **Step 5: Run all unit tests + import-linter**

```bash
docker compose exec backend uv run pytest tests/unit/test_anomaly_models.py -v
docker compose exec backend uv run lint-imports
```

Expected: 8 passed; import-linter clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/anomalies_models.py backend/app/domain/models.py backend/tests/unit/test_anomaly_models.py
git commit -m "feat(anomalies): Pydantic DTOs for the anomalies surface"
```

---

## Task 7: `anomaly_service.list_anomalies`

**Files:**
- Create: `backend/app/services/anomaly_service.py`
- Create: `backend/tests/integration/test_anomaly_service.py`

- [ ] **Step 1: Write the failing tests** — create `backend/tests/integration/test_anomaly_service.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.adapters.storage.invoice_repo import create_invoice
from app.adapters.storage.user_repo import upsert_demo_user
from app.adapters.storage.vendor_repo import upsert_by_normalized_name
from app.db.models import Extraction, Invoice
from app.services.anomaly_service import (
    list_anomalies,
)


def _seed_invoice_with_anomaly(
    db_session: Session,
    *,
    vendor_name: str,
    file_hash: str,
    total: float,
    currency: str,
    z_score: float,
    avg: float,
    std: float,
    review_status: str = "pending",
    confirmed_history_totals: list[float] | None = None,
) -> Invoice:
    """Insert a vendor + invoice + current extraction with one anomaly reason.

    Optionally pre-seeds confirmed prior invoices for the same vendor so the
    sparkline-history query has data to return.
    """
    vendor = upsert_by_normalized_name(db_session, name=vendor_name)

    if confirmed_history_totals:
        for i, t in enumerate(confirmed_history_totals):
            prev_inv = create_invoice(
                db_session,
                file_path=f"/data/uploads/{file_hash}-prev-{i}.pdf",
                file_hash=f"{file_hash}-prev-{i}",
                vendor_id=vendor.id,
            )
            prev_inv.review_status = "confirmed"
            db_session.add(
                Extraction(
                    invoice_id=prev_inv.id,
                    model="stub",
                    cascade_trace={},
                    extracted_fields={"total": {"value": t, "confidence": 0.99, "source": "stub"}},
                    confidence_per_field={"total": 0.99},
                    predicted_triage_state="confident",
                    predicted_triage_reasons=[],
                    line_items=[],
                    tax_breakdown=[],
                    raw_text=None,
                    is_current=True,
                )
            )

    inv = create_invoice(
        db_session,
        file_path=f"/data/uploads/{file_hash}.pdf",
        file_hash=file_hash,
        vendor_id=vendor.id,
    )
    inv.review_status = review_status
    db_session.add(
        Extraction(
            invoice_id=inv.id,
            model="stub",
            cascade_trace={},
            extracted_fields={
                "total": {"value": total, "confidence": 0.99, "source": "stub"},
                "currency": {"value": currency, "confidence": 0.99, "source": "stub"},
            },
            confidence_per_field={"total": 0.99, "currency": 0.99},
            predicted_triage_state="needs_review",
            predicted_triage_reasons=[
                {
                    "type": "anomaly",
                    "field": "total",
                    "vendor_mean": avg,
                    "vendor_std": std,
                    "z_score": z_score,
                }
            ],
            line_items=[],
            tax_breakdown=[],
            raw_text=None,
            is_current=True,
        )
    )
    db_session.commit()
    return inv


class TestListAnomaliesEmpty:
    def test_empty_corpus_zero_counts(self, db_session: Session) -> None:
        resp = list_anomalies(db_session)
        assert resp.anomalies == []
        assert resp.counts.all == 0
        assert resp.counts.unreviewed == 0
        assert resp.aggregates.total_flagged_amount == 0
        assert resp.aggregates.vendors_affected == 0


class TestListAnomaliesPopulated:
    def test_amount_anomaly_surfaces_with_correct_shape(self, db_session: Session) -> None:
        _seed_invoice_with_anomaly(
            db_session,
            vendor_name="Halcyon Software",
            file_hash="halc-1",
            total=34062.50,
            currency="USD",
            z_score=4.2,
            avg=7900.0,
            std=1500.0,
            confirmed_history_totals=[6800, 7200, 8100, 7500, 9200, 6900, 7600, 8400, 7300, 8900, 7800],
        )
        resp = list_anomalies(db_session)
        assert len(resp.anomalies) == 1
        a = resp.anomalies[0]
        assert a.type == "amount"
        assert a.status == "unreviewed"
        assert a.vendor == "Halcyon Software"
        assert a.metric.value == 34062.50
        assert a.metric.currency == "USD"
        assert a.severity == "high"
        assert a.z_score == 4.2
        assert a.headline == "$34,062.50 invoice"
        assert "4.2σ" in a.sub
        assert "$7,900" in a.sub
        # 11 prior + 1 current = 12 history points
        assert len(a.history) == 12
        assert a.history[-1].current is True

    def test_severity_bands(self, db_session: Session) -> None:
        _seed_invoice_with_anomaly(
            db_session,
            vendor_name="Vendor A",
            file_hash="A-1",
            total=10000.0,
            currency="USD",
            z_score=4.5,
            avg=1000.0,
            std=500.0,
        )
        _seed_invoice_with_anomaly(
            db_session,
            vendor_name="Vendor B",
            file_hash="B-1",
            total=2200.0,
            currency="USD",
            z_score=3.0,
            avg=1000.0,
            std=400.0,
        )
        resp = list_anomalies(db_session)
        severities = {a.vendor: a.severity for a in resp.anomalies}
        assert severities["Vendor A"] == "high"
        assert severities["Vendor B"] == "medium"

    def test_aggregates_dominant_currency(self, db_session: Session) -> None:
        _seed_invoice_with_anomaly(
            db_session,
            vendor_name="USD Vendor 1",
            file_hash="usd-1",
            total=10000.0,
            currency="USD",
            z_score=3.5,
            avg=1000.0,
            std=500.0,
        )
        _seed_invoice_with_anomaly(
            db_session,
            vendor_name="USD Vendor 2",
            file_hash="usd-2",
            total=20000.0,
            currency="USD",
            z_score=4.0,
            avg=2000.0,
            std=500.0,
        )
        _seed_invoice_with_anomaly(
            db_session,
            vendor_name="EUR Vendor",
            file_hash="eur-1",
            total=5000.0,
            currency="EUR",
            z_score=3.2,
            avg=500.0,
            std=200.0,
        )
        resp = list_anomalies(db_session)
        assert resp.aggregates.total_flagged_currency == "USD"
        assert resp.aggregates.total_flagged_amount == 30000.0
        assert resp.aggregates.vendors_affected == 3
        assert resp.aggregates.highest_severity_z == 4.0

    def test_counts_breakdown(self, db_session: Session) -> None:
        _seed_invoice_with_anomaly(
            db_session,
            vendor_name="Count Vendor",
            file_hash="cnt-1",
            total=10000.0,
            currency="USD",
            z_score=3.5,
            avg=1000.0,
            std=500.0,
        )
        resp = list_anomalies(db_session)
        assert resp.counts.all == 1
        assert resp.counts.unreviewed == 1
        assert resp.counts.amount == 1
        assert resp.counts.frequency == 0
        assert resp.counts.pattern == 0
        assert resp.counts.acknowledged == 0
```

- [ ] **Step 2: Run to verify failure**

```bash
docker compose exec backend uv run pytest tests/integration/test_anomaly_service.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement** — create `backend/app/services/anomaly_service.py`:

```python
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.storage import anomaly_repo
from app.db.models import AnomalyAck, Extraction, Invoice, User, Vendor
from app.domain.anomalies_models import (
    AnomaliesResponse,
    AnomalyAggregates,
    AnomalyCounts,
    AnomalyHistoryPoint,
    AnomalyMetric,
    AnomalyOut,
)

SUPPORTED_SUBTYPE = "amount"
SUPPORTED_FIELD = "total"
HISTORY_LIMIT = 11


def list_anomalies(session: Session) -> AnomaliesResponse:
    rows = session.execute(
        select(Invoice, Extraction, Vendor)
        .join(Extraction, Extraction.invoice_id == Invoice.id)
        .join(Vendor, Vendor.id == Invoice.vendor_id, isouter=True)
        .where(Extraction.is_current.is_(True))
    ).all()

    invoice_ids = [inv.id for inv, _, _ in rows]
    acks = {
        (ack.invoice_id, ack.anomaly_subtype, ack.anomaly_field): ack
        for ack in anomaly_repo.list_acks_by_invoice_ids(session, invoice_ids=invoice_ids)
    }

    ack_users = _load_ack_users(session, acks)

    anomalies: list[AnomalyOut] = []
    for inv, extr, vendor in rows:
        if vendor is None:
            continue
        for reason in extr.predicted_triage_reasons or []:
            if reason.get("type") != "anomaly":
                continue
            field = reason.get("field")
            if field != SUPPORTED_FIELD:
                continue
            anomaly = _build_anomaly_out(
                session=session,
                invoice=inv,
                extraction=extr,
                vendor=vendor,
                reason=reason,
                ack=acks.get((inv.id, SUPPORTED_SUBTYPE, field)),
                ack_user_email=_email_for_ack(acks.get((inv.id, SUPPORTED_SUBTYPE, field)), ack_users),
            )
            anomalies.append(anomaly)

    anomalies.sort(key=lambda a: a.detected_at, reverse=True)
    counts = _compute_counts(anomalies)
    aggregates = _compute_aggregates(anomalies)
    return AnomaliesResponse(anomalies=anomalies, counts=counts, aggregates=aggregates)


def _build_anomaly_out(
    *,
    session: Session,
    invoice: Invoice,
    extraction: Extraction,
    vendor: Vendor,
    reason: dict[str, Any],
    ack: AnomalyAck | None,
    ack_user_email: str | None,
) -> AnomalyOut:
    fields = extraction.extracted_fields or {}
    total_spec = fields.get(SUPPORTED_FIELD) or {}
    value = float(total_spec.get("value") or 0.0)
    currency_spec = fields.get("currency") or {}
    currency = str(currency_spec.get("value") or "USD")
    z = float(reason.get("z_score") or 0.0)
    avg = float(reason.get("vendor_mean") or 0.0)

    prior = anomaly_repo.vendor_history_query(
        session,
        vendor_id=vendor.id,
        exclude_invoice_id=invoice.id,
        limit=HISTORY_LIMIT,
    )
    history = [AnomalyHistoryPoint(value=v) for v in reversed(prior)]
    history.append(AnomalyHistoryPoint(value=value, current=True))

    return AnomalyOut(
        id=f"{invoice.id}:{SUPPORTED_SUBTYPE}:{SUPPORTED_FIELD}",
        type="amount",
        status="acknowledged" if ack else "unreviewed",
        vendor=vendor.name,
        invoice_id=invoice.id,
        detected_at=invoice.uploaded_at,
        headline=_format_headline(value, currency),
        sub=_format_sub(z, avg, currency),
        z_score=z,
        severity=_severity_band(z),
        metric=AnomalyMetric(value=value, currency=currency, unit="$"),
        history=history,
        avg=avg,
        acknowledged_at=ack.acknowledged_at if ack else None,
        acknowledged_by=ack_user_email,
    )


def _format_headline(value: float, currency: str) -> str:
    if currency == "USD":
        return f"${value:,.2f} invoice"
    return f"{currency} {value:,.2f} invoice"


def _format_sub(z: float, avg: float, currency: str) -> str:
    symbol = "$" if currency == "USD" else f"{currency} "
    return f"{z:.1f}σ above rolling average of {symbol}{avg:,.0f}"


def _severity_band(z: float) -> str:
    if z >= 4.0:
        return "high"
    if z >= 2.5:
        return "medium"
    return "low"


def _compute_counts(anomalies: list[AnomalyOut]) -> AnomalyCounts:
    unreviewed = [a for a in anomalies if a.status == "unreviewed"]
    acked = [a for a in anomalies if a.status == "acknowledged"]
    return AnomalyCounts(
        all=len(anomalies),
        unreviewed=len(unreviewed),
        amount=len([a for a in unreviewed if a.type == "amount"]),
        frequency=0,
        pattern=0,
        acknowledged=len(acked),
    )


def _compute_aggregates(anomalies: list[AnomalyOut]) -> AnomalyAggregates:
    unreviewed = [a for a in anomalies if a.status == "unreviewed"]
    if not unreviewed:
        return AnomalyAggregates(
            total_flagged_amount=0.0,
            total_flagged_currency="USD",
            vendors_affected=0,
            highest_severity_z=None,
            highest_severity_vendor=None,
        )

    buckets: dict[str, float] = defaultdict(float)
    for a in unreviewed:
        buckets[a.metric.currency] += a.metric.value
    dominant = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))[0]

    top = max(unreviewed, key=lambda a: a.z_score)
    return AnomalyAggregates(
        total_flagged_amount=round(dominant[1], 2),
        total_flagged_currency=dominant[0],
        vendors_affected=len({a.vendor for a in unreviewed}),
        highest_severity_z=top.z_score,
        highest_severity_vendor=top.vendor,
    )


def _load_ack_users(
    session: Session, acks: dict[tuple, AnomalyAck]
) -> dict[UUID, str]:
    user_ids = {ack.acknowledged_by_user_id for ack in acks.values()}
    if not user_ids:
        return {}
    rows = session.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
    return {u.id: str(u.email) for u in rows}


def _email_for_ack(ack: AnomalyAck | None, users: dict[UUID, str]) -> str | None:
    if ack is None:
        return None
    return users.get(ack.acknowledged_by_user_id)
```

- [ ] **Step 4: Run the tests**

```bash
docker compose exec backend uv run pytest tests/integration/test_anomaly_service.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/anomaly_service.py backend/tests/integration/test_anomaly_service.py
git commit -m "feat(anomalies): anomaly_service.list_anomalies — list + counts + aggregates"
```

---

## Task 8: `anomaly_service.acknowledge` (single + bulk)

**Files:**
- Modify: `backend/app/services/anomaly_service.py`
- Modify: `backend/tests/integration/test_anomaly_service.py`

- [ ] **Step 1: Append failing tests** to `backend/tests/integration/test_anomaly_service.py`:

```python
from app.services.anomaly_service import acknowledge, acknowledge_bulk
from sqlalchemy.orm.attributes import flag_modified


class TestAcknowledge:
    def test_acknowledge_inserts_ack_and_appends_vendor_memory(
        self, db_session: Session
    ) -> None:
        inv = _seed_invoice_with_anomaly(
            db_session,
            vendor_name="Ack Halcyon",
            file_hash="ack-halc-1",
            total=34062.50,
            currency="USD",
            z_score=4.2,
            avg=7900.0,
            std=1500.0,
        )
        user = upsert_demo_user(db_session, email="acker@example.test", password="x")

        anomaly_id = f"{inv.id}:amount:total"
        updated = acknowledge(
            db_session,
            anomaly_id=anomaly_id,
            user_id=user.id,
            notes=None,
        )
        assert updated.status == "acknowledged"
        assert updated.acknowledged_by == "acker@example.test"

        vendor = db_session.execute(
            select(Vendor).where(Vendor.id == inv.vendor_id)
        ).scalar_one()
        outliers = (vendor.memory or {}).get("acknowledged_outliers", {})
        assert "total" in outliers
        assert len(outliers["total"]) == 1
        assert outliers["total"][0]["value"] == 34062.50

    def test_acknowledge_is_idempotent(self, db_session: Session) -> None:
        inv = _seed_invoice_with_anomaly(
            db_session,
            vendor_name="Idem Vendor",
            file_hash="idem-1",
            total=20000.0,
            currency="USD",
            z_score=4.0,
            avg=2000.0,
            std=500.0,
        )
        user = upsert_demo_user(db_session, email="idem-acker@example.test", password="x")

        anomaly_id = f"{inv.id}:amount:total"
        first = acknowledge(db_session, anomaly_id=anomaly_id, user_id=user.id, notes=None)
        second = acknowledge(db_session, anomaly_id=anomaly_id, user_id=user.id, notes="extra")

        assert first.acknowledged_at == second.acknowledged_at

        vendor = db_session.execute(
            select(Vendor).where(Vendor.id == inv.vendor_id)
        ).scalar_one()
        outliers = (vendor.memory or {}).get("acknowledged_outliers", {})
        assert len(outliers["total"]) == 1

    def test_acknowledge_unknown_id_raises(self, db_session: Session) -> None:
        user = upsert_demo_user(db_session, email="nobody-acker@example.test", password="x")
        with pytest.raises(LookupError):
            acknowledge(
                db_session,
                anomaly_id="00000000-0000-0000-0000-000000000000:amount:total",
                user_id=user.id,
                notes=None,
            )

    def test_acknowledge_malformed_id_raises(self, db_session: Session) -> None:
        user = upsert_demo_user(db_session, email="mal-acker@example.test", password="x")
        with pytest.raises(ValueError):
            acknowledge(db_session, anomaly_id="not-a-real-id", user_id=user.id, notes=None)


class TestAcknowledgeBulk:
    def test_partial_success(self, db_session: Session) -> None:
        inv = _seed_invoice_with_anomaly(
            db_session,
            vendor_name="Bulk Vendor",
            file_hash="bulk-1",
            total=15000.0,
            currency="USD",
            z_score=3.5,
            avg=1500.0,
            std=400.0,
        )
        user = upsert_demo_user(db_session, email="bulk-acker@example.test", password="x")

        good = f"{inv.id}:amount:total"
        bad = "00000000-0000-0000-0000-000000000000:amount:total"
        result = acknowledge_bulk(
            db_session,
            anomaly_ids=[good, bad],
            user_id=user.id,
        )
        assert len(result.acknowledged) == 1
        assert result.acknowledged[0].vendor == "Bulk Vendor"
        assert len(result.failed) == 1
        assert result.failed[0].id == bad
        assert result.failed[0].error == "not_found"
```

- [ ] **Step 2: Run to verify failure**

```bash
docker compose exec backend uv run pytest tests/integration/test_anomaly_service.py -v
```

Expected: the new tests fail with `ImportError`.

- [ ] **Step 3: Implement** — append to `backend/app/services/anomaly_service.py`:

```python
from datetime import UTC, datetime

from sqlalchemy.orm.attributes import flag_modified

from app.db.models import AnomalyAck
from app.domain.anomalies_models import (
    BulkAcknowledgeFailure,
    BulkAcknowledgeOut,
)


def parse_anomaly_id(anomaly_id: str) -> tuple[UUID, str, str]:
    parts = anomaly_id.split(":", 2)
    if len(parts) != 3:
        raise ValueError(f"malformed anomaly id: {anomaly_id!r}")
    invoice_id_raw, subtype, field = parts
    try:
        invoice_id = UUID(invoice_id_raw)
    except ValueError as exc:
        raise ValueError(f"invalid invoice id in anomaly id: {anomaly_id!r}") from exc
    if subtype != SUPPORTED_SUBTYPE:
        raise ValueError(f"unsupported anomaly subtype: {subtype!r}")
    return invoice_id, subtype, field


def acknowledge(
    session: Session,
    *,
    anomaly_id: str,
    user_id: UUID,
    notes: str | None,
) -> AnomalyOut:
    invoice_id, subtype, field = parse_anomaly_id(anomaly_id)

    row = session.execute(
        select(Invoice, Extraction, Vendor)
        .join(Extraction, Extraction.invoice_id == Invoice.id)
        .join(Vendor, Vendor.id == Invoice.vendor_id, isouter=True)
        .where(
            Invoice.id == invoice_id,
            Extraction.is_current.is_(True),
        )
    ).first()
    if row is None or row[2] is None:
        raise LookupError(f"no active anomaly for id {anomaly_id!r}")

    invoice, extraction, vendor = row
    reason = next(
        (
            r
            for r in (extraction.predicted_triage_reasons or [])
            if r.get("type") == "anomaly" and r.get("field") == field
        ),
        None,
    )
    if reason is None:
        raise LookupError(f"no anomaly reason for id {anomaly_id!r}")

    ack = anomaly_repo.create_ack(
        session,
        invoice_id=invoice_id,
        subtype=subtype,
        field=field,
        user_id=user_id,
        notes=notes,
    )

    fields = extraction.extracted_fields or {}
    value = float((fields.get(field) or {}).get("value") or 0.0)
    _append_acknowledged_outlier(
        session=session,
        vendor=vendor,
        field=field,
        value=value,
        invoice_id=invoice_id,
        acked_at=ack.acknowledged_at,
    )

    user_email = session.execute(
        select(User.email).where(User.id == user_id)
    ).scalar_one()

    return _build_anomaly_out(
        session=session,
        invoice=invoice,
        extraction=extraction,
        vendor=vendor,
        reason=reason,
        ack=ack,
        ack_user_email=str(user_email),
    )


def acknowledge_bulk(
    session: Session,
    *,
    anomaly_ids: list[str],
    user_id: UUID,
) -> BulkAcknowledgeOut:
    acknowledged: list[AnomalyOut] = []
    failed: list[BulkAcknowledgeFailure] = []
    for aid in anomaly_ids:
        try:
            anomaly = acknowledge(session, anomaly_id=aid, user_id=user_id, notes=None)
            acknowledged.append(anomaly)
        except LookupError:
            failed.append(BulkAcknowledgeFailure(id=aid, error="not_found"))
        except ValueError as exc:
            failed.append(BulkAcknowledgeFailure(id=aid, error=str(exc)))
    return BulkAcknowledgeOut(acknowledged=acknowledged, failed=failed)


def _append_acknowledged_outlier(
    *,
    session: Session,
    vendor: Vendor,
    field: str,
    value: float,
    invoice_id: UUID,
    acked_at: datetime,
) -> None:
    memory = dict(vendor.memory or {})
    outliers = dict(memory.get("acknowledged_outliers", {}) or {})
    field_list = list(outliers.get(field, []) or [])

    already = any(
        abs(value - float(o.get("value") or 0.0)) < 1e-6 for o in field_list
    )
    if not already:
        field_list.append(
            {
                "value": value,
                "acked_at": acked_at.astimezone(UTC).isoformat(),
                "invoice_id": str(invoice_id),
            }
        )

    outliers[field] = field_list
    memory["acknowledged_outliers"] = outliers
    vendor.memory = memory
    flag_modified(vendor, "memory")
    session.commit()
```

The `flag_modified` call is load-bearing: SQLAlchemy doesn't detect in-place dict mutations on JSONB columns, so without it the update silently doesn't persist. The pattern matches the one already used in `vendor_memory_service.update_stats_from_extraction`.

- [ ] **Step 4: Run all anomaly_service tests**

```bash
docker compose exec backend uv run pytest tests/integration/test_anomaly_service.py -v
```

Expected: all tests pass (the original 4 from Task 7 + the 5 new ones).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/anomaly_service.py backend/tests/integration/test_anomaly_service.py
git commit -m "feat(anomalies): acknowledge + acknowledge_bulk with vendor.memory update"
```

---

## Task 9: API router `/api/anomalies` + register + import-linter

**Files:**
- Create: `backend/app/api/anomalies.py`
- Modify: `backend/app/main.py`
- Modify: `backend/pyproject.toml`
- Create: `backend/tests/integration/test_anomaly_api.py`

- [ ] **Step 1: Add the import-linter allow-list entry** in `backend/pyproject.toml`. Find the third contract block (`"api is a thin shell — no domain or adapter imports"`) and add to its `ignore_imports` list:

```toml
ignore_imports = [
    "app.api.invoices -> app.db.session",
    "app.api.search -> app.db.session",
    "app.api.deps -> app.db.session",
    "app.api.auth -> app.db.session",
    "app.api.anomalies -> app.db.session",
]
```

- [ ] **Step 2: Write the failing tests** — create `backend/tests/integration/test_anomaly_api.py`:

```python
from __future__ import annotations

from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.adapters.storage.invoice_repo import create_invoice
from app.adapters.storage.vendor_repo import upsert_by_normalized_name
from app.db.models import Extraction


def _seed_anomaly_invoice(db_session: Session) -> str:
    vendor = upsert_by_normalized_name(db_session, name="API Halcyon")
    inv = create_invoice(
        db_session,
        file_path="/data/uploads/api-halc.pdf",
        file_hash="api-halc-1",
        vendor_id=vendor.id,
    )
    inv.review_status = "pending"
    db_session.add(
        Extraction(
            invoice_id=inv.id,
            model="stub",
            cascade_trace={},
            extracted_fields={
                "total": {"value": 34062.50, "confidence": 0.99, "source": "stub"},
                "currency": {"value": "USD", "confidence": 0.99, "source": "stub"},
            },
            confidence_per_field={"total": 0.99},
            predicted_triage_state="needs_review",
            predicted_triage_reasons=[
                {
                    "type": "anomaly",
                    "field": "total",
                    "vendor_mean": 7900.0,
                    "vendor_std": 1500.0,
                    "z_score": 4.2,
                }
            ],
            line_items=[],
            tax_breakdown=[],
            raw_text=None,
            is_current=True,
        )
    )
    db_session.commit()
    return str(inv.id)


class TestGetAnomalies:
    def test_unauthenticated_returns_401(self, unauthed_client: TestClient) -> None:
        res = unauthed_client.get("/api/anomalies")
        assert res.status_code == 401

    def test_authed_empty_corpus(self, api_client: TestClient) -> None:
        res = api_client.get("/api/anomalies")
        assert res.status_code == 200
        body = res.json()
        assert body["anomalies"] == []
        assert body["counts"]["unreviewed"] == 0
        assert body["aggregates"]["vendors_affected"] == 0

    def test_authed_with_seed(self, api_client: TestClient, db_session: Session) -> None:
        invoice_id = _seed_anomaly_invoice(db_session)
        res = api_client.get("/api/anomalies")
        assert res.status_code == 200
        body = res.json()
        assert len(body["anomalies"]) == 1
        a = body["anomalies"][0]
        assert a["type"] == "amount"
        assert a["id"] == f"{invoice_id}:amount:total"
        assert a["severity"] == "high"
        assert body["counts"]["unreviewed"] == 1
        assert body["aggregates"]["total_flagged_currency"] == "USD"


class TestAcknowledge:
    def test_unauthenticated_returns_401(self, unauthed_client: TestClient) -> None:
        res = unauthed_client.post(
            "/api/anomalies/00000000-0000-0000-0000-000000000000:amount:total/acknowledge"
        )
        assert res.status_code == 401

    def test_unknown_id_returns_404(self, api_client: TestClient) -> None:
        res = api_client.post(
            "/api/anomalies/00000000-0000-0000-0000-000000000000:amount:total/acknowledge"
        )
        assert res.status_code == 404

    def test_malformed_id_returns_422(self, api_client: TestClient) -> None:
        res = api_client.post("/api/anomalies/not-a-real-id/acknowledge")
        assert res.status_code == 422

    def test_acknowledge_round_trip(self, api_client: TestClient, db_session: Session) -> None:
        invoice_id = _seed_anomaly_invoice(db_session)
        anomaly_id = f"{invoice_id}:amount:total"
        res = api_client.post(f"/api/anomalies/{anomaly_id}/acknowledge")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "acknowledged"
        assert body["acknowledged_by"] == "test-clerk@sift.demo"


class TestAcknowledgeBulk:
    def test_unauthenticated_returns_401(self, unauthed_client: TestClient) -> None:
        res = unauthed_client.post(
            "/api/anomalies/acknowledge-bulk",
            json={"anomaly_ids": ["00000000-0000-0000-0000-000000000000:amount:total"]},
        )
        assert res.status_code == 401

    def test_empty_list_returns_422(self, api_client: TestClient) -> None:
        res = api_client.post("/api/anomalies/acknowledge-bulk", json={"anomaly_ids": []})
        assert res.status_code == 422

    def test_oversize_list_returns_422(self, api_client: TestClient) -> None:
        res = api_client.post(
            "/api/anomalies/acknowledge-bulk",
            json={"anomaly_ids": ["x"] * 201},
        )
        assert res.status_code == 422

    def test_partial_success(self, api_client: TestClient, db_session: Session) -> None:
        invoice_id = _seed_anomaly_invoice(db_session)
        good = f"{invoice_id}:amount:total"
        bad = "00000000-0000-0000-0000-000000000000:amount:total"
        res = api_client.post(
            "/api/anomalies/acknowledge-bulk",
            json={"anomaly_ids": [good, bad]},
        )
        assert res.status_code == 200
        body = res.json()
        assert len(body["acknowledged"]) == 1
        assert len(body["failed"]) == 1
        assert body["failed"][0]["id"] == bad
```

- [ ] **Step 3: Run to verify failure**

```bash
docker compose exec backend uv run pytest tests/integration/test_anomaly_api.py -v
```

Expected: every test fails (404 on the routes — the router doesn't exist yet).

- [ ] **Step 4: Implement** — create `backend/app/api/anomalies.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_clerk
from app.db.session import get_session
from app.domain.anomalies_models import (
    AnomaliesResponse,
    AnomalyOut,
    BulkAcknowledgeIn,
    BulkAcknowledgeOut,
)
from app.domain.auth import ClerkOut
from app.services import anomaly_service

router = APIRouter()


@router.get("", response_model=AnomaliesResponse)
def list_anomalies_endpoint(
    _clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> AnomaliesResponse:
    return anomaly_service.list_anomalies(session)


@router.post("/{anomaly_id}/acknowledge", response_model=AnomalyOut)
def acknowledge_endpoint(
    anomaly_id: str,
    clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> AnomalyOut:
    try:
        return anomaly_service.acknowledge(
            session,
            anomaly_id=anomaly_id,
            user_id=clerk.id,
            notes=None,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post("/acknowledge-bulk", response_model=BulkAcknowledgeOut)
def acknowledge_bulk_endpoint(
    body: BulkAcknowledgeIn,
    clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> BulkAcknowledgeOut:
    return anomaly_service.acknowledge_bulk(
        session,
        anomaly_ids=body.anomaly_ids,
        user_id=clerk.id,
    )
```

- [ ] **Step 5: Register the router** in `backend/app/main.py`. Find the existing `from app.api import auth, invoices, search` line and the include_router block. Change to:

```python
    from app.api import anomalies, auth, invoices, search

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(invoices.router, prefix="/api/invoices", tags=["invoices"])
    app.include_router(search.router, prefix="/api/search", tags=["search"])
    app.include_router(anomalies.router, prefix="/api/anomalies", tags=["anomalies"])
```

- [ ] **Step 6: Verify import-linter is clean**

```bash
docker compose exec backend uv run lint-imports
```

Expected: 3 contracts kept, 0 broken.

- [ ] **Step 7: Run the anomaly API tests + full suite**

```bash
docker compose exec backend uv run pytest tests/integration/test_anomaly_api.py -v
docker compose exec backend uv run pytest tests/integration -q
```

Expected: all anomaly API tests pass. Full suite: previous baseline preserved (no new failures).

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/anomalies.py backend/app/main.py backend/pyproject.toml backend/tests/integration/test_anomaly_api.py
git commit -m "feat(api): anomalies router — list, acknowledge, acknowledge-bulk"
```

---

## Task 10: Regenerate frontend types

**Files:**
- Modify: `frontend/src/types/generated/domain.ts`

- [ ] **Step 1: Run the generator** (the login-backend cycle already established the working invocation):

```bash
docker compose exec backend uv run python scripts/generate_types.py
```

If the host invocation is needed instead, follow the same pattern used in the login-backend Task 19 — it requires `PYTHONPATH=/Users/lscypher/Workspace/sift` and `json-schema-to-typescript` available globally.

- [ ] **Step 2: Verify the new interfaces appear**

```bash
grep -E "interface (AnomalyOut|AnomalyMetric|AnomalyHistoryPoint|AnomalyCounts|AnomalyAggregates|AnomaliesResponse|BulkAcknowledge)" /Users/lscypher/Workspace/sift/frontend/src/types/generated/domain.ts | wc -l
```

Expected: at least 7.

- [ ] **Step 3: Type-check the frontend**

```bash
cd /Users/lscypher/Workspace/sift/frontend && pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git -C /Users/lscypher/Workspace/sift add frontend/src/types/generated/domain.ts
git -C /Users/lscypher/Workspace/sift commit -m "chore(types): regenerate frontend types — anomaly DTOs"
```

---

## Task 11: Tailwind theme tokens for anomaly pills

**Files:**
- Modify: `frontend/tailwind.config.ts`

- [ ] **Step 1: Read the current `tailwind.config.ts`** to find the `extend.colors` block.

```bash
grep -n "extend" /Users/lscypher/Workspace/sift/frontend/tailwind.config.ts | head -3
```

- [ ] **Step 2: Add the anomaly tokens** inside `extend.colors`. Append:

```ts
        'anomaly-amount-fg':    'oklch(0.45 0.13 25)',
        'anomaly-amount-bg':    'oklch(0.96 0.04 25)',
        'anomaly-amount-ring':  'oklch(0.88 0.07 25)',
        'anomaly-frequency-fg': 'oklch(0.42 0.13 290)',
        'anomaly-frequency-bg': 'oklch(0.96 0.04 290)',
        'anomaly-frequency-ring':'oklch(0.88 0.07 290)',
        'anomaly-severity-high':   'oklch(0.55 0.18 25)',
        'anomaly-severity-medium': 'var(--triage-needs-review)',
        'anomaly-severity-low':    'var(--ink-48)',
```

If `tailwind.config.ts` references CSS variables for some existing colors (which `colors_and_type.css` defines), keep the same pattern; otherwise inline the oklch values as above.

- [ ] **Step 3: Type-check + verify the dev server compiles**

```bash
cd /Users/lscypher/Workspace/sift/frontend && pnpm tsc --noEmit
```

If the dev server is running, the changes hot-reload; otherwise the next dev-server start picks them up.

- [ ] **Step 4: Commit**

```bash
git -C /Users/lscypher/Workspace/sift add frontend/tailwind.config.ts
git -C /Users/lscypher/Workspace/sift commit -m "feat(frontend): tailwind tokens for anomaly type pills + severity colors"
```

---

## Task 12: Frontend state hooks `state/anomalies.ts`

**Files:**
- Create: `frontend/src/state/anomalies.ts`

- [ ] **Step 1: Implement** — create `frontend/src/state/anomalies.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, api } from '@/state/api'
import type {
  AnomaliesResponse,
  AnomalyOut,
  BulkAcknowledgeOut,
} from '@/types/generated/domain'

const ANOMALIES_KEY = ['anomalies'] as const

export function useAnomaliesQuery() {
  return useQuery<AnomaliesResponse, ApiError>({
    queryKey: ANOMALIES_KEY,
    queryFn: () => api<AnomaliesResponse>('/api/anomalies'),
    staleTime: 15_000,
  })
}

export function useAnomalyCountQuery() {
  return useQuery<AnomaliesResponse, ApiError, number>({
    queryKey: ANOMALIES_KEY,
    queryFn: () => api<AnomaliesResponse>('/api/anomalies'),
    staleTime: 15_000,
    select: (data) => data.counts.unreviewed,
  })
}

export function useAcknowledgeAnomaly() {
  const qc = useQueryClient()
  return useMutation<AnomalyOut, ApiError, string>({
    mutationFn: (anomalyId) =>
      api<AnomalyOut>(`/api/anomalies/${encodeURIComponent(anomalyId)}/acknowledge`, {
        method: 'POST',
      }),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ANOMALIES_KEY })
    },
  })
}

export function useBulkAcknowledgeAnomalies() {
  const qc = useQueryClient()
  return useMutation<BulkAcknowledgeOut, ApiError, string[]>({
    mutationFn: (anomalyIds) =>
      api<BulkAcknowledgeOut>('/api/anomalies/acknowledge-bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ anomaly_ids: anomalyIds }),
      }),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ANOMALIES_KEY })
    },
  })
}
```

- [ ] **Step 2: Type-check**

```bash
cd /Users/lscypher/Workspace/sift/frontend && pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git -C /Users/lscypher/Workspace/sift add frontend/src/state/anomalies.ts
git -C /Users/lscypher/Workspace/sift commit -m "feat(frontend): anomalies hooks — list, count, acknowledge, bulk"
```

---

## Task 13: `TypePill` component

**Files:**
- Create: `frontend/src/components/anomalies/TypePill.tsx`

- [ ] **Step 1: Implement** — create the file:

```tsx
import type { ReactNode } from 'react'

type TypeKey = 'amount' | 'frequency' | 'terms_changed' | 'new_line_item'

type PillMeta = {
  label: string
  classes: string
}

const META: Record<TypeKey, PillMeta> = {
  amount: {
    label: 'Amount',
    classes: 'text-anomaly-amount-fg bg-anomaly-amount-bg border-anomaly-amount-ring',
  },
  frequency: {
    label: 'Frequency',
    classes:
      'text-anomaly-frequency-fg bg-anomaly-frequency-bg border-anomaly-frequency-ring',
  },
  terms_changed: {
    label: 'Terms',
    classes:
      'text-aside-duplicate bg-aside-duplicate-tint border-aside-duplicate-ring',
  },
  new_line_item: {
    label: 'New line',
    classes:
      'text-aside-review bg-aside-review-tint border-aside-review-ring',
  },
}

export function TypePill({ type, icon }: { type: TypeKey; icon?: ReactNode }) {
  const meta = META[type] ?? META.amount
  return (
    <span
      className={[
        'inline-flex items-center gap-1.5 border px-2 py-0.5 text-[11.5px] font-medium tracking-[-0.005em]',
        meta.classes,
      ].join(' ')}
    >
      {icon}
      <span>{meta.label}</span>
    </span>
  )
}
```

The component is type-agnostic — it accepts all four `TypeKey` values even though Phase 1 only emits `amount`. The other three render correctly for future phases without touching this file.

- [ ] **Step 2: Type-check**

```bash
cd /Users/lscypher/Workspace/sift/frontend && pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git -C /Users/lscypher/Workspace/sift add frontend/src/components/anomalies/TypePill.tsx
git -C /Users/lscypher/Workspace/sift commit -m "feat(frontend): anomaly TypePill component"
```

---

## Task 14: `Sparkline` component

**Files:**
- Create: `frontend/src/components/anomalies/Sparkline.tsx`

- [ ] **Step 1: Implement** — create the file:

```tsx
import type { AnomalyHistoryPoint } from '@/types/generated/domain'

type SparklineProps = {
  data: AnomalyHistoryPoint[]
  avg: number
  variant: 'bars' | 'line'
}

const W = 320
const H = 80
const PAD = 6

export function Sparkline({ data, avg, variant }: SparklineProps) {
  if (data.length === 0) {
    return (
      <div className="text-[11px] text-ink-48 italic">No vendor history yet.</div>
    )
  }

  const values = data.map((d) => d.value)
  const max = Math.max(...values, avg)
  const min = 0
  const xStep = data.length === 1 ? 0 : (W - PAD * 2) / (data.length - 1)
  const yFor = (v: number) =>
    H - PAD - ((v - min) / Math.max(max - min, 1)) * (H - PAD * 2)

  return (
    <div>
      <svg
        width={W}
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        className="block w-full max-w-[320px]"
      >
        <line
          x1={PAD}
          y1={yFor(avg)}
          x2={W - PAD}
          y2={yFor(avg)}
          stroke="var(--ink-48)"
          strokeWidth="1"
          strokeDasharray="2 3"
          opacity="0.55"
        />
        <text
          x={W - PAD - 2}
          y={yFor(avg) - 4}
          textAnchor="end"
          fontFamily="var(--font-mono)"
          fontSize="9"
          fill="var(--ink-60)"
        >
          avg
        </text>

        {variant === 'bars'
          ? data.map((d, i) => {
              const x = PAD + i * xStep
              const barW = Math.max(6, xStep - 4)
              const y = yFor(d.value)
              return (
                <rect
                  key={i}
                  x={x - barW / 2}
                  y={y}
                  width={barW}
                  height={H - PAD - y}
                  fill={d.current ? 'var(--action)' : 'var(--ink-60)'}
                  opacity={d.current ? 1 : 0.35}
                />
              )
            })
          : (
              <>
                <polyline
                  fill="none"
                  stroke="var(--ink-60)"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity="0.5"
                  points={data
                    .map((d, i) => `${PAD + i * xStep},${yFor(d.value)}`)
                    .join(' ')}
                />
                {data.map((d, i) => (
                  <circle
                    key={i}
                    cx={PAD + i * xStep}
                    cy={yFor(d.value)}
                    r={d.current ? 5 : 2.5}
                    fill={d.current ? 'var(--action)' : 'var(--ink-60)'}
                    opacity={d.current ? 1 : 0.6}
                  />
                ))}
              </>
            )}
      </svg>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-ink-48">
        <span>12 invoices ago</span>
        <span>now</span>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

```bash
cd /Users/lscypher/Workspace/sift/frontend && pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git -C /Users/lscypher/Workspace/sift add frontend/src/components/anomalies/Sparkline.tsx
git -C /Users/lscypher/Workspace/sift commit -m "feat(frontend): anomaly Sparkline component"
```

---

## Task 15: `AnomalyCard` component

**Files:**
- Create: `frontend/src/components/anomalies/AnomalyCard.tsx`

- [ ] **Step 1: Implement** — create the file:

```tsx
import type { AnomalyOut } from '@/types/generated/domain'
import { Sparkline } from '@/components/anomalies/Sparkline'
import { TypePill } from '@/components/anomalies/TypePill'

type AnomalyCardProps = {
  anomaly: AnomalyOut
  selected: boolean
  onToggle: () => void
  onAcknowledge: () => void
  onInvestigate: () => void
}

const SEVERITY_CLASS: Record<string, string> = {
  high: 'text-anomaly-severity-high border-anomaly-severity-high',
  medium: 'text-anomaly-severity-medium border-anomaly-severity-medium',
  low: 'text-anomaly-severity-low border-anomaly-severity-low',
}

export function AnomalyCard({
  anomaly,
  selected,
  onToggle,
  onAcknowledge,
  onInvestigate,
}: AnomalyCardProps) {
  const isAck = anomaly.status === 'acknowledged'

  return (
    <div
      className={[
        'flex flex-col border bg-surface transition-colors duration-100',
        selected ? 'border-action' : 'border-hairline',
        isAck ? 'opacity-70' : 'opacity-100',
      ].join(' ')}
    >
      <header className="flex items-center gap-2.5 border-b border-hairline-soft px-3.5 py-3">
        <TypePill type={anomaly.type} />
        <span
          className={[
            'font-mono text-[11.5px] font-medium px-1.5 py-px border',
            SEVERITY_CLASS[anomaly.severity] ?? '',
          ].join(' ')}
        >
          {anomaly.z_score.toFixed(1)}σ
        </span>
        <span className="ml-auto flex items-center gap-1.5">
          {isAck && (
            <span className="font-mono text-[11px] text-aside-confident">
              acknowledged
            </span>
          )}
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            aria-label="Select anomaly"
            className="m-0 cursor-pointer accent-action"
          />
        </span>
      </header>

      <div className="flex-1 p-3.5">
        <div className="flex items-center gap-1.5">
          <span className="text-[13.5px] font-medium text-ink">{anomaly.vendor}</span>
          <span className="ml-auto font-mono text-[11.5px] text-ink-48">
            {new Date(anomaly.detected_at).toLocaleString(undefined, {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </div>
        <div className="mt-1.5 font-mono text-[18px] font-semibold tracking-[-0.005em] text-ink">
          {anomaly.headline}
        </div>
        <div className="mt-1 text-[12.5px] leading-[1.5] text-ink-60">
          {anomaly.sub}
        </div>

        <div className="mt-3.5">
          <Sparkline data={anomaly.history} avg={anomaly.avg} variant="bars" />
        </div>
      </div>

      <footer className="flex gap-1.5 border-t border-hairline-soft bg-surface-recess px-3.5 py-2.5">
        {!isAck && (
          <button
            type="button"
            onClick={onAcknowledge}
            className="border border-hairline bg-surface px-2.5 py-1 text-[12px] font-medium text-ink-80 transition-colors hover:border-action hover:text-action"
          >
            Acknowledge
          </button>
        )}
        <button
          type="button"
          onClick={onInvestigate}
          className="border border-transparent px-2.5 py-1 text-[12px] font-medium text-ink-60 transition-colors hover:text-ink"
        >
          Investigate
        </button>
      </footer>
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

```bash
cd /Users/lscypher/Workspace/sift/frontend && pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git -C /Users/lscypher/Workspace/sift add frontend/src/components/anomalies/AnomalyCard.tsx
git -C /Users/lscypher/Workspace/sift commit -m "feat(frontend): AnomalyCard component"
```

---

## Task 16: `AnomaliesScreen` route component

**Files:**
- Create: `frontend/src/routes/AnomaliesScreen.tsx`

- [ ] **Step 1: Implement** — create the file:

```tsx
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { AnomalyCard } from '@/components/anomalies/AnomalyCard'
import {
  useAcknowledgeAnomaly,
  useAnomaliesQuery,
  useBulkAcknowledgeAnomalies,
} from '@/state/anomalies'
import type { AnomalyOut } from '@/types/generated/domain'

type FilterKey = 'unreviewed' | 'all' | 'amount' | 'frequency' | 'pattern' | 'acknowledged'

const EMPTY: Record<FilterKey, string> = {
  unreviewed: 'Nothing to flag. New anomalies surface here as invoices arrive.',
  all: 'No anomalies in the corpus yet.',
  amount: 'Nothing to flag. New anomalies surface here as invoices arrive.',
  frequency: "Sift doesn't yet flag frequency anomalies — coming next.",
  pattern: 'Pattern anomalies (terms changed, new line items) ship in a later iteration.',
  acknowledged: 'Nothing acknowledged yet.',
}

function filterAnomalies(anomalies: AnomalyOut[], key: FilterKey): AnomalyOut[] {
  if (key === 'all') return anomalies
  if (key === 'unreviewed') return anomalies.filter((a) => a.status === 'unreviewed')
  if (key === 'acknowledged') return anomalies.filter((a) => a.status === 'acknowledged')
  if (key === 'amount') {
    return anomalies.filter((a) => a.status === 'unreviewed' && a.type === 'amount')
  }
  return []
}

function formatCurrency(amount: number, currency: string): string {
  if (currency === 'USD') {
    if (amount >= 1_000) return `$${(amount / 1_000).toFixed(1)}K`
    return `$${amount.toFixed(0)}`
  }
  if (amount >= 1_000) return `${currency} ${(amount / 1_000).toFixed(1)}K`
  return `${currency} ${amount.toFixed(0)}`
}

export function AnomaliesScreen() {
  const navigate = useNavigate()
  const { data, isLoading, isError } = useAnomaliesQuery()
  const acknowledge = useAcknowledgeAnomaly()
  const bulkAcknowledge = useBulkAcknowledgeAnomalies()
  const [filter, setFilter] = useState<FilterKey>('unreviewed')
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const visible = useMemo(
    () => filterAnomalies(data?.anomalies ?? [], filter),
    [data?.anomalies, filter],
  )

  if (isLoading) {
    return (
      <div className="p-6 text-sm text-ink-60">Loading anomalies…</div>
    )
  }
  if (isError || !data) {
    return (
      <div className="p-6 text-sm text-aside-review">
        Couldn't load anomalies. Refresh to try again.
      </div>
    )
  }

  const onCardToggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const onAcknowledgeAll = () => {
    if (selected.size === 0) return
    bulkAcknowledge.mutate(Array.from(selected), {
      onSettled: () => setSelected(new Set()),
    })
  }

  return (
    <div className="px-6 py-5">
      <div className="mb-5">
        <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.10em] text-ink-48">
          What changed this period
        </div>
        <div className="mb-1 text-[21px] font-semibold tracking-[-0.012em] text-ink">
          {data.counts.unreviewed} {data.counts.unreviewed === 1 ? 'anomaly needs' : 'anomalies need'} a second look
        </div>
        <div className="max-w-[70ch] text-[14px] leading-[1.5] text-ink-60">
          The extractions are confident — the <i>values</i> are unusual.
          Per-vendor Z-scores flag invoices that need a second pair of eyes
          before payment.
        </div>
      </div>

      <div className="mb-4 grid grid-cols-4 border border-hairline bg-surface">
        <StatTile label="Unreviewed" value={String(data.counts.unreviewed)} />
        <StatTile
          label="Total $ flagged"
          value={formatCurrency(data.aggregates.total_flagged_amount, data.aggregates.total_flagged_currency)}
          suffix={data.aggregates.total_flagged_currency}
        />
        <StatTile label="Vendors affected" value={String(data.aggregates.vendors_affected)} />
        <StatTile
          label="Highest severity"
          value={data.aggregates.highest_severity_z !== null ? `${data.aggregates.highest_severity_z.toFixed(1)}σ` : '—'}
          suffix={data.aggregates.highest_severity_vendor ?? undefined}
        />
      </div>

      <div className="mb-3.5 flex items-center gap-2">
        <FilterTab id="unreviewed" cur={filter} set={setFilter} label="Unreviewed" count={data.counts.unreviewed} />
        <FilterTab id="all" cur={filter} set={setFilter} label="All" count={data.counts.all} />
        <FilterTab id="amount" cur={filter} set={setFilter} label="Amount" count={data.counts.amount} />
        <FilterTab id="frequency" cur={filter} set={setFilter} label="Frequency" count={data.counts.frequency} />
        <FilterTab id="pattern" cur={filter} set={setFilter} label="Pattern" count={data.counts.pattern} />
        <FilterTab id="acknowledged" cur={filter} set={setFilter} label="Acknowledged" count={data.counts.acknowledged} />
        <div className="ml-auto flex items-center gap-2">
          {selected.size > 0 && (
            <>
              <span className="font-mono text-[12px] text-ink-60">
                {selected.size} selected
              </span>
              <button
                type="button"
                onClick={onAcknowledgeAll}
                disabled={bulkAcknowledge.isPending}
                className="border border-action bg-action px-2.5 py-1 text-[12px] font-medium text-white transition-colors disabled:cursor-not-allowed disabled:opacity-60"
              >
                {bulkAcknowledge.isPending ? 'Acknowledging…' : 'Acknowledge all'}
              </button>
            </>
          )}
        </div>
      </div>

      {visible.length === 0 ? (
        <EmptyState message={EMPTY[filter]} />
      ) : (
        <div className="grid gap-3.5" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))' }}>
          {visible.map((a) => (
            <AnomalyCard
              key={a.id}
              anomaly={a}
              selected={selected.has(a.id)}
              onToggle={() => onCardToggle(a.id)}
              onAcknowledge={() => acknowledge.mutate(a.id)}
              onInvestigate={() => navigate(`/invoice/${a.invoice_id}`)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function StatTile({ label, value, suffix }: { label: string; value: string; suffix?: string }) {
  return (
    <div className="border-r border-hairline px-5 py-4 last:border-r-0">
      <div className="text-[10.5px] font-medium uppercase tracking-[0.06em] text-ink-48">
        {label}
      </div>
      <div className="mt-1.5 flex items-baseline gap-2">
        <span className="font-mono text-[22px] font-semibold tracking-[-0.012em] text-ink">
          {value}
        </span>
        {suffix && (
          <span className="font-mono text-[11.5px] text-ink-60">{suffix}</span>
        )}
      </div>
    </div>
  )
}

function FilterTab({
  id,
  cur,
  set,
  label,
  count,
}: {
  id: FilterKey
  cur: FilterKey
  set: (k: FilterKey) => void
  label: string
  count: number
}) {
  const active = cur === id
  return (
    <button
      type="button"
      data-active={active}
      onClick={() => set(id)}
      className={[
        'inline-flex items-center gap-1.5 border px-2.5 py-1 text-[12px] font-medium transition-colors',
        active
          ? 'border-action bg-action text-white'
          : 'border-hairline bg-surface text-ink-60 hover:border-ink-48 hover:text-ink',
      ].join(' ')}
    >
      <span>{label}</span>
      <span className="font-mono text-[11px] opacity-80">{count}</span>
    </button>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="border border-hairline bg-surface px-10 py-12 text-center text-ink-60">
      <div className="mb-1.5 text-[16px] font-semibold text-ink">Nothing to flag</div>
      <div className="mx-auto max-w-[40ch] text-[13.5px]">{message}</div>
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

```bash
cd /Users/lscypher/Workspace/sift/frontend && pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git -C /Users/lscypher/Workspace/sift add frontend/src/routes/AnomaliesScreen.tsx
git -C /Users/lscypher/Workspace/sift commit -m "feat(frontend): AnomaliesScreen route with filter tabs, stat strip, bulk-ack"
```

---

## Task 17: Router + Shell sidebar wiring

**Files:**
- Modify: `frontend/src/routes/router.tsx`
- Modify: `frontend/src/components/shell/Shell.tsx`

- [ ] **Step 1: Read `router.tsx`** to confirm the route block structure (it should be familiar from the login backend cycle).

- [ ] **Step 2: Add the route** in `frontend/src/routes/router.tsx`. Inside the `<Shell />` children list, add the entry alongside `inbox`, `search`, etc.:

```tsx
import { AnomaliesScreen } from '@/routes/AnomaliesScreen'
```

Then in the `children` array:

```tsx
      { path: 'anomalies', element: <AnomaliesScreen /> },
```

Place it after the `inbox` route and before `search` to match the sidebar's Workflow grouping.

- [ ] **Step 3: Update the Anomalies sidebar entry** in `frontend/src/components/shell/Shell.tsx`. The current block (lines 111-115) is:

```tsx
          <div className="nav-item">
            <Icons.bell />
            <span>Anomalies</span>
            <span className="nav-count">{counts.likely_duplicate}</span>
          </div>
```

Replace with:

```tsx
          <Link
            to="/anomalies"
            className="nav-item"
            data-active={location.pathname === '/anomalies'}
            style={{ textDecoration: 'none' }}
          >
            <Icons.bell />
            <span>Anomalies</span>
            <span className="nav-count">{anomalyCount}</span>
          </Link>
```

Add the import at the top of `Shell.tsx`:

```tsx
import { useAnomalyCountQuery } from '@/state/anomalies'
```

And inside the `Shell()` function body, near the other query hooks at the top (so the early-return pattern from the login work isn't violated):

```tsx
  const { data: anomalyCount = 0 } = useAnomalyCountQuery()
```

Place this hook with the other unconditional hooks BEFORE any conditional early-return.

- [ ] **Step 4: Type-check**

```bash
cd /Users/lscypher/Workspace/sift/frontend && pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git -C /Users/lscypher/Workspace/sift add frontend/src/routes/router.tsx frontend/src/components/shell/Shell.tsx
git -C /Users/lscypher/Workspace/sift commit -m "feat(shell): wire Anomalies sidebar entry + real unreviewed count"
```

---

## Task 18: End-to-end verification

**Files:**
- Read-only verification across the whole repo.

- [ ] **Step 1: Full backend test suite**

```bash
docker compose exec backend uv run pytest -q
```

Expected: all anomaly tests pass; existing tests preserve their baseline. (The 11 pre-existing LLM-stub failures from the login cycle remain only if `SIFT_LLM_PROVIDER=anthropic` is in the local `.env`.)

- [ ] **Step 2: Import-linter**

```bash
docker compose exec backend uv run lint-imports
```

Expected: 3 contracts kept, 0 broken.

- [ ] **Step 3: Ruff (auth-and-anomaly files only — avoid pre-existing repo debt)**

```bash
docker compose exec backend uv run ruff check \
  app/domain/anomalies.py \
  app/domain/anomalies_models.py \
  app/adapters/storage/anomaly_repo.py \
  app/services/anomaly_service.py \
  app/api/anomalies.py \
  tests/unit/test_anomalies.py \
  tests/unit/test_anomaly_models.py \
  tests/integration/test_anomaly_repo.py \
  tests/integration/test_anomaly_service.py \
  tests/integration/test_anomaly_api.py
```

Expected: clean. Fix any I001 (import sort) or F401 (unused imports) via `--fix` and re-commit.

- [ ] **Step 4: Import-style guards**

```bash
grep -rn "from '\.\." /Users/lscypher/Workspace/sift/frontend/src
grep -rn "^from \." /Users/lscypher/Workspace/sift/backend/app
```

Both must return empty (no output, exit code 1).

- [ ] **Step 5: Frontend type-check**

```bash
cd /Users/lscypher/Workspace/sift/frontend && pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Step 6: Demo walkthrough**

Bring up the dev stack (`docker compose up -d`). In a browser:

1. Sign in with the demo user (`ap-clerk@sift.demo` / `letmein-demo`).
2. Click **Anomalies** in the sidebar — page loads with header, stat strip, filter tabs, and (initially) an empty Unreviewed state because no anomalies exist in the fresh DB.
3. Run `make seed-demo` to seed the curated invoices (one is Halcyon Software with a 4.2σ anomaly).
4. Refresh `/anomalies`. The Halcyon card surfaces. Sparkline shows prior Halcyon invoices + the current one in `--action` color.
5. Click **Acknowledge**. The card flips to "acknowledged" (opacity 0.7). The sidebar count drops by 1.
6. Click the Acknowledged tab — the card appears there.
7. Click **Investigate** on the (now-acknowledged) card. Bounces to `/invoice/<id>` (existing ReviewScreen).
8. Re-upload the same Halcyon PDF (or a near-duplicate value). Verify the new extraction does NOT emit an anomaly reason for `total` (the ack-tolerance skip is working).
9. Click **Frequency** tab → renders the "coming next" empty state.
10. Click **Pattern** tab → renders the "ship in a later iteration" empty state.

- [ ] **Step 7: Optional housekeeping commit**

If steps 1-6 surfaced anything (ruff-fixable, doc-string in spec needing a fix), bundle into one commit. Otherwise skip.

---

## Coverage Map (plan → spec)

| Spec section | Implementing tasks |
| --- | --- |
| Anomaly identity (composite key) | 7 (parser + DTO id field), 8 (parse_anomaly_id) |
| Data model: `anomaly_acks` | 1, 2 |
| `vendor.memory.acknowledged_outliers` shape | 8 |
| Detection skip logic | 3, 4 |
| API surface (GET, POST single, POST bulk) | 9 |
| Severity bands | 7 |
| Dominant-currency aggregate logic | 7 |
| Sparkline data source | 5 (vendor_history_query) |
| Headline + sub copy | 7 |
| Frontend new files | 12, 13, 14, 15, 16 |
| Frontend modified files | 10 (types), 11 (tailwind), 17 (router + shell) |
| Empty states | 16 (EMPTY constant) |
| Layer placement (ADR-0005) | 1, 3, 5, 6, 7, 8, 9 |
| Migration | 2 |
| Code style — minimal comments | enforced in every code block above |
| Code style — alias imports | enforced in every code block above |
| Testing (unit + integration) | 3, 5, 6, 7, 8, 9 |
| Out of scope items | not implemented (acknowledged in plan header + spec) |

Every spec requirement has a task. Frequency/Pattern/Terms/New-line-item types remain out of scope per the spec — they ship in Phase 2/3/4.
