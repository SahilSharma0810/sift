"""POST /api/invoices  — upload + extract
GET  /api/invoices       — list newest-first
GET  /api/invoices/{id} — single invoice + current extraction
GET  /api/invoices/{id}/file — serves the raw PDF (used by PdfViewer)
POST /api/invoices/{id}/confirm
POST /api/invoices/{id}/dismiss-duplicate
POST /api/invoices/{id}/mark-unprocessable
POST /api/invoices/{id}/retry

Thin route handlers per ADR-0005 — parse request, call one service method,
serialize response. No direct imports from app.adapters or app.db.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.responses import Response

from app.api.deps import get_current_clerk
from app.db.session import get_session
from app.domain.auth import ClerkOut
from app.domain.models import InvoiceOut, VendorOut
from app.services.clerk_actions import (
    confirm_invoice,
    dismiss_duplicate,
    mark_unprocessable,
    retry_extraction,
)
from app.services.invoice_queries import (
    get_invoice_dto,
    get_vendor_for_invoice,
    list_invoice_dtos,
    serve_invoice_pdf,
    upload_pdf_and_extract,
)

router = APIRouter()

def _serialize(invoice, session: Session) -> InvoiceOut:
    """Convert an ORM Invoice to InvoiceOut DTO via the service layer."""
    dto = get_invoice_dto(session, invoice.id)
    if dto is None:
        raise HTTPException(status_code=404, detail="not found")
    return dto

@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def upload_invoice(
    file: UploadFile = File(...),
    _clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> InvoiceOut:
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="only application/pdf is accepted",
        )
    return upload_pdf_and_extract(session, source=file.file)

@router.get("", response_model=list[InvoiceOut])
def list_invoices_endpoint(
    _clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> list[InvoiceOut]:
    return list_invoice_dtos(session, limit=200)

@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice_endpoint(
    invoice_id: UUID,
    _clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> InvoiceOut:
    dto = get_invoice_dto(session, invoice_id)
    if dto is None:
        raise HTTPException(status_code=404, detail="not found")
    return dto

@router.get("/{invoice_id}/file")
def serve_invoice_pdf_endpoint(
    invoice_id: UUID,
    _clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> Response:
    try:
        return serve_invoice_pdf(session, invoice_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

@router.get("/{invoice_id}/vendor", response_model=VendorOut | None)
def get_invoice_vendor(
    invoice_id: UUID,
    _clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> VendorOut | None:
    return get_vendor_for_invoice(session, invoice_id=invoice_id)

class _DismissBody(BaseModel):
    against_id: UUID

@router.post("/{invoice_id}/confirm", response_model=InvoiceOut)
def confirm_endpoint(
    invoice_id: UUID,
    _clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> InvoiceOut:
    inv = confirm_invoice(session, invoice_id=invoice_id)
    return _serialize(inv, session)

@router.post("/{invoice_id}/dismiss-duplicate", response_model=InvoiceOut)
def dismiss_endpoint(
    invoice_id: UUID,
    body: _DismissBody,
    _clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> InvoiceOut:
    inv = dismiss_duplicate(session, invoice_id=invoice_id, against_id=body.against_id)
    return _serialize(inv, session)

@router.post("/{invoice_id}/mark-unprocessable", response_model=InvoiceOut)
def unprocessable_endpoint(
    invoice_id: UUID,
    _clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> InvoiceOut:
    inv = mark_unprocessable(session, invoice_id=invoice_id)
    return _serialize(inv, session)

@router.post("/{invoice_id}/retry", response_model=InvoiceOut)
def retry_endpoint(
    invoice_id: UUID,
    force_tier: str | None = None,
    _clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> InvoiceOut:
    try:
        result = retry_extraction(
            session, invoice_id=invoice_id, force_tier=force_tier
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"invoice {invoice_id} PDF is no longer available",
        ) from exc
    return _serialize(result.invoice, session)
