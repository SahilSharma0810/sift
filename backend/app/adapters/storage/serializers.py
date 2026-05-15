"""ORM -> DTO serialization at the persistence seam.

The shape difference between SQLAlchemy ORM rows (the schema sketch in
db/models.py) and the Pydantic DTOs that services and the API hand back
(domain/models.py: InvoiceOut, ExtractionOut, VendorOut) lives in this
single module - one place to look when a column rename ripples through
the API contract.

Layered correctly: adapters import from domain (DTOs are the inward
dependency) and db (ORM rows are sibling persistence shape). No service
or api import here.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.adapters.storage import extraction_repo
from app.db.models import Extraction, Invoice, Vendor
from app.domain.models import (
    ExtractionOut,
    InvoiceOut,
    VendorMemory,
    VendorMemoryStats,
    VendorOut,
)

def extraction_to_dto(extraction: Extraction) -> ExtractionOut:
    """Convert an ORM Extraction row to an ExtractionOut DTO."""
    return ExtractionOut.model_validate(
        {
            "id": extraction.id,
            "invoice_id": extraction.invoice_id,
            "model": extraction.model,
            "cascade_trace": extraction.cascade_trace,
            "extracted_fields": extraction.extracted_fields,
            "confidence_per_field": extraction.confidence_per_field,
            "predicted_triage_state": extraction.predicted_triage_state,
            "predicted_triage_reasons": extraction.predicted_triage_reasons,
            "line_items": extraction.line_items or [],
            "tax_breakdown": extraction.tax_breakdown or [],
            "is_current": extraction.is_current,
            "created_at": extraction.created_at,
        }
    )

def invoice_to_dto(invoice: Invoice, session: Session) -> InvoiceOut:
    """Convert an ORM Invoice row (+ its current extraction) to an InvoiceOut DTO.

    The `current_extraction` field is resolved via extraction_repo so the
    Invoice DTO is always consistent with what the inbox / review screen
    would render right now - never with a stale extraction snapshot.
    """
    current = extraction_repo.get_current_extraction(session, invoice_id=invoice.id)
    current_out: ExtractionOut | None = (
        extraction_to_dto(current) if current is not None else None
    )
    return InvoiceOut(
        id=invoice.id,
        file_path=invoice.file_path,
        file_hash=invoice.file_hash,
        perceptual_hash=invoice.perceptual_hash,
        vendor_id=invoice.vendor_id,
        uploaded_at=invoice.uploaded_at,
        review_status=invoice.review_status,  # type: ignore[arg-type]
        duplicate_dismissals=invoice.duplicate_dismissals or [],
        current_extraction=current_out,
    )

def vendor_to_dto(vendor: Vendor) -> VendorOut:
    """Convert an ORM Vendor row to a VendorOut DTO (with VendorMemory)."""
    memory_dict = vendor.memory or {}
    stats_raw = memory_dict.get("stats") or {}
    memory = VendorMemory(
        rules=memory_dict.get("rules", []) or [],
        stats=VendorMemoryStats(
            total_seen=int(stats_raw.get("total_seen", 0) or 0),
            avg_total=float(stats_raw.get("avg_total", 0.0) or 0.0),
            std_total=float(stats_raw.get("std_total", 0.0) or 0.0),
        ),
    )
    return VendorOut(
        id=vendor.id,
        name=vendor.name,
        tax_id=vendor.tax_id,
        normalized_name=vendor.normalized_name,
        first_seen_at=vendor.first_seen_at,
        memory=memory,
    )
