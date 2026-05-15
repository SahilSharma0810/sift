"""Cascade orchestration per ADR-0003 (Haiku -> Sonnet -> Opus).

The Cascade is Sift's tiered-model contract: a reactive escalation that
starts at the model tier appropriate for the input (Haiku on digital,
Sonnet on vision) and walks up to Sonnet then Opus when the initial
extraction's Composite Confidence falls below the trigger threshold,
math fails to reconcile, or the Vendor is unseen.

This module is the single source of truth for that contract. Pure helpers
(should_trigger_cascade, agreement_score) live in domain/scoring.py; the
orchestration lives here because it calls IO.

Quality contract:

* Auto-trigger conditions live in domain.scoring.should_trigger_cascade.
* When the cascade escalates, agreement_score(initial_value, next_value)
  per field decides disputed-vs-confirmed. Disputed values are replaced
  by the higher tier and their composite confidence is later overridden
  by the agreement score in the callsite.
* Math is re-checked on post-Sonnet values. If math fails but `total`
  didn't dispute against Sonnet, `total` is forced into the disputed
  set so Opus runs - same-error agreement is the cascade's known blind
  spot (see DocILE case 04345516).
* Clerk-forced tiers (Cmd+K "Force Sonnet" / "Force Opus" per ADR-0006)
  route through this module via `force_escalate=True`. The force is on
  the starting tier, not on bypassing quality discipline - higher tiers
  still run with agreement scoring, so a forced Sonnet on the digital
  path produces the same trace and quality posture as an auto-cascaded
  Sonnet on the same invoice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from app.adapters.llm_client import (
    EXTRACT_HEADER,
    EXTRACT_HEADER_VISION,
    ExtractionResult,
    LLMClient,
)
from app.config import Settings
from app.domain.scoring import agreement_score, should_trigger_cascade
from app.domain.validators import REQUIRED_FIELDS, math_reconciles

log = structlog.get_logger(__name__)

# Fields the cascade compares for agreement. REQUIRED_FIELDS plus the
# arithmetic dependents math_reconciles cares about.
CASCADE_FIELDS: tuple[str, ...] = (*REQUIRED_FIELDS, "subtotal", "tax")

# Agreement-score threshold below which a field is considered disputed.
# Two-bucket scoring (1.0 / 0.3) per ADR-0003 makes 0.3 the boundary.
DISPUTE_THRESHOLD = 0.3


@dataclass(frozen=True, slots=True)
class TierTrace:
    """Per-tier execution record on the cascade trace.

    Persisted as part of `cascade_trace.tiers` on the Extraction row.
    Fields mirror the historical on-disk shape so the refactor is
    schema-compatible.
    """

    model: str
    prompt_hash: str
    schema_hash: str
    usage: dict[str, int]
    llm_self_confidence: dict[str, float]

    @classmethod
    def from_result(cls, r: ExtractionResult) -> TierTrace:
        return cls(
            model=r.model,
            prompt_hash=r.prompt_hash,
            schema_hash=r.schema_hash,
            usage=r.usage,
            llm_self_confidence=r.self_reported_confidence,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "prompt_hash": self.prompt_hash,
            "schema_hash": self.schema_hash,
            "usage": self.usage,
            "llm_self_confidence": self.llm_self_confidence,
        }


@dataclass(frozen=True, slots=True)
class CascadeResult:
    """Cascade output: final field values plus full per-field provenance.

    `cascade_fired` is derived from `tier_traces` (more than one tier =
    fired). Callers never branch on Optional - all four maps are always
    populated, even when no escalation happened.
    """

    final_fields: dict[str, Any]
    agreement_overrides: dict[str, float]
    tier_traces: list[TierTrace]
    per_field_source: dict[str, str]
    raw_initial_fields: dict[str, Any] | None

    @property
    def cascade_fired(self) -> bool:
        return len(self.tier_traces) > 1

    @property
    def trace_tiers_dicts(self) -> list[dict[str, Any]]:
        """Persistable form of tier_traces for the JSONB cascade_trace column."""
        return [t.to_dict() for t in self.tier_traces]


def run_cascade(
    *,
    llm: LLMClient,
    initial: ExtractionResult,
    initial_tier: str,
    invoice_text: str | None,
    page_pngs: list[bytes] | None,
    settings: Settings,
    composite_confidence: dict[str, float],
    math_passed: bool,
    is_unseen_vendor: bool,
    force_escalate: bool = False,
) -> CascadeResult:
    """Run the tiered Haiku -> Sonnet -> Opus cascade.

    Decides whether to escalate (per ADR-0003 trigger or clerk force),
    orchestrates the next-tier LLM calls, and applies agreement-score
    overrides on disputed fields. The cascade is the single source of
    truth for "which tier's value wins, and which fields' confidence is
    replaced by the cross-model agreement score."

    Force escalation: `force_escalate=True` skips the trigger check and
    runs all higher tiers above `initial_tier`. A clerk's "Force Sonnet"
    on the digital path means initial=Sonnet plus an Opus comparison;
    "Force Opus" returns the initial unchanged (no higher tier exists).
    """
    initial_flat = _flat_fields(initial.fields)
    raw_initial = initial.fields if page_pngs is not None else None
    base = _make_base_result(initial_flat, initial, initial_tier, raw_initial)

    should_fire = force_escalate or should_trigger_cascade(
        composite_confidence,
        math_passed=math_passed,
        is_unseen_vendor=is_unseen_vendor,
    )
    if not should_fire:
        return base

    log.info(
        "cascade.fire",
        initial_tier=initial_tier,
        forced=force_escalate,
        math_passed=math_passed,
        is_unseen_vendor=is_unseen_vendor,
    )

    if initial_tier == "haiku":
        return _haiku_to_sonnet_to_opus(
            llm=llm,
            base=base,
            invoice_text=invoice_text,
            page_pngs=page_pngs,
            settings=settings,
        )
    if initial_tier == "sonnet":
        return _sonnet_to_opus(
            llm=llm,
            base=base,
            initial=initial,
            invoice_text=invoice_text,
            page_pngs=page_pngs,
            settings=settings,
            forced=force_escalate,
        )
    return base


# ---------- Private helpers --------------------------------------------------


def _make_base_result(
    fields: dict[str, Any],
    initial: ExtractionResult,
    tier: str,
    raw_initial: dict[str, Any] | None,
) -> CascadeResult:
    return CascadeResult(
        final_fields=dict(fields),
        agreement_overrides={},
        tier_traces=[TierTrace.from_result(initial)],
        per_field_source={k: tier for k in fields},
        raw_initial_fields=raw_initial,
    )


def _haiku_to_sonnet_to_opus(
    *,
    llm: LLMClient,
    base: CascadeResult,
    invoice_text: str | None,
    page_pngs: list[bytes] | None,
    settings: Settings,
) -> CascadeResult:
    sonnet_result = _call_at_tier(
        llm=llm,
        tier="sonnet",
        model=settings.model_tier_2,
        invoice_text=invoice_text,
        page_pngs=page_pngs,
    )
    if sonnet_result is None:
        return base

    fields = dict(base.final_fields)
    per_field_source = dict(base.per_field_source)
    overrides: dict[str, float] = {}
    traces = [*base.tier_traces, TierTrace.from_result(sonnet_result)]

    sonnet_flat = _flat_fields(sonnet_result.fields)
    disputed: list[str] = []
    for field_name in CASCADE_FIELDS:
        h_val = fields.get(field_name)
        s_val = sonnet_flat.get(field_name)
        score = agreement_score(h_val, s_val, field_name)
        overrides[field_name] = score
        if score <= DISPUTE_THRESHOLD:
            disputed.append(field_name)
            fields[field_name] = s_val
            per_field_source[field_name] = "sonnet"

    # Same-error agreement blind spot per ADR-0003 commentary: math is
    # independent ground truth that agreement can't catch.
    if not _math_ok(fields) and "total" not in disputed:
        disputed.append("total")

    required_disputes = [f for f in disputed if f in REQUIRED_FIELDS]
    if not required_disputes:
        return CascadeResult(
            final_fields=fields,
            agreement_overrides=overrides,
            tier_traces=traces,
            per_field_source=per_field_source,
            raw_initial_fields=base.raw_initial_fields,
        )

    opus_result = _call_at_tier(
        llm=llm,
        tier="opus",
        model=settings.model_tier_3,
        invoice_text=invoice_text,
        page_pngs=page_pngs,
    )
    if opus_result is None:
        return CascadeResult(
            final_fields=fields,
            agreement_overrides=overrides,
            tier_traces=traces,
            per_field_source=per_field_source,
            raw_initial_fields=base.raw_initial_fields,
        )

    traces = [*traces, TierTrace.from_result(opus_result)]
    opus_flat = _flat_fields(opus_result.fields)
    for field_name in required_disputes:
        opus_val = opus_flat.get(field_name)
        # Two-of-three consensus: if Opus agrees with the current
        # (Sonnet-or-Haiku) value, lift the dispute override to 1.0.
        if agreement_score(opus_val, fields.get(field_name), field_name) == 1.0:
            overrides[field_name] = 1.0
        fields[field_name] = opus_val
        per_field_source[field_name] = "opus"

    return CascadeResult(
        final_fields=fields,
        agreement_overrides=overrides,
        tier_traces=traces,
        per_field_source=per_field_source,
        raw_initial_fields=base.raw_initial_fields,
    )


def _sonnet_to_opus(
    *,
    llm: LLMClient,
    base: CascadeResult,
    initial: ExtractionResult,
    invoice_text: str | None,
    page_pngs: list[bytes] | None,
    settings: Settings,
    forced: bool,
) -> CascadeResult:
    """Sonnet -> Opus path (vision auto-cascade, or forced Sonnet on digital).

    Vision auto-cascade applies an extra inner-trigger check: only
    escalate to Opus on math fail OR self-reported low confidence on a
    REQUIRED field. Forced runs skip this check - the clerk explicitly
    wanted Opus discipline. Self-reported confidence is not trusted for
    composite scoring (ADR-0003) but IS trusted as a cost-routing signal
    here: false-positive escalations cost money, never correctness.
    """
    fields = dict(base.final_fields)
    if not forced and not _vision_should_escalate(initial, fields):
        return base

    opus_result = _call_at_tier(
        llm=llm,
        tier="opus",
        model=settings.model_tier_3,
        invoice_text=invoice_text,
        page_pngs=page_pngs,
    )
    if opus_result is None:
        return base

    per_field_source = dict(base.per_field_source)
    overrides: dict[str, float] = {}
    traces = [*base.tier_traces, TierTrace.from_result(opus_result)]
    opus_flat = _flat_fields(opus_result.fields)
    for field_name in CASCADE_FIELDS:
        a = fields.get(field_name)
        b = opus_flat.get(field_name)
        score = agreement_score(a, b, field_name)
        overrides[field_name] = score
        if score <= DISPUTE_THRESHOLD:
            fields[field_name] = b
            per_field_source[field_name] = "opus"

    return CascadeResult(
        final_fields=fields,
        agreement_overrides=overrides,
        tier_traces=traces,
        per_field_source=per_field_source,
        raw_initial_fields=base.raw_initial_fields,
    )


def _call_at_tier(
    *,
    llm: LLMClient,
    tier: str,
    model: str,
    invoice_text: str | None,
    page_pngs: list[bytes] | None,
) -> ExtractionResult | None:
    """Dispatch the right extraction spec for the available input."""
    if invoice_text is not None:
        return llm.call(EXTRACT_HEADER, model=model, text=invoice_text)
    if page_pngs is not None:
        return llm.call(EXTRACT_HEADER_VISION, model=model, page_pngs=page_pngs)
    return None


def _vision_should_escalate(initial: ExtractionResult, fields: dict[str, Any]) -> bool:
    """Vision-path inner trigger: math fail OR low self-confidence on REQUIRED."""
    if not _math_ok(fields):
        return True
    return any(initial.self_reported_confidence.get(f, 1.0) < 0.7 for f in REQUIRED_FIELDS)


def _flat_fields(raw: dict[str, Any]) -> dict[str, Any]:
    return {k: _normalize_value(v) for k, v in raw.items()}


def _normalize_value(v: Any) -> Any:
    if isinstance(v, dict) and "value" in v:
        return v["value"]
    return v


def _math_ok(fields: dict[str, Any]) -> bool:
    return math_reconciles(
        subtotal=_maybe_float(fields.get("subtotal")),
        tax=_maybe_float(fields.get("tax")),
        total=_maybe_float(fields.get("total")),
    )


def _maybe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
