"""Invoice repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.db.models import Invoice

def create_invoice(
    session: Session,
    *,
    storage_key: str,
    file_hash: str,
    vendor_id: UUID | None,
    perceptual_hash: str | None = None,
) -> Invoice:
    inv = Invoice(
        storage_key=storage_key,
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

def find_phash_candidates(session: Session) -> list[Invoice]:
    """Invoices with a stored perceptual_hash, for duplicate scanning.

    At demo volume (≤500 invoices) this is a full scan in Python. At
    production scale, add a simhash bucket index.
    """
    return list(
        session.execute(select(Invoice).where(Invoice.perceptual_hash.is_not(None))).scalars()
    )

def set_perceptual_hash(session: Session, *, invoice_id: UUID, perceptual_hash: str) -> None:
    inv = session.get(Invoice, invoice_id)
    if inv is None:
        raise LookupError(f"invoice {invoice_id} not found")
    inv.perceptual_hash = perceptual_hash
    session.flush()

def update_review_status(session: Session, *, invoice_id: UUID, review_status: str) -> Invoice:
    inv = session.get(Invoice, invoice_id)
    if inv is None:
        raise LookupError(f"invoice {invoice_id} not found")
    inv.review_status = review_status
    session.flush()
    return inv

def record_duplicate_dismissal(
    session: Session, *, invoice_id: UUID, dismissed_against_id: UUID
) -> None:
    """Persist that this invoice was dismissed-as-not-a-duplicate against another.

    SQLAlchemy does not detect in-place mutation of JSONB columns — we must
    call `flag_modified(inv, "duplicate_dismissals")` after appending, or the
    change silently doesn't persist.
    """
    inv = session.get(Invoice, invoice_id)
    if inv is None:
        raise LookupError(f"invoice {invoice_id} not found")
    current = list(inv.duplicate_dismissals or [])
    target = str(dismissed_against_id)
    if target not in current:
        current.append(target)
        inv.duplicate_dismissals = current
        flag_modified(inv, "duplicate_dismissals")
    session.flush()
