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
    line_items: list[dict[str, Any]] | None = None,
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
