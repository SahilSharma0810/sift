"""DTO-returning queries used by the API layer.

Composes repository reads with the ORM->DTO serialization at
`adapters/storage/serializers.py`. Each function is a single fetch and
a single conversion - no business logic. The API layer imports from
here for read endpoints and the upload+extract endpoint.

Per ADR-0005, these are service-layer use cases: parse request, fetch,
serialize, return.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.adapters.storage import invoice_repo
from app.adapters.storage.serializers import invoice_to_dto, vendor_to_dto
from app.db.models import Vendor
from app.domain.models import InvoiceOut, VendorOut
from app.services.extraction_service import extract_from_pdf

def extract_and_serialize(session: Session, *, pdf_path: Path) -> InvoiceOut:
    """Run the full extraction pipeline and return a serialized DTO."""
    result = extract_from_pdf(session, pdf_path=pdf_path)
    return invoice_to_dto(result.invoice, session)

def list_invoice_dtos(session: Session, *, limit: int = 200) -> list[InvoiceOut]:
    """Return newest-first list of InvoiceOut DTOs."""
    invoices = invoice_repo.list_invoices(session, limit=limit)
    return [invoice_to_dto(inv, session) for inv in invoices]

def get_invoice_dto(session: Session, invoice_id: UUID) -> InvoiceOut | None:
    """Return an InvoiceOut DTO for the given invoice_id, or None."""
    inv = invoice_repo.get_invoice(session, invoice_id)
    if inv is None:
        return None
    return invoice_to_dto(inv, session)

def get_invoice_storage_key(session: Session, invoice_id: UUID) -> str | None:
    """Return the blob-store key for an Invoice, or None if not found."""
    inv = invoice_repo.get_invoice(session, invoice_id)
    if inv is None:
        return None
    return inv.storage_key

def get_vendor_for_invoice(session: Session, *, invoice_id) -> VendorOut | None:
    """Return the Vendor (with memory) associated with an Invoice, or None."""
    inv = invoice_repo.get_invoice(session, invoice_id)
    if inv is None or inv.vendor_id is None:
        return None
    v = session.get(Vendor, inv.vendor_id)
    if v is None:
        return None
    return vendor_to_dto(v)
