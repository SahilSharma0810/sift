"""Clerk-initiated Triage State transitions per ADR-0006.

The four operations the AP Clerk can perform on an Invoice from the
Review Screen and Cmd+K palette:

- **Confirm** — accept the Extraction as ground truth. Triggers
  vendor-stats update so subsequent extractions from the same Vendor
  benefit from accumulated history. Per ADR-0003, stats are updated
  ONLY on confirm so unconfirmed/wrong values never pollute history.
- **Dismiss duplicate** — record that this Invoice is NOT a duplicate of
  another Invoice the system flagged. The dismissal pair is persisted so
  the duplicate detector skips this combination on subsequent
  re-extractions.
- **Mark unprocessable** — failure-mode UX per ADR-0006. Clerk explicit
  decision when retry isn't viable.
- **Retry** — re-run the full extraction pipeline against the same file,
  optionally forcing a higher model tier (Cmd+K "Force Sonnet/Opus").
  Always creates a new Extraction row; the prior row stays on the
  Invoice for audit.

Each function is a thin Triage State transition: ORM read, ORM update,
optional cross-service call (vendor stats on confirm; full pipeline on
retry), commit. Returns the ORM Invoice or ExtractResult for the API
layer to serialize via invoice_queries.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.adapters.storage import extraction_repo, invoice_repo
from app.adapters.storage.blob_store import get_blob_store
from app.db.models import Invoice, Vendor
from app.services.extraction_service import ExtractResult, extract_from_pdf
from app.services.vendor_memory_service import update_stats_from_extraction

def retry_extraction(
    session: Session, *, invoice_id, force_tier: str | None = None
) -> ExtractResult:
    """Re-run extraction for an existing Invoice, skipping file_hash dedup.

    Always creates a new Extraction row (the prior row stays on the
    Invoice as audit trail). When `force_tier` is set, the Cascade
    module routes through it with full agreement-scoring discipline
    per ADR-0003 — the clerk-forced tier becomes the cascade's starting
    point, not a bypass.
    """
    inv = invoice_repo.get_invoice(session, invoice_id)
    if inv is None:
        raise LookupError(f"invoice {invoice_id} not found")
    store = get_blob_store()
    with store.local_path(inv.storage_key) as pdf_path:
        return extract_from_pdf(
            session,
            pdf_path=pdf_path,
            storage_key=inv.storage_key,
            force_tier=force_tier,
            skip_dedup=True,
        )

def confirm_invoice(session: Session, *, invoice_id) -> Invoice:
    """Mark Invoice confirmed; update Vendor stats from its current Extraction.

    Per ADR-0003, stats are updated ONLY on confirm so unconfirmed /
    wrong values never pollute Vendor History that drives history_score
    and anomaly detection downstream.
    """
    invoice = invoice_repo.get_invoice(session, invoice_id)
    if invoice is None:
        raise LookupError(f"invoice {invoice_id} not found")
    invoice = invoice_repo.update_review_status(
        session, invoice_id=invoice_id, review_status="confirmed"
    )
    current = extraction_repo.get_current_extraction(session, invoice_id=invoice_id)
    if current is not None and invoice.vendor_id is not None:
        vendor = session.get(Vendor, invoice.vendor_id)
        if vendor is not None:
            update_stats_from_extraction(session, vendor=vendor, extraction=current)
    session.commit()
    return invoice

def dismiss_duplicate(session: Session, *, invoice_id, against_id) -> Invoice:
    """Persist that this Invoice was reviewed and is NOT a duplicate of `against_id`.

    The pair is added to `invoices.duplicate_dismissals` so the duplicate
    detector skips this combination on subsequent re-extractions.
    """
    invoice_repo.record_duplicate_dismissal(
        session, invoice_id=invoice_id, dismissed_against_id=against_id
    )
    session.commit()
    invoice = invoice_repo.get_invoice(session, invoice_id)
    if invoice is None:
        raise LookupError(f"invoice {invoice_id} not found")
    return invoice

def mark_unprocessable(session: Session, *, invoice_id) -> Invoice:
    """Set `review_status=unprocessable`. Failure-mode UX per ADR-0006."""
    inv = invoice_repo.update_review_status(
        session, invoice_id=invoice_id, review_status="unprocessable"
    )
    session.commit()
    return inv
