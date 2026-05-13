"""Extraction service — orchestrates the digital happy path.

Pipeline: hash + dedupe → pdf-read → llm-extract → validate → score →
triage → save. The vision path lands Day 2; the cascade lands Day 2.

Per ADR-0005, this module imports from domain + adapters + db.session.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from app.adapters.llm_client import LLMClient
from app.adapters.pdf_reader import has_text, read_digital
from app.adapters.storage import extraction_repo, invoice_repo, vendor_repo
from app.config import get_settings
from app.db.models import Extraction, Invoice
from app.domain.models import ExtractionOut, InvoiceOut
from app.domain.scoring import compute_composite_confidence
from app.domain.triage import derive_triage
from app.domain.validators import compute_structural_scores, math_reconciles

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ExtractResult:
    invoice: Invoice
    extraction: Extraction


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _build_extracted_fields(
    raw: dict, structural: dict[str, float], confidence: dict[str, float], model: str
) -> dict:
    """Build the per-field ExtractedField shape from raw LLM output.

    Bbox is left None on the digital happy path for now; Day-2 bbox-follow
    wires the fuzzy-match from word boxes.
    """
    source = f"pymupdf+{model}"
    return {
        field: {
            "value": raw.get(field),
            "bbox": None,
            "page": 0,
            "confidence": confidence.get(field, 0.0),
            "source": source,
        }
        for field in (
            "vendor_name",
            "invoice_number",
            "invoice_date",
            "subtotal",
            "tax",
            "total",
            "currency",
        )
    }


def _get_or_create_invoice(
    session: Session,
    file_hash: str,
    file_path: str,
    vendor_id: object,
    perceptual_hash: str | None = None,
) -> Invoice:
    """Return existing invoice for file_hash or create a new one.

    Prevents duplicate invoice rows when a previous run crashed between
    create_invoice and create_extraction (partial-failure resumption).
    """
    existing = invoice_repo.find_by_file_hash(session, file_hash)
    if existing is not None:
        return existing
    return invoice_repo.create_invoice(
        session,
        file_path=file_path,
        file_hash=file_hash,
        vendor_id=vendor_id,
        perceptual_hash=perceptual_hash,
    )


def extract_from_pdf(session: Session, *, pdf_path: Path) -> ExtractResult:
    """Run the full Day-1 happy-path pipeline on a single digital PDF."""
    settings = get_settings()

    # 1. Hash + dedupe
    file_hash = _hash_file(pdf_path)
    existing = invoice_repo.find_by_file_hash(session, file_hash)
    if existing is not None:
        current = extraction_repo.get_current_extraction(session, invoice_id=existing.id)
        if current is not None:
            log.info("extraction.dedup_hit", invoice_id=str(existing.id))
            return ExtractResult(invoice=existing, extraction=current)

    # 2. PDF path branch — Day 1 digital path only.
    if not has_text(pdf_path):
        raise NotImplementedError("Vision path lands Day 2 — this PDF has no embedded text")
    pdf = read_digital(pdf_path)

    # 3. LLM extract.
    llm = LLMClient(api_key=settings.anthropic_api_key)
    llm_result = llm.extract_header(invoice_text=pdf.full_text, model=settings.model_tier_1)

    # 3a. Short-circuit: LLM reported it could not extract an invoice.
    if llm_result.extraction_failed:
        reasons = [
            {
                "type": "extraction_failed",
                "stage": "llm_call",
                "detail": llm_result.extraction_failure_reason or "LLM reported extraction failed",
            }
        ]
        vendor_name = llm_result.fields.get("vendor_name") or "Unknown"
        vendor = vendor_repo.upsert_by_normalized_name(session, name=vendor_name)
        invoice = _get_or_create_invoice(session, file_hash, str(pdf_path), vendor.id)
        extraction = extraction_repo.create_extraction(
            session,
            invoice_id=invoice.id,
            model=llm_result.model,
            extracted_fields={},
            confidence_per_field={},
            predicted_triage_state="needs_review",
            predicted_triage_reasons=reasons,
            cascade_trace={
                "tiers": [
                    {
                        "model": llm_result.model,
                        "prompt_hash": llm_result.prompt_hash,
                        "schema_hash": llm_result.schema_hash,
                        "usage": llm_result.usage,
                        "llm_self_confidence": llm_result.self_reported_confidence,
                        "extraction_failed": True,
                    }
                ]
            },
        )
        session.commit()
        log.warning(
            "extraction.llm_reported_failure",
            invoice_id=str(invoice.id),
            detail=reasons[0]["detail"],
        )
        return ExtractResult(invoice=invoice, extraction=extraction)

    # 4. Validate + score.
    structural = compute_structural_scores(llm_result.fields)
    math_ok = math_reconciles(
        subtotal=float(llm_result.fields.get("subtotal") or 0),
        tax=float(llm_result.fields.get("tax") or 0),
        total=float(llm_result.fields.get("total") or 0),
    )
    # Day 1 has no per-vendor history yet, so history scores are all default.
    confidence = compute_composite_confidence(structural, history={})

    # 5. Upsert vendor.
    vendor_name = llm_result.fields.get("vendor_name") or "Unknown"
    vendor = vendor_repo.upsert_by_normalized_name(session, name=vendor_name)
    is_unseen = vendor.memory == {}  # cold-start

    # 6. Triage state + reasons.
    state, reasons = derive_triage(
        extracted_fields=llm_result.fields,
        confidence=confidence,
        math_passed=math_ok,
        is_unseen_vendor=is_unseen,
        duplicate_of=None,  # Day 2 wires duplicate detection
    )

    # 7. Save invoice + extraction.
    invoice = _get_or_create_invoice(session, file_hash, str(pdf_path), vendor.id)
    extracted_fields_shape = _build_extracted_fields(
        llm_result.fields, structural, confidence, llm_result.model
    )
    extraction = extraction_repo.create_extraction(
        session,
        invoice_id=invoice.id,
        model=llm_result.model,
        extracted_fields=extracted_fields_shape,
        confidence_per_field=confidence,
        predicted_triage_state=state,
        predicted_triage_reasons=reasons,
        cascade_trace={
            "tiers": [
                {
                    "model": llm_result.model,
                    "prompt_hash": llm_result.prompt_hash,
                    "schema_hash": llm_result.schema_hash,
                    "usage": llm_result.usage,
                    "llm_self_confidence": llm_result.self_reported_confidence,
                }
            ]
        },
    )
    session.commit()

    log.info(
        "extraction.complete",
        invoice_id=str(invoice.id),
        triage_state=state,
        n_reasons=len(reasons),
    )
    return ExtractResult(invoice=invoice, extraction=extraction)


# ---------- DTO helpers — used by the api layer ----------


def _orm_extraction_to_dto(extraction: Extraction) -> ExtractionOut:
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
            "is_current": extraction.is_current,
            "created_at": extraction.created_at,
        }
    )


def _orm_invoice_to_dto(invoice: Invoice, session: Session) -> InvoiceOut:
    """Convert an ORM Invoice row (+ its current extraction) to an InvoiceOut DTO."""
    current = extraction_repo.get_current_extraction(session, invoice_id=invoice.id)
    current_out: ExtractionOut | None = (
        _orm_extraction_to_dto(current) if current is not None else None
    )
    return InvoiceOut(
        id=invoice.id,
        file_path=invoice.file_path,
        file_hash=invoice.file_hash,
        perceptual_hash=invoice.perceptual_hash,
        vendor_id=invoice.vendor_id,
        uploaded_at=invoice.uploaded_at,
        review_status=invoice.review_status,  # type: ignore[arg-type]
        current_extraction=current_out,
    )


def extract_and_serialize(session: Session, *, pdf_path: Path) -> InvoiceOut:
    """Run the full extraction pipeline and return a serialized DTO."""
    result = extract_from_pdf(session, pdf_path=pdf_path)
    return _orm_invoice_to_dto(result.invoice, session)


def list_invoice_dtos(session: Session, *, limit: int = 200) -> list[InvoiceOut]:
    """Return newest-first list of InvoiceOut DTOs."""
    invoices = invoice_repo.list_invoices(session, limit=limit)
    return [_orm_invoice_to_dto(inv, session) for inv in invoices]


def get_invoice_dto(session: Session, invoice_id: UUID) -> InvoiceOut | None:
    """Return an InvoiceOut DTO for the given invoice_id, or None."""
    inv = invoice_repo.get_invoice(session, invoice_id)
    if inv is None:
        return None
    return _orm_invoice_to_dto(inv, session)


def get_invoice_file_path(session: Session, invoice_id: UUID) -> Path | None:
    """Return the file path for an invoice, or None if not found."""
    inv = invoice_repo.get_invoice(session, invoice_id)
    if inv is None:
        return None
    return Path(inv.file_path)
