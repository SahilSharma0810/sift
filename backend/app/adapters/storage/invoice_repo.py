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
        session.execute(select(Invoice).order_by(Invoice.uploaded_at.desc()).limit(limit)).scalars()
    )
