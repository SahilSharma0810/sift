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


def _build_raw_text(
    extracted_fields: dict[str, Any],
    line_items: list[dict[str, Any]] | None,
    tax_breakdown: list[dict[str, Any]] | None,
) -> str:
    """Concatenate every extracted value into a single FTS-searchable string.

    Postgres maintains the tsvector + GIN index automatically from this
    column (see alembic 8c3c0a978b23). Day-4 NL queries route through
    `raw_text fts_matches "..."` clauses on this column.
    """
    chunks: list[str] = []
    for field_data in (extracted_fields or {}).values():
        if isinstance(field_data, dict):
            v = field_data.get("value")
            if v is not None:
                chunks.append(str(v))
    for item in line_items or []:
        if isinstance(item, dict):
            d = item.get("description")
            if d:
                chunks.append(str(d))
    for row in tax_breakdown or []:
        if isinstance(row, dict):
            j = row.get("jurisdiction")
            if j:
                chunks.append(str(j))
    # Single space as separator — tsvector tokenization handles the rest.
    return " ".join(chunks)


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
    line_items: list[dict[str, Any]] | None = None,
    tax_breakdown: list[dict[str, Any]] | None = None,
) -> Extraction:
    """Create a new extraction and mark it `is_current=True`.

    Demotes any previously-current extraction for the same invoice in the
    same flush — preserves the partial-unique constraint without races.
    Also populates `raw_text` for FTS — Postgres maintains the tsvector
    column + GIN index automatically.
    """
    # Demote previous current (if any).
    session.execute(
        update(Extraction)
        .where(Extraction.invoice_id == invoice_id, Extraction.is_current.is_(True))
        .values(is_current=False)
    )
    session.flush()

    ext = Extraction(
        invoice_id=invoice_id,
        model=model,
        extracted_fields=extracted_fields,
        confidence_per_field=confidence_per_field,
        predicted_triage_state=predicted_triage_state,
        predicted_triage_reasons=predicted_triage_reasons,
        cascade_trace=cascade_trace,
        line_items=line_items or [],
        tax_breakdown=tax_breakdown or [],
        raw_text=_build_raw_text(extracted_fields, line_items, tax_breakdown),
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
        update(Extraction).where(Extraction.invoice_id == ext.invoice_id).values(is_current=False)
    )
    session.flush()
    ext.is_current = True
    session.flush()
