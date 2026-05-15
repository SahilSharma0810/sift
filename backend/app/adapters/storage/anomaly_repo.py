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
