"""Extraction service — Day-2 pipeline.

Pipeline:
1. Hash file → existing-invoice dedup short-circuit (current extraction present)
2. has_text() branch → digital path (Haiku, text) or vision path (Sonnet, images)
3. First-tier LLM extraction
4. If extraction_failed → write extraction_failed reason, commit, return
5. Validate + structural_score + composite confidence (with history if vendor known)
6. Cascade decision: if math fails OR min_confidence < 0.7 OR unseen vendor →
   run next-tier LLM on same input, compute agreement_score per field, replace
   disputed confidence, recompute math + composite. If after Sonnet the
   minimum agreement on a REQUIRED field is <= 0.3, escalate to Opus on
   the disputed fields.
7. Resolve bboxes (digital path: fuzzy-match against word stream; vision
   path: take from tool-use input)
8. Compute perceptual hash + persist on invoice
9. Duplicate detection: content_match (file_hash) + phash distance
10. Anomaly detection vs vendor stats (skipped if duplicate)
11. derive_triage → predicted_triage_state + predicted_triage_reasons
12. Save extraction + invoice (1:N atomic via repo)

Per ADR-0005: services orchestrate domain + adapters; never imports from api.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from app.adapters.llm_client import ExtractionResult, LLMClient, make_llm_client
from app.adapters.pdf_reader import (
    DigitalRead,
    compute_perceptual_hash,
    has_text,
    read_digital,
    render_page_pngs,
    resolve_bboxes,
)
from app.adapters.storage import extraction_repo, invoice_repo, vendor_repo
from app.config import get_settings
from app.db.models import Extraction, Invoice
from app.domain.anomalies import detect_anomalies
from app.domain.duplicates import classify_duplicate, hamming_distance
from app.domain.models import ExtractionOut, InvoiceOut, VendorMemory, VendorMemoryStats, VendorOut
from app.domain.scoring import (
    agreement_score,
    compute_composite_confidence,
    should_trigger_cascade,
)
from app.domain.triage import derive_triage
from app.domain.validators import (
    REQUIRED_FIELDS,
    compute_structural_scores,
    line_items_sum_check,
    math_reconciles,
    tax_breakdown_sum_check,
)
from app.services.vendor_memory_service import compute_history_scores

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ExtractResult:
    invoice: Invoice
    extraction: Extraction


def _hash_file(path: Path) -> str:
    """SHA-256 of file bytes — chunked 64KB to avoid memory spikes on large scans."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize_value(field_value: Any) -> Any:
    """Vision-path values come as {"value": ..., "bbox": ...}; text-path values are bare."""
    if isinstance(field_value, dict) and "value" in field_value:
        return field_value["value"]
    return field_value


def _flat_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Strip out the wrapper dicts to get a flat field-name → value mapping."""
    return {k: _normalize_value(v) for k, v in raw.items()}


def _get_or_create_invoice(
    session: Session,
    *,
    file_hash: str,
    file_path: Path,
    vendor_id,
    perceptual_hash: str | None,
) -> Invoice:
    existing = invoice_repo.find_by_file_hash(session, file_hash)
    if existing is not None:
        return existing
    return invoice_repo.create_invoice(
        session,
        file_path=str(file_path),
        file_hash=file_hash,
        vendor_id=vendor_id,
        perceptual_hash=perceptual_hash,
    )


def _extract_line_items_if_digital(
    *,
    llm: LLMClient,
    use_vision: bool,
    invoice_text: str | None,
    final_model: str,
    subtotal: Any,
) -> list[dict[str, Any]]:
    """Run line-item extraction on the digital path; vision returns empty.

    Logs (does not raise) on sum-check mismatch — line items are
    quality-gated for Day 3 per PLAN.md and the sum check is a warning
    rather than a triage signal.
    """
    if use_vision or invoice_text is None:
        return []
    try:
        result = llm.extract_line_items(invoice_text=invoice_text, model=final_model)
    except Exception as exc:
        log.warning("extraction.line_items.failed", error=str(exc), model=final_model)
        return []

    items = result.items
    try:
        sub_float = float(subtotal) if subtotal is not None else None
    except (TypeError, ValueError):
        sub_float = None

    matches, delta = line_items_sum_check(items, sub_float)
    if not matches:
        log.info(
            "extraction.line_items.sum_mismatch",
            delta=str(delta),
            n_items=len(items),
            subtotal=sub_float,
        )
    return items


def _extract_tax_breakdown_if_digital(
    *,
    llm: LLMClient,
    use_vision: bool,
    invoice_text: str | None,
    final_model: str,
    header_tax: Any,
) -> list[dict[str, Any]]:
    """Run tax-breakdown extraction on the digital path; vision returns empty.

    Same gating semantics as _extract_line_items_if_digital — Day 4 logs
    sum mismatches but never alters triage state. Vision path returns []
    for now; tax-breakdown vision is Day 5+ stretch.
    """
    if use_vision or invoice_text is None:
        return []
    try:
        result = llm.extract_tax_breakdown(invoice_text=invoice_text, model=final_model)
    except Exception as exc:
        log.warning("extraction.tax_breakdown.failed", error=str(exc), model=final_model)
        return []

    rows = result.rows
    try:
        tax_float = float(header_tax) if header_tax is not None else None
    except (TypeError, ValueError):
        tax_float = None

    matches, delta = tax_breakdown_sum_check(rows, tax_float)
    if not matches:
        log.info(
            "extraction.tax_breakdown.sum_mismatch",
            delta=str(delta),
            n_rows=len(rows),
            header_tax=tax_float,
        )
    return rows


def _build_extracted_fields_shape(
    *,
    fields: dict[str, Any],
    bboxes: dict[str, tuple[float, float, float, float]],
    raw_vision_fields: dict[str, Any] | None,
    confidence: dict[str, float],
    per_field_source: dict[str, str],
) -> dict[str, Any]:
    """Construct the on-disk ExtractedField shape per field.

    Vision path: bbox comes from the LLM tool-use input.
    Digital path: bbox comes from fuzzy-match against word stream.
    Source: "pymupdf+<tier-or-model>" for digital, "claude-vision" for vision.
    """
    out: dict[str, Any] = {}
    for field in (*REQUIRED_FIELDS, "subtotal", "tax"):
        value = fields.get(field)
        bbox = None
        if raw_vision_fields and isinstance(raw_vision_fields.get(field), dict):
            bbox = raw_vision_fields[field].get("bbox")
        if bbox is None:
            bbox = bboxes.get(field)
        tier = per_field_source.get(field, "haiku")
        source = "claude-vision" if raw_vision_fields else f"pymupdf+{tier}"
        out[field] = {
            "value": value,
            "bbox": list(bbox) if bbox else None,
            "page": 0,
            "confidence": confidence.get(field, 0.0),
            "source": source,
        }
    return out


def _run_cascade(
    *,
    llm: LLMClient,
    initial: ExtractionResult,
    initial_tier: str,
    invoice_text: str | None,
    page_pngs: list[bytes] | None,
    settings,
) -> tuple[dict[str, Any], dict[str, float], list[dict[str, Any]], dict[str, str]]:
    """Run cascade tiers + agreement-score override.

    Returns (final_fields, agreement_overrides, trace_tiers, per_field_source).
    """
    fields = _flat_fields(initial.fields)
    overrides: dict[str, float] = {}
    per_field_source: dict[str, str] = {k: initial_tier for k in fields}
    trace_tiers: list[dict[str, Any]] = [
        {
            "model": initial.model,
            "prompt_hash": initial.prompt_hash,
            "schema_hash": initial.schema_hash,
            "usage": initial.usage,
            "llm_self_confidence": initial.self_reported_confidence,
        }
    ]

    # Tier 2: Sonnet
    sonnet_result: ExtractionResult | None = None
    if invoice_text is not None:
        sonnet_result = llm.extract_header(invoice_text=invoice_text, model=settings.model_tier_2)
    elif page_pngs is not None and initial_tier != "sonnet":
        sonnet_result = llm.extract_header_vision(page_pngs=page_pngs, model=settings.model_tier_2)

    if sonnet_result is None:
        return fields, overrides, trace_tiers, per_field_source

    sonnet_flat = _flat_fields(sonnet_result.fields)
    trace_tiers.append(
        {
            "model": sonnet_result.model,
            "prompt_hash": sonnet_result.prompt_hash,
            "schema_hash": sonnet_result.schema_hash,
            "usage": sonnet_result.usage,
            "llm_self_confidence": sonnet_result.self_reported_confidence,
        }
    )

    disputed: list[str] = []
    for field in (*REQUIRED_FIELDS, "subtotal", "tax"):
        h_val = fields.get(field)
        s_val = sonnet_flat.get(field)
        score = agreement_score(h_val, s_val, field)
        overrides[field] = score
        if score <= 0.3:
            disputed.append(field)
            # Prefer Sonnet's value on dispute.
            fields[field] = s_val
            per_field_source[field] = "sonnet"

    # Tier 3: Opus — only if disputed REQUIRED fields remain at low agreement.
    required_disputes = [f for f in disputed if f in REQUIRED_FIELDS]
    if not required_disputes:
        return fields, overrides, trace_tiers, per_field_source

    opus_result: ExtractionResult | None = None
    if invoice_text is not None:
        opus_result = llm.extract_header(invoice_text=invoice_text, model=settings.model_tier_3)
    elif page_pngs is not None:
        opus_result = llm.extract_header_vision(page_pngs=page_pngs, model=settings.model_tier_3)

    if opus_result is None:
        return fields, overrides, trace_tiers, per_field_source

    opus_flat = _flat_fields(opus_result.fields)
    trace_tiers.append(
        {
            "model": opus_result.model,
            "prompt_hash": opus_result.prompt_hash,
            "schema_hash": opus_result.schema_hash,
            "usage": opus_result.usage,
            "llm_self_confidence": opus_result.self_reported_confidence,
        }
    )
    for field in required_disputes:
        o_val = opus_flat.get(field)
        # If Opus agrees with either prior tier, lift the override score.
        if agreement_score(o_val, fields.get(field), field) == 1.0:
            overrides[field] = 1.0
        fields[field] = o_val
        per_field_source[field] = "opus"

    return fields, overrides, trace_tiers, per_field_source


def _detect_duplicate(
    session: Session,
    *,
    file_hash: str,
    perceptual_hash: str,
    dismissals_against: list[str],
    exclude_invoice_id: Any = None,
) -> dict[str, Any] | None:
    """Run the two-signal duplicate check, honoring prior `not-a-duplicate` dismissals."""
    candidates = invoice_repo.find_phash_candidates(session)
    best_id = None
    best_dist: int | None = None
    content_match_id = None
    content_match_phash_dist: int | None = None
    for cand in candidates:
        # Skip the invoice being processed — self-match is not a duplicate.
        if exclude_invoice_id is not None and cand.id == exclude_invoice_id:
            continue
        is_content_match = cand.file_hash == file_hash
        if is_content_match:
            content_match_id = cand.id
        if cand.perceptual_hash is None:
            continue
        try:
            dist = hamming_distance(perceptual_hash, cand.perceptual_hash)
        except Exception:
            continue
        if is_content_match:
            # Track the phash distance ONLY against the content-match candidate.
            # Sharing best_dist (computed against any candidate) would misclassify
            # "both" when the visually-closest candidate is a different invoice
            # than the file_hash match.
            content_match_phash_dist = dist
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_id = cand.id

    if content_match_id is not None:
        if str(content_match_id) in dismissals_against:
            return None
        match = classify_duplicate(content_match=True, phash_distance=content_match_phash_dist)
        if match:
            method, sim = match
            return {
                "invoice_id": str(content_match_id),
                "similarity": sim,
                "match_method": method,
            }

    if best_id is not None:
        if str(best_id) in dismissals_against:
            return None
        match = classify_duplicate(content_match=False, phash_distance=best_dist)
        if match:
            method, sim = match
            return {
                "invoice_id": str(best_id),
                "similarity": sim,
                "match_method": method,
            }

    return None


def extract_from_pdf(
    session: Session,
    *,
    pdf_path: Path,
    force_tier: str | None = None,
    skip_dedup: bool = False,
) -> ExtractResult:
    """Day-2 extraction pipeline. See module docstring for stages."""
    settings = get_settings()
    file_hash = _hash_file(pdf_path)

    if not skip_dedup:
        existing = invoice_repo.find_by_file_hash(session, file_hash)
        if existing is not None:
            current = extraction_repo.get_current_extraction(session, invoice_id=existing.id)
            if current is not None:
                log.info("extraction.dedup_hit", invoice_id=str(existing.id))
                return ExtractResult(invoice=existing, extraction=current)

    # Path branch
    use_vision = not has_text(pdf_path)
    llm: LLMClient = make_llm_client(settings)

    invoice_text: str | None = None
    page_pngs: list[bytes] | None = None
    initial_tier = "haiku"
    digital: DigitalRead | None = None

    if use_vision:
        page_pngs = render_page_pngs(pdf_path, scale=1.2)
        initial_tier = "sonnet"
        initial_result = llm.extract_header_vision(
            page_pngs=page_pngs, model=force_tier or settings.model_tier_2
        )
    else:
        digital = read_digital(pdf_path)
        invoice_text = digital.full_text
        initial_result = llm.extract_header(
            invoice_text=invoice_text, model=force_tier or settings.model_tier_1
        )

    # Extraction_failed short-circuit
    if initial_result.extraction_failed:
        log.warning(
            "extraction.llm_reported_failure",
            model=initial_result.model,
            detail=initial_result.extraction_failure_reason,
        )
        try:
            phash = compute_perceptual_hash(pdf_path)
        except Exception:
            phash = None
        vendor_name = _normalize_value(initial_result.fields.get("vendor_name")) or "Unknown"
        vendor = vendor_repo.upsert_by_normalized_name(session, name=str(vendor_name))
        invoice = _get_or_create_invoice(
            session,
            file_hash=file_hash,
            file_path=pdf_path,
            vendor_id=vendor.id,
            perceptual_hash=phash,
        )
        extraction = extraction_repo.create_extraction(
            session,
            invoice_id=invoice.id,
            model=initial_result.model,
            extracted_fields={},
            confidence_per_field={},
            predicted_triage_state="needs_review",
            predicted_triage_reasons=[
                {
                    "type": "extraction_failed",
                    "stage": "llm_call",
                    "detail": initial_result.extraction_failure_reason
                    or "LLM reported extraction_failed",
                }
            ],
            cascade_trace={
                "tiers": [
                    {
                        "model": initial_result.model,
                        "prompt_hash": initial_result.prompt_hash,
                        "schema_hash": initial_result.schema_hash,
                        "usage": initial_result.usage,
                        "extraction_failed": True,
                    }
                ]
            },
        )
        session.commit()
        return ExtractResult(invoice=invoice, extraction=extraction)

    # Validate + score on initial result (before cascade decision)
    fields_flat = _flat_fields(initial_result.fields)
    structural = compute_structural_scores(fields_flat)
    math_ok = math_reconciles(
        subtotal=float(fields_flat.get("subtotal") or 0),
        tax=float(fields_flat.get("tax") or 0),
        total=float(fields_flat.get("total") or 0),
    )
    vendor_name = fields_flat.get("vendor_name") or "Unknown"
    vendor = vendor_repo.upsert_by_normalized_name(session, name=str(vendor_name))
    history_scores = compute_history_scores(vendor=vendor, fields=fields_flat)
    composite = compute_composite_confidence(structural, history=history_scores)
    is_unseen = bool(vendor.memory == {} or not vendor.memory.get("stats", {}).get("total_seen", 0))

    # Cascade decision
    final_fields = fields_flat
    raw_vision_fields = initial_result.fields if use_vision else None
    cascade_trace_tiers: list[dict[str, Any]] = [
        {
            "model": initial_result.model,
            "prompt_hash": initial_result.prompt_hash,
            "schema_hash": initial_result.schema_hash,
            "usage": initial_result.usage,
            "llm_self_confidence": initial_result.self_reported_confidence,
        }
    ]
    per_field_source: dict[str, str] = {k: initial_tier for k in fields_flat}
    overrides: dict[str, float] = {}

    if not force_tier and should_trigger_cascade(
        composite, math_passed=math_ok, is_unseen_vendor=is_unseen
    ):
        final_fields, overrides, cascade_trace_tiers, per_field_source = _run_cascade(
            llm=llm,
            initial=initial_result,
            initial_tier=initial_tier,
            invoice_text=invoice_text,
            page_pngs=page_pngs,
            settings=settings,
        )
        # Re-validate after cascade replacement
        structural = compute_structural_scores(final_fields)
        math_ok = math_reconciles(
            subtotal=float(final_fields.get("subtotal") or 0),
            tax=float(final_fields.get("tax") or 0),
            total=float(final_fields.get("total") or 0),
        )
        composite = compute_composite_confidence(structural, history=history_scores)
        # Apply agreement overrides on disputed fields
        for field, override_score in overrides.items():
            composite[field] = min(composite.get(field, 1.0), override_score)

    # Bboxes
    bboxes_resolved: dict[str, tuple[float, float, float, float]] = {}
    if not use_vision and digital is not None:
        bboxes_resolved = resolve_bboxes(
            words=digital.words,
            page_count=digital.page_count,
            extracted=final_fields,
        )

    extracted_fields_shape = _build_extracted_fields_shape(
        fields=final_fields,
        bboxes=bboxes_resolved,
        raw_vision_fields=raw_vision_fields,
        confidence=composite,
        per_field_source=per_field_source,
    )

    # Perceptual hash + duplicate detection
    try:
        phash = compute_perceptual_hash(pdf_path)
    except Exception:
        phash = None

    invoice = _get_or_create_invoice(
        session,
        file_hash=file_hash,
        file_path=pdf_path,
        vendor_id=vendor.id,
        perceptual_hash=phash,
    )
    dismissals_against = [str(x) for x in (invoice.duplicate_dismissals or [])]
    duplicate_of = None
    if phash:
        duplicate_of = _detect_duplicate(
            session,
            file_hash=file_hash,
            perceptual_hash=phash,
            dismissals_against=dismissals_against,
            exclude_invoice_id=invoice.id,
        )

    # Anomaly detection (skipped if duplicate)
    anomalies: list[dict[str, Any]] = []
    if duplicate_of is None:
        stats = (vendor.memory or {}).get("stats", {}) or {}
        anomalies = detect_anomalies(fields=final_fields, stats=stats)

    state, reasons = derive_triage(
        extracted_fields=final_fields,
        confidence=composite,
        math_passed=math_ok,
        is_unseen_vendor=is_unseen,
        duplicate_of=duplicate_of,
        anomalies=anomalies,
    )

    # Line items + tax breakdown — Days 3 / 4. Both quality-gated: sum
    # mismatches are logged but do NOT alter triage. Vision path returns []
    # for both. Cascade-final model tier is used so the most-capable model
    # the cascade reached drives both extractions.
    final_model_tier = cascade_trace_tiers[-1]["model"]
    line_items_raw = _extract_line_items_if_digital(
        llm=llm,
        use_vision=use_vision,
        invoice_text=invoice_text,
        final_model=final_model_tier,
        subtotal=final_fields.get("subtotal"),
    )
    tax_breakdown_raw = _extract_tax_breakdown_if_digital(
        llm=llm,
        use_vision=use_vision,
        invoice_text=invoice_text,
        final_model=final_model_tier,
        header_tax=final_fields.get("tax"),
    )

    extraction = extraction_repo.create_extraction(
        session,
        invoice_id=invoice.id,
        model=initial_result.model,
        extracted_fields=extracted_fields_shape,
        confidence_per_field=composite,
        predicted_triage_state=state,
        predicted_triage_reasons=reasons,
        cascade_trace={"tiers": cascade_trace_tiers},
        line_items=line_items_raw,
        tax_breakdown=tax_breakdown_raw,
    )
    session.commit()
    log.info(
        "extraction.complete",
        invoice_id=str(invoice.id),
        triage_state=state,
        n_reasons=len(reasons),
        n_tiers=len(cascade_trace_tiers),
    )
    return ExtractResult(invoice=invoice, extraction=extraction)


def retry_extraction(
    session: Session, *, invoice_id, force_tier: str | None = None
) -> ExtractResult:
    """Re-run extraction for an existing invoice, skipping the file_hash dedup."""
    inv = invoice_repo.get_invoice(session, invoice_id)
    if inv is None:
        raise LookupError(f"invoice {invoice_id} not found")
    return extract_from_pdf(
        session, pdf_path=Path(inv.file_path), force_tier=force_tier, skip_dedup=True
    )


from app.db.models import Vendor as _VendorModel  # noqa: E402
from app.services.vendor_memory_service import update_stats_from_extraction  # noqa: E402


def confirm_invoice(session: Session, *, invoice_id) -> Invoice:
    """Mark invoice confirmed; update vendor stats from its current extraction.

    Stats are updated ONLY on confirm (not on every extraction) so that
    unconfirmed / wrong values never pollute the vendor history that drives
    history_score and anomaly detection.
    """
    invoice = invoice_repo.get_invoice(session, invoice_id)
    if invoice is None:
        raise LookupError(f"invoice {invoice_id} not found")
    invoice = invoice_repo.update_review_status(
        session, invoice_id=invoice_id, review_status="confirmed"
    )
    current = extraction_repo.get_current_extraction(session, invoice_id=invoice_id)
    if current is not None and invoice.vendor_id is not None:
        vendor = session.get(_VendorModel, invoice.vendor_id)
        if vendor is not None:
            update_stats_from_extraction(session, vendor=vendor, extraction=current)
    session.commit()
    return invoice


def dismiss_duplicate(session: Session, *, invoice_id, against_id) -> Invoice:
    """Persist that this invoice was reviewed and is NOT a duplicate of `against_id`.

    The pair is added to invoices.duplicate_dismissals so the duplicate
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
    """Set review_status=unprocessable. Used for failure-mode UX."""
    inv = invoice_repo.update_review_status(
        session, invoice_id=invoice_id, review_status="unprocessable"
    )
    session.commit()
    return inv


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
            "line_items": extraction.line_items or [],
            "tax_breakdown": extraction.tax_breakdown or [],
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
        duplicate_dismissals=invoice.duplicate_dismissals or [],
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


def get_vendor_for_invoice(session: Session, *, invoice_id) -> VendorOut | None:
    """Return the vendor (with memory) associated with an invoice, or None."""
    from app.db.models import Vendor as VendorModel

    inv = invoice_repo.get_invoice(session, invoice_id)
    if inv is None or inv.vendor_id is None:
        return None
    v = session.get(VendorModel, inv.vendor_id)
    if v is None:
        return None
    memory_dict = v.memory or {}
    memory = VendorMemory(
        rules=memory_dict.get("rules", []) or [],
        stats=VendorMemoryStats(
            total_seen=int(memory_dict.get("stats", {}).get("total_seen", 0) or 0),
            avg_total=float(memory_dict.get("stats", {}).get("avg_total", 0.0) or 0.0),
            std_total=float(memory_dict.get("stats", {}).get("std_total", 0.0) or 0.0),
        ),
    )
    return VendorOut(
        id=v.id,
        name=v.name,
        tax_id=v.tax_id,
        normalized_name=v.normalized_name,
        first_seen_at=v.first_seen_at,
        memory=memory,
    )
