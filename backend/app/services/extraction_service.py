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

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.adapters.llm_client import (
    EXTRACT_HEADER,
    EXTRACT_HEADER_VISION,
    EXTRACT_LINE_ITEMS,
    EXTRACT_TAX_BREAKDOWN,
    ExtractionResult,
    LLMClient,
    make_llm_client,
)
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
from app.domain import confidence
from app.domain.anomalies import AcknowledgedOutlier, detect_anomalies
from app.domain.date_parser import parse_date_or_range
from app.domain.duplicates import classify_duplicate, hamming_distance
from app.domain.models import (
    AnomalyReason,
    DuplicateOfReason,
    ExtractionFailedReason,
    TriageReason,
    VendorMemoryStats,
)
from app.domain.triage import derive_triage
from app.domain.validators import (
    REQUIRED_FIELDS,
    line_items_sum_check,
    tax_breakdown_sum_check,
)
from app.services import cascade

log = structlog.get_logger(__name__)

@dataclass(frozen=True, slots=True)
class ExtractResult:
    invoice: Invoice
    extraction: Extraction


def _digital_extraction_empty(result: ExtractionResult) -> bool:
    """Digital-path Haiku came back with nothing usable — fall through to vision.

    Triggers when the LLM either self-reports `extraction_failed` or returns
    all required fields null/blank. Distinguishes "PDF had extractable text
    but the text was so degraded that text-only extraction couldn't recover
    anything" from "model genuinely thinks this isn't an invoice" — the
    fall-through gives the latter a second chance via the rendered image.
    """
    if result.extraction_failed:
        return True
    flat = {k: _normalize_value(v) for k, v in result.fields.items()}
    return all(flat.get(f) in (None, "") for f in REQUIRED_FIELDS)

def _normalize_value(field_value: Any) -> Any:
    """Vision-path values come as {"value": ..., "bbox": ...}; text-path values are bare."""
    if isinstance(field_value, dict) and "value" in field_value:
        return field_value["value"]
    return field_value

def _flat_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Strip out the wrapper dicts to get a flat field-name → value mapping."""
    return {k: _normalize_value(v) for k, v in raw.items()}

def _dump_reasons(reasons: list[TriageReason]) -> list[dict[str, Any]]:
    """Serialize Pydantic reason models to JSONB-compatible dicts."""
    return [r.model_dump(mode="json") for r in reasons]

def _get_or_create_invoice(
    session: Session,
    *,
    file_hash: str,
    storage_key: str,
    vendor_id,
    perceptual_hash: str | None,
) -> Invoice:
    existing = invoice_repo.find_by_file_hash(session, file_hash)
    if existing is not None:
        return existing
    return invoice_repo.create_invoice(
        session,
        storage_key=storage_key,
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
        result = llm.call(EXTRACT_LINE_ITEMS, model=final_model, text=invoice_text)
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
        result = llm.call(EXTRACT_TAX_BREAKDOWN, model=final_model, text=invoice_text)
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

    `invoice_date` also gets `iso_from` / `iso_to` populated via the
    Python date parser — the canonical form the search SQL filters on.
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

    date_field = out.get("invoice_date")
    if date_field is not None:
        iso_from, iso_to = parse_date_or_range(date_field.get("value"))
        date_field["iso_from"] = iso_from
        date_field["iso_to"] = iso_to

    return out

def _tier_for_model(model: str, settings) -> str:
    """Map a model name to the logical cascade tier label.

    The cascade module needs the LOGICAL tier (haiku / sonnet / opus)
    to decide what to escalate to. Mapping happens here at the service
    boundary so the cascade module stays free of the model-name coupling.
    Unrecognised models fall back to "haiku" so an out-of-band tier
    string never causes the cascade to silently skip escalation.
    """
    if model == settings.model_tier_1:
        return "haiku"
    if model == settings.model_tier_2:
        return "sonnet"
    if model == settings.model_tier_3:
        return "opus"
    return "haiku"

def _detect_duplicate(
    session: Session,
    *,
    file_hash: str,
    perceptual_hash: str,
    dismissals_against: list[str],
    exclude_invoice_id: Any = None,
) -> DuplicateOfReason | None:
    """Run the two-signal duplicate check, honoring prior `not-a-duplicate` dismissals."""
    candidates = invoice_repo.find_phash_candidates(session)
    best_id = None
    best_dist: int | None = None
    content_match_id = None
    content_match_phash_dist: int | None = None
    for cand in candidates:

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
            return DuplicateOfReason(
                invoice_id=content_match_id,
                similarity=sim,
                match_method=method,
            )

    if best_id is not None:
        if str(best_id) in dismissals_against:
            return None
        match = classify_duplicate(content_match=False, phash_distance=best_dist)
        if match:
            method, sim = match
            return DuplicateOfReason(
                invoice_id=best_id,
                similarity=sim,
                match_method=method,
            )

    return None

def extract_from_pdf(
    session: Session,
    *,
    pdf_path: Path,
    storage_key: str,
    force_tier: str | None = None,
    skip_dedup: bool = False,
) -> ExtractResult:
    """Day-2 extraction pipeline. See module docstring for stages.

    `pdf_path` is the local on-disk file used for reading + extraction.
    `storage_key` is the blob-store key used to record where the file
    lives across backends (local or R2). The caller pre-computes the
    sha256 + `.pdf` so we don't double-hash.
    """
    settings = get_settings()
    file_hash = storage_key.removesuffix(".pdf")

    if not skip_dedup:
        existing = invoice_repo.find_by_file_hash(session, file_hash)
        if existing is not None:
            current = extraction_repo.get_current_extraction(session, invoice_id=existing.id)
            if current is not None:
                log.info("extraction.dedup_hit", invoice_id=str(existing.id))
                return ExtractResult(invoice=existing, extraction=current)

    use_vision = not has_text(pdf_path)
    llm: LLMClient = make_llm_client(settings)

    invoice_text: str | None = None
    page_pngs: list[bytes] | None = None
    digital: DigitalRead | None = None

    if use_vision:
        page_pngs = render_page_pngs(pdf_path, scale=1.2)
        initial_model = force_tier or settings.model_tier_2
        initial_result = llm.call(EXTRACT_HEADER_VISION, model=initial_model, page_pngs=page_pngs)
    else:
        digital = read_digital(pdf_path)
        invoice_text = digital.full_text
        initial_model = force_tier or settings.model_tier_1
        initial_result = llm.call(EXTRACT_HEADER, model=initial_model, text=invoice_text)

        if force_tier is None and _digital_extraction_empty(initial_result):
            log.info(
                "extraction.digital_to_vision_fallback",
                reason="extraction_failed" if initial_result.extraction_failed else "all_required_null",
                digital_model=initial_result.model,
            )
            page_pngs = render_page_pngs(pdf_path, scale=1.2)
            use_vision = True
            initial_model = settings.model_tier_2
            initial_result = llm.call(EXTRACT_HEADER_VISION, model=initial_model, page_pngs=page_pngs)

    initial_tier = _tier_for_model(initial_model, settings)

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
            storage_key=storage_key,
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
            predicted_triage_reasons=_dump_reasons([
                ExtractionFailedReason(
                    stage="llm_call",
                    detail=initial_result.extraction_failure_reason
                    or "LLM reported extraction_failed",
                )
            ]),
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

    fields_flat = _flat_fields(initial_result.fields)
    vendor_name = fields_flat.get("vendor_name") or "Unknown"
    vendor = vendor_repo.upsert_by_normalized_name(session, name=str(vendor_name))
    raw_stats = (vendor.memory or {}).get("stats") or None
    vendor_stats = VendorMemoryStats(**raw_stats) if raw_stats else None
    pre_report = confidence.compute_confidence(
        extracted_fields=fields_flat,
        vendor_stats=vendor_stats,
    )
    is_unseen = vendor_stats is None or vendor_stats.total_seen == 0

    cascade_result = cascade.run_cascade(
        llm=llm,
        initial=initial_result,
        initial_tier=initial_tier,
        invoice_text=invoice_text,
        page_pngs=page_pngs,
        settings=settings,
        composite_confidence=pre_report.composite,
        math_passed=pre_report.math_passed,
        is_unseen_vendor=is_unseen,
        force_escalate=bool(force_tier),
    )
    final_fields = cascade_result.final_fields
    raw_vision_fields = cascade_result.raw_initial_fields
    cascade_trace_tiers = cascade_result.trace_tiers_dicts
    per_field_source = cascade_result.per_field_source

    report = confidence.compute_confidence(
        extracted_fields=final_fields,
        vendor_stats=vendor_stats,
        agreement_overrides=cascade_result.agreement_overrides,
    )
    composite = report.composite
    math_ok = report.math_passed

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

    try:
        phash = compute_perceptual_hash(pdf_path)
    except Exception:
        phash = None

    invoice = _get_or_create_invoice(
        session,
        file_hash=file_hash,
        storage_key=storage_key,
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

    anomalies: list[AnomalyReason] = []
    if duplicate_of is None and vendor_stats is not None:
        acked_raw = (vendor.memory or {}).get("acknowledged_outliers") or {}
        acked: dict[str, list[AcknowledgedOutlier]] = {
            field: [AcknowledgedOutlier(value=float(o.get("value", 0.0) or 0.0)) for o in lst]
            for field, lst in acked_raw.items()
        }
        anomalies = detect_anomalies(
            fields=final_fields,
            stats=vendor_stats,
            acknowledged_outliers=acked,
        )

    state, reasons = derive_triage(
        extracted_fields=final_fields,
        confidence=composite,
        math_passed=math_ok,
        is_unseen_vendor=is_unseen,
        duplicate_of=duplicate_of,
        anomalies=anomalies,
    )

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
        predicted_triage_reasons=_dump_reasons(reasons),
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

"""Pipeline ends here. Clerk-initiated Triage State transitions
(`confirm_invoice`, `dismiss_duplicate`, `mark_unprocessable`,
`retry_extraction`) live in `services/clerk_actions.py`. DTO-returning
queries used by the API layer live in `services/invoice_queries.py`."""
