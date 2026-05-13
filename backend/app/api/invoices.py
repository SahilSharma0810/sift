"""POST /api/invoices  — upload + extract
GET  /api/invoices       — list newest-first
GET  /api/invoices/{id} — single invoice + current extraction
GET  /api/invoices/{id}/file — serves the raw PDF (used by PdfViewer)

Thin route handlers per ADR-0005 — parse request, call one service method,
serialize response. No direct imports from app.adapters or app.db.
"""

from __future__ import annotations

import hashlib
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_session
from app.domain.models import InvoiceOut
from app.services.extraction_service import (
    extract_and_serialize,
    get_invoice_dto,
    get_invoice_file_path,
    list_invoice_dtos,
)

router = APIRouter()


@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def upload_invoice(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> InvoiceOut:
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="only application/pdf is accepted",
        )

    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    raw = file.file.read()
    file_hash = hashlib.sha256(raw).hexdigest()
    target = settings.upload_dir / f"{file_hash}.pdf"
    if not target.exists():
        target.write_bytes(raw)

    return extract_and_serialize(session, pdf_path=target)


@router.get("", response_model=list[InvoiceOut])
def list_invoices_endpoint(session: Session = Depends(get_session)) -> list[InvoiceOut]:
    return list_invoice_dtos(session, limit=200)


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice_endpoint(invoice_id: UUID, session: Session = Depends(get_session)) -> InvoiceOut:
    dto = get_invoice_dto(session, invoice_id)
    if dto is None:
        raise HTTPException(status_code=404, detail="not found")
    return dto


@router.get("/{invoice_id}/file")
def serve_invoice_pdf(invoice_id: UUID, session: Session = Depends(get_session)) -> FileResponse:
    path = get_invoice_file_path(session, invoice_id)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, media_type="application/pdf")
