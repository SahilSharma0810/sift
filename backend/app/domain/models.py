"""Domain models — pure Pydantic types, no IO.

Single source of truth for business types. Frontend TypeScript types are
generated from these (see scripts/generate_types.py). SQLAlchemy ORM in
app/db/models.py is a thin storage projection of these shapes.

All JSONB shapes locked here match PLAN.md "Schema sketch".
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------- Triage states + review statuses ----------
TriageState = Literal["confident", "needs_review", "likely_duplicate"]
ReviewStatus = Literal["pending", "confirmed", "dismissed_duplicate", "unprocessable"]
# Open-ended string so the service can emit `pymupdf+<full-model-id>` without
# requiring a Literal update on every model rename. The frontend SourceBadge
# component tokenizes by model keyword (haiku / sonnet / opus / memory /
# manual). Known prefixes for documentation:
#   "pymupdf+<model>"     digital text extraction
#   "claude-vision"       vision tool-use
#   "memory-applied"      auto-filled from vendor memory rule
#   "manual-correction"   clerk edited an extracted value
#   "manual-entry"        clerk filled an unextracted/failed field
ExtractionSource = str


# ---------- ExtractedField — locked shape from PLAN.md ----------
class ExtractedField(BaseModel):
    """A single extracted field with bbox + confidence + provenance.

    See PLAN.md `extracted_fields` shape. The bbox-highlight UX (beat 1)
    and provenance-hover UX (beat 3) both depend on this shape.
    """

    model_config = ConfigDict(extra="forbid")

    value: str | float | int | None
    bbox: tuple[float, float, float, float] | None = None  # x0, y0, x1, y1
    page: int = 0
    confidence: float = Field(ge=0.0, le=1.0)
    source: ExtractionSource


# ---------- TaxBreakdownLine — Day 4 ----------
class TaxBreakdownLine(BaseModel):
    """One row of the per-jurisdiction tax breakdown table.

    Day-4 quality-gated extraction surface, mirrors the line-items gate.
    Math check (sum of `amount` vs header `tax`) is logged but does NOT
    alter triage state — see PLAN.md Day-4 gate.
    """

    model_config = ConfigDict(extra="forbid")

    jurisdiction: str
    rate: float | None = None  # nullable: some invoices show only the amount
    amount: float
    bbox: tuple[float, float, float, float] | None = None
    page: int = 0
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


# ---------- LineItem — Day 3 ----------
class LineItem(BaseModel):
    """A single invoice line item (one row of the line-items table).

    Day-3 quality-gated extraction surface. `description` is the only field
    we trust enough to require; quantity/unit_price are commonly missing on
    service invoices where the line is a flat-fee item. Math checks (sum
    of `line_total` vs subtotal) are logged but do NOT alter triage state
    in Day 3 — see PLAN.md Day-3 gate.
    """

    model_config = ConfigDict(extra="forbid")

    description: str
    quantity: float | None = None
    unit_price: float | None = None
    line_total: float
    bbox: tuple[float, float, float, float] | None = None
    page: int = 0
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


# ---------- Triage reasons — discriminated union ----------
class _BaseReason(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MathFailsReason(_BaseReason):
    type: Literal["math_fails"] = "math_fails"
    subtotal: float
    tax: float
    total: float
    delta: float


class AnomalyReason(_BaseReason):
    type: Literal["anomaly"] = "anomaly"
    field: str
    vendor_mean: float
    vendor_std: float
    z_score: float


class DuplicateOfReason(_BaseReason):
    type: Literal["duplicate_of"] = "duplicate_of"
    invoice_id: UUID
    similarity: float
    match_method: Literal["perceptual_hash", "content_fingerprint", "both"]


class LowConfidenceReason(_BaseReason):
    type: Literal["low_confidence"] = "low_confidence"
    field: str
    score: float
    reason: str


class MissingFieldReason(_BaseReason):
    type: Literal["missing_field"] = "missing_field"
    field: str


class UnseenVendorReason(_BaseReason):
    type: Literal["unseen_vendor"] = "unseen_vendor"
    vendor_name: str


class ExtractionFailedReason(_BaseReason):
    """Per ADR-0006. Distinct from low_confidence — this is the system,
    not the model, having failed.
    """

    type: Literal["extraction_failed"] = "extraction_failed"
    stage: Literal["pdf_read", "llm_call", "validation", "cascade_exhausted"]
    detail: str


TriageReason = Annotated[
    MathFailsReason
    | AnomalyReason
    | DuplicateOfReason
    | LowConfidenceReason
    | MissingFieldReason
    | UnseenVendorReason
    | ExtractionFailedReason,
    Field(discriminator="type"),
]


# ---------- Vendor memory — locked shape from PLAN.md ----------
class VendorMemoryRule(BaseModel):
    """A single learned rule applied to extractions for a vendor."""

    model_config = ConfigDict(extra="forbid")

    field: str
    pattern_type: Literal["date_format", "name_normalization", "static_value"]
    value: str
    source_correction_id: UUID
    applied_count: int = 0
    first_learned_at: datetime


class VendorMemoryStats(BaseModel):
    """Cached per-vendor stats — feeds anomaly detection AND history_score."""

    model_config = ConfigDict(extra="forbid")

    total_seen: int = 0
    avg_total: float = 0.0
    std_total: float = 0.0


class VendorMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules: list[VendorMemoryRule] = Field(default_factory=list)
    stats: VendorMemoryStats = Field(default_factory=VendorMemoryStats)


# ---------- Top-level types (for API responses + frontend codegen) ----------
class VendorOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    tax_id: str | None = None
    normalized_name: str
    first_seen_at: datetime
    memory: VendorMemory


class ExtractionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    invoice_id: UUID
    model: str
    cascade_trace: dict
    extracted_fields: dict[str, ExtractedField]
    confidence_per_field: dict[str, float]
    predicted_triage_state: TriageState
    predicted_triage_reasons: list[TriageReason]
    line_items: list[LineItem] = Field(default_factory=list)
    tax_breakdown: list[TaxBreakdownLine] = Field(default_factory=list)
    is_current: bool
    created_at: datetime


class InvoiceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    file_path: str
    file_hash: str
    perceptual_hash: str | None
    vendor_id: UUID | None
    uploaded_at: datetime
    review_status: ReviewStatus
    duplicate_dismissals: list[UUID] = Field(default_factory=list)
    current_extraction: ExtractionOut | None = None


class FieldCorrectionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    extraction_id: UUID
    field_name: str
    original_value: str | None
    corrected_value: str
    corrected_at: datetime
