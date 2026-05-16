"""LLM provider adapter -- ExtractionSpec-driven, single-method seam.

ADR-0005: services depend on the `LLMClient` Protocol, never on a concrete
implementation. The Protocol exposes ONE method, `call(spec, ...)`, that
dispatches per `ExtractionSpec`. Adding a new extraction (a sixth prompt /
schema / parser combination) is one new spec constant -- no new method on
the Protocol, no new method on either implementation.

Each ExtractionSpec carries:
  - `name`         -- short identifier for logs and stub dispatch
  - `prompt_name`  -- the versioned prompt file to load (ADR-0005 single
                     source of truth: prompt body + schema hashes are
                     logged per call)
  - `input_shape`  -- "text" or "vision"; the seam between the two
                     content-block shapes
  - `parser`       -- typed extractor from tool_use dict -> Result[T]
  - `max_tokens`   -- per-spec budget; defaults to header-sized

Implementations:
  - `AnthropicLLMClient` -- real provider. Tool-use + prompt-cached system
    block + tenacity retries on transient errors per ADR-0006.
  - `StubLLMClient`      -- deterministic offline stub for demos / interview
    review. Same single-method shape; spec.name dispatches to scripted
    scenario producers.
"""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar, Generic, Literal, Protocol, TypeVar

import structlog
from anthropic import (
    Anthropic,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    RateLimitError,
)
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings
from app.prompts import LoadedPrompt, load

log = structlog.get_logger(__name__)

@dataclass(frozen=True, slots=True)
class ExtractionResult:
    fields: dict[str, Any]
    self_reported_confidence: dict[str, float]
    extraction_failed: bool
    extraction_failure_reason: str | None
    model: str
    prompt_hash: str
    schema_hash: str
    usage: dict[str, int]

@dataclass(frozen=True, slots=True)
class LineItemsResult:
    """Output of the line-items spec — list of raw line-item dicts.

    Each dict matches `prompts/schemas/extraction_line_items_schema.json`:
    {description, quantity?, unit_price?, line_total, confidence?}.
    Service-layer code wraps these into domain.LineItem before persisting.
    """

    items: list[dict[str, Any]]
    model: str
    prompt_hash: str
    schema_hash: str
    usage: dict[str, int]

@dataclass(frozen=True, slots=True)
class StructuredQueryResult:
    """Output of the structured-query spec — raw payload matching the
    StructuredQuery schema (filters/sort/limit/untranslated_intent).

    Service-layer code validates the payload against the Pydantic
    StructuredQuery model (FIELD_OP_COMPATIBILITY) before handing it to
    the search builder. Malformed LLM output is rejected via ValueError,
    never silently passed through to SQL.
    """

    payload: dict[str, Any]
    model: str
    prompt_hash: str
    schema_hash: str
    usage: dict[str, int]

@dataclass(frozen=True, slots=True)
class TaxBreakdownResult:
    """Output of the tax-breakdown spec — list of raw per-jurisdiction rows.

    Each dict matches `prompts/schemas/extraction_tax_breakdown_schema.json`:
    {jurisdiction, rate?, amount, confidence?}.
    """

    rows: list[dict[str, Any]]
    model: str
    prompt_hash: str
    schema_hash: str
    usage: dict[str, int]

T = TypeVar("T")

_DEFAULT_MAX_TOKENS = 1024

@dataclass(frozen=True, slots=True)
class _CallContext:
    """Plumbing data the result parser may need."""

    model: str
    prompt_hash: str
    schema_hash: str
    usage: dict[str, int]

@dataclass(frozen=True, slots=True)
class ExtractionSpec(Generic[T]):
    """One LLM extraction operation: prompt + input shape + result parser.

    Adding a new extraction is one new module-level constant of this
    type. The `parser` callable converts the raw tool_use input dict
    plus per-call context into the typed Result[T] the caller expects.
    """

    name: str
    prompt_name: str
    input_shape: Literal["text", "vision"]
    parser: Callable[[dict[str, Any], _CallContext], T]
    max_tokens: int = _DEFAULT_MAX_TOKENS

def _parse_header_text(tool_input: dict[str, Any], ctx: _CallContext) -> ExtractionResult:
    """Text-path header: confidence + extraction_failed are top-level keys."""
    confidence = tool_input.pop("confidence", {}) or {}
    failed = bool(tool_input.pop("extraction_failed", False))
    failure_reason = tool_input.pop("extraction_failure_reason", None)
    return ExtractionResult(
        fields=tool_input,
        self_reported_confidence=confidence,
        extraction_failed=failed,
        extraction_failure_reason=failure_reason,
        model=ctx.model,
        prompt_hash=ctx.prompt_hash,
        schema_hash=ctx.schema_hash,
        usage=ctx.usage,
    )

def _parse_header_vision(tool_input: dict[str, Any], ctx: _CallContext) -> ExtractionResult:
    """Vision-path header: per-field {value, bbox, page, confidence} dicts.

    Self-reported confidence is pulled from each field's `confidence` key
    rather than from a top-level dict. The vision schema (ADR-0001) puts
    bboxes alongside values, so the field shape is richer than the text path.
    """
    failed = bool(tool_input.pop("extraction_failed", False))
    failure_reason = tool_input.pop("extraction_failure_reason", None)
    self_conf = {
        k: float(v.get("confidence", 0.0))
        for k, v in tool_input.items()
        if isinstance(v, dict)
    }
    return ExtractionResult(
        fields=tool_input,
        self_reported_confidence=self_conf,
        extraction_failed=failed,
        extraction_failure_reason=failure_reason,
        model=ctx.model,
        prompt_hash=ctx.prompt_hash,
        schema_hash=ctx.schema_hash,
        usage=ctx.usage,
    )

def _parse_line_items(tool_input: dict[str, Any], ctx: _CallContext) -> LineItemsResult:
    return LineItemsResult(
        items=list(tool_input.get("items") or []),
        model=ctx.model,
        prompt_hash=ctx.prompt_hash,
        schema_hash=ctx.schema_hash,
        usage=ctx.usage,
    )

def _parse_tax_breakdown(tool_input: dict[str, Any], ctx: _CallContext) -> TaxBreakdownResult:
    return TaxBreakdownResult(
        rows=list(tool_input.get("rows") or []),
        model=ctx.model,
        prompt_hash=ctx.prompt_hash,
        schema_hash=ctx.schema_hash,
        usage=ctx.usage,
    )

def _parse_structured_query(
    tool_input: dict[str, Any], ctx: _CallContext
) -> StructuredQueryResult:
    return StructuredQueryResult(
        payload=tool_input,
        model=ctx.model,
        prompt_hash=ctx.prompt_hash,
        schema_hash=ctx.schema_hash,
        usage=ctx.usage,
    )

EXTRACT_HEADER: ExtractionSpec[ExtractionResult] = ExtractionSpec(
    name="header",
    prompt_name="extraction_header_v2",
    input_shape="text",
    parser=_parse_header_text,
)

EXTRACT_HEADER_VISION: ExtractionSpec[ExtractionResult] = ExtractionSpec(
    name="header_vision",
    prompt_name="extraction_header_vision_v2",
    input_shape="vision",
    parser=_parse_header_vision,
)

EXTRACT_LINE_ITEMS: ExtractionSpec[LineItemsResult] = ExtractionSpec(
    name="line_items",
    prompt_name="extraction_line_items_v1",
    input_shape="text",
    parser=_parse_line_items,
)

EXTRACT_TAX_BREAKDOWN: ExtractionSpec[TaxBreakdownResult] = ExtractionSpec(
    name="tax_breakdown",
    prompt_name="extraction_tax_breakdown_v1",
    input_shape="text",
    parser=_parse_tax_breakdown,
)

EXTRACT_STRUCTURED_QUERY: ExtractionSpec[StructuredQueryResult] = ExtractionSpec(
    name="structured_query",
    prompt_name="nl_to_structured_query_v1",
    input_shape="text",
    parser=_parse_structured_query,
)

class LLMClient(Protocol):
    """Single-method seam: dispatch on ExtractionSpec for any extraction."""

    def call(
        self,
        spec: ExtractionSpec[T],
        *,
        model: str,
        text: str | None = None,
        page_pngs: list[bytes] | None = None,
    ) -> T: ...

def _is_transient_error(exc: BaseException) -> bool:
    """True for retryable Anthropic errors per ADR-0006: timeout, 429, 5xx."""
    if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError):
        return 500 <= exc.status_code < 600
    return False

_retry_decorator = retry(
    retry=retry_if_exception(_is_transient_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)

class AnthropicLLMClient:
    """Anthropic SDK-backed implementation of LLMClient.

    Tool-use schema + prompt-cached system block per ADR-0001. Tenacity
    retries on transient errors per ADR-0006 (timeout / 429 / 5xx, 3
    attempts, exponential backoff). Auth errors (401/403) and 4xx schema
    errors fast-fail without retry.
    """

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError(
                "AnthropicLLMClient requires ANTHROPIC_API_KEY. "
                "Set SIFT_LLM_PROVIDER=stub to run without a real key."
            )
        self._client = Anthropic(api_key=api_key)

    @_retry_decorator
    def call(
        self,
        spec: ExtractionSpec[T],
        *,
        model: str,
        text: str | None = None,
        page_pngs: list[bytes] | None = None,
    ) -> T:
        """Run an extraction. The spec's `input_shape` decides whether the
        request carries text or vision content blocks; the spec's `parser`
        converts the tool_use output to the typed Result[T].
        """
        if spec.input_shape == "text":
            if text is None:
                raise ValueError(
                    f"spec {spec.name!r} requires text=..., got None"
                )
            user_content: str | list[dict[str, Any]] = text
            input_size = len(text)
        else:
            if not page_pngs:
                raise ValueError(
                    f"spec {spec.name!r} requires page_pngs=..., got empty/None"
                )
            user_content = _build_vision_user_content(page_pngs)
            input_size = len(page_pngs)

        prompt: LoadedPrompt = load(spec.prompt_name)
        system = [
            {
                "type": "text",
                "text": prompt.body,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        tool = {
            "name": prompt.schema["name"],
            "description": prompt.schema["description"],
            "input_schema": prompt.schema["input_schema"],
        }

        log.info(
            f"llm.{spec.name}.start",
            model=model,
            prompt_hash=prompt.body_hash,
            schema_hash=prompt.schema_hash,
            input_size=input_size,
        )

        response = self._client.messages.create(
            model=model,
            max_tokens=spec.max_tokens,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": user_content}],
        )

        tool_input: dict[str, Any] | None = None
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool["name"]:
                tool_input = dict(block.input)
                break
        if tool_input is None:
            raise RuntimeError(f"LLM did not emit the {tool['name']} tool call")

        usage_obj = getattr(response, "usage", None)
        usage = {
            "input_tokens": getattr(usage_obj, "input_tokens", 0),
            "output_tokens": getattr(usage_obj, "output_tokens", 0),
            "cache_creation_input_tokens": getattr(usage_obj, "cache_creation_input_tokens", 0),
            "cache_read_input_tokens": getattr(usage_obj, "cache_read_input_tokens", 0),
        }
        log.info(
            f"llm.{spec.name}.done",
            model=model,
            prompt_hash=prompt.body_hash,
            usage=usage,
        )

        ctx = _CallContext(
            model=response.model,
            prompt_hash=prompt.body_hash,
            schema_hash=prompt.schema_hash,
            usage=usage,
        )
        return spec.parser(tool_input, ctx)

def _build_vision_user_content(page_pngs: list[bytes]) -> list[dict[str, Any]]:
    """Vision content: one image block per PNG plus a trailing instruction."""
    blocks: list[dict[str, Any]] = []
    for png in page_pngs:
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(png).decode(),
                },
            }
        )
    blocks.append({"type": "text", "text": "Extract the header fields."})
    return blocks

_SEED_VENDOR_RE = re.compile(r"\[seed-vendor:([^\]]+)\]")
_SEED_TOTAL_RE = re.compile(r"\[seed-total:([\d.]+)\]")
_SEED_NUMBER_RE = re.compile(r"\[seed-number:([^\]]+)\]")

class StubLLMClient:
    """Deterministic offline LLM stub.

    Default provider for local dev / interview review — produces realistic
    Results without any network or API key. Scenarios are chosen by
    keyword in the invoice text; the cascade flow is exercised because
    haiku and sonnet return slightly different `total` values, triggering
    the agreement-score override path in services/cascade.

    Override scenarios by including a keyword in the source document:
      "halcyon"   → big-spend invoice (drives anomaly demo with vendor history)
      "bramble"   → near-duplicate-friendly fixture
      "[stub:fail]" or "encrypted document" → extraction_failed=True
      default     → Vega Logistics, ~$1180, math reconciles on tier-2+

    Seed markers (used by scripts/seed_demo.py to populate the demo inbox):
      [seed-vendor:Name] → force vendor_name
      [seed-total:N]     → force total to N (subtotal/tax derived 85/15)
      [seed-number:X]    → force invoice_number to X
    """

    _SCENARIOS: ClassVar[dict[str, dict[str, Any]]] = {
        "halcyon": {
            "vendor_name": "Halcyon Software",
            "invoice_number_prefix": "HAL-2026-",
            "subtotal": 28_900.00,
            "tax": 5_162.50,
            "total_tier1": 34_063.50,
            "total_tier2": 34_062.50,
            "currency": "USD",
            "line_items": [
                {
                    "description": "Annual Platform License — Enterprise tier",
                    "quantity": 1,
                    "unit_price": 24_000.00,
                    "line_total": 24_000.00,
                },
                {
                    "description": "Premium Support Add-on (24x7)",
                    "quantity": 1,
                    "unit_price": 4_900.00,
                    "line_total": 4_900.00,
                },
            ],
            "tax_breakdown": [
                {"jurisdiction": "California State Sales Tax", "rate": 7.25, "amount": 2_095.25},
                {"jurisdiction": "San Francisco County Tax", "rate": 1.0, "amount": 289.00},
                {"jurisdiction": "Local City Surcharge", "rate": 9.95, "amount": 2_778.25},
            ],
        },
        "bramble": {
            "vendor_name": "Bramble Catering",
            "invoice_number_prefix": "BR-2026-",
            "subtotal": 635.59,
            "tax": 114.41,
            "total_tier1": 751.00,
            "total_tier2": 750.00,
            "currency": "USD",
            "line_items": [
                {
                    "description": "House Salad (small bowl)",
                    "quantity": 20,
                    "unit_price": 8.50,
                    "line_total": 170.00,
                },
                {
                    "description": "Roast Vegetable Platter",
                    "quantity": 8,
                    "unit_price": 24.50,
                    "line_total": 196.00,
                },
                {
                    "description": "Sourdough Sandwiches (assorted)",
                    "quantity": 18,
                    "unit_price": 9.99,
                    "line_total": 179.82,
                },
                {
                    "description": "Sparkling Water (1L)",
                    "quantity": 12,
                    "unit_price": 4.50,
                    "line_total": 54.00,
                },
                {
                    "description": "Service & Setup Fee",
                    "quantity": None,
                    "unit_price": None,
                    "line_total": 35.77,
                },
            ],
            "tax_breakdown": [
                {"jurisdiction": "GST", "rate": 18.0, "amount": 114.41},
            ],
        },
        "default": {
            "vendor_name": "Vega Logistics",
            "invoice_number_prefix": "INV-2026-",
            "subtotal": 1_000.00,
            "tax": 180.00,
            "total_tier1": 1_181.00,
            "total_tier2": 1_180.00,
            "currency": "USD",
            "line_items": [
                {
                    "description": "Last-Mile Delivery — Aurora freight",
                    "quantity": 12,
                    "unit_price": 65.00,
                    "line_total": 780.00,
                },
                {
                    "description": "Pallet Handling & Sorting",
                    "quantity": 4,
                    "unit_price": 35.00,
                    "line_total": 140.00,
                },
                {
                    "description": "Fuel Surcharge",
                    "quantity": None,
                    "unit_price": None,
                    "line_total": 80.00,
                },
            ],
            "tax_breakdown": [
                {"jurisdiction": "Federal Excise", "rate": 12.0, "amount": 120.00},
                {"jurisdiction": "State Highway Surcharge", "rate": 6.0, "amount": 60.00},
            ],
        },
    }

    def call(
        self,
        spec: ExtractionSpec[T],
        *,
        model: str,
        text: str | None = None,
        page_pngs: list[bytes] | None = None,
    ) -> T:
        """Dispatch on spec.name to the appropriate scripted scenario.

        Returns the same typed Result the Anthropic client would, just
        synthesized from the canned _SCENARIOS map (or _stub_translate_nl
        for the structured-query spec).
        """
        if spec.name == "header":
            if text is None:
                raise ValueError("EXTRACT_HEADER requires text=")
            return self._stub_header(text=text, model=model)  # type: ignore[return-value]
        if spec.name == "header_vision":
            if page_pngs is None:
                raise ValueError("EXTRACT_HEADER_VISION requires page_pngs=")
            return self._stub_header_vision(page_pngs=page_pngs, model=model)  # type: ignore[return-value]
        if spec.name == "line_items":
            if text is None:
                raise ValueError("EXTRACT_LINE_ITEMS requires text=")
            return self._stub_line_items(text=text, model=model)  # type: ignore[return-value]
        if spec.name == "tax_breakdown":
            if text is None:
                raise ValueError("EXTRACT_TAX_BREAKDOWN requires text=")
            return self._stub_tax_breakdown(text=text, model=model)  # type: ignore[return-value]
        if spec.name == "structured_query":
            if text is None:
                raise ValueError("EXTRACT_STRUCTURED_QUERY requires text=")
            return self._stub_structured_query(natural_language=text, model=model)  # type: ignore[return-value]
        raise ValueError(f"StubLLMClient: unknown spec name {spec.name!r}")

    def _stub_header(self, *, text: str, model: str) -> ExtractionResult:
        if self._is_failure_trigger(text):
            return self._failure_result(model=model, vision=False)
        scenario = self._pick_scenario(text)
        seed = self._seed_from(text)
        fields = self._build_fields(scenario, model=model, seed=seed)
        _apply_seed_overrides(fields, text, model=model)
        confidence = {k: 0.95 for k in fields}
        log.info("llm.header.stub", model=model, scenario=scenario["vendor_name"])
        return ExtractionResult(
            fields=fields,
            self_reported_confidence=confidence,
            extraction_failed=False,
            extraction_failure_reason=None,
            model=model,
            prompt_hash="stub-text-v1",
            schema_hash="stub-text-v1",
            usage=_stub_usage(),
        )

    def _stub_header_vision(self, *, page_pngs: list[bytes], model: str) -> ExtractionResult:
        seed_text = hashlib.sha256(b"".join(page_pngs)).hexdigest()
        scenario = self._SCENARIOS["default"]
        seed = self._seed_from(seed_text)
        flat = self._build_fields(scenario, model=model, seed=seed)
        bboxes = {
            "vendor_name": [0.08, 0.06, 0.55, 0.10],
            "invoice_number": [0.66, 0.13, 0.92, 0.16],
            "invoice_date": [0.66, 0.17, 0.92, 0.20],
            "subtotal": [0.70, 0.61, 0.92, 0.64],
            "tax": [0.70, 0.65, 0.92, 0.68],
            "total": [0.70, 0.71, 0.92, 0.74],
            "currency": [0.62, 0.71, 0.69, 0.74],
        }
        fields: dict[str, Any] = {}
        for k, v in flat.items():
            fields[k] = {
                "value": v,
                "bbox": bboxes.get(k),
                "page": 0,
                "confidence": 0.95,
            }
        log.info("llm.header_vision.stub", model=model, n_pages=len(page_pngs))
        return ExtractionResult(
            fields=fields,
            self_reported_confidence={k: 0.95 for k in fields},
            extraction_failed=False,
            extraction_failure_reason=None,
            model=model,
            prompt_hash="stub-vision-v1",
            schema_hash="stub-vision-v1",
            usage=_stub_usage(),
        )

    def _stub_line_items(self, *, text: str, model: str) -> LineItemsResult:
        if self._is_failure_trigger(text):
            return LineItemsResult(
                items=[],
                model=model,
                prompt_hash="stub-line-items-v1",
                schema_hash="stub-line-items-v1",
                usage=_stub_usage(),
            )
        scenario = self._pick_scenario(text)
        items_template = scenario.get("line_items", [])
        items = [{**item, "confidence": 0.92, "page": 0} for item in items_template]
        log.info(
            "llm.line_items.stub",
            model=model,
            scenario=scenario["vendor_name"],
            n_items=len(items),
        )
        return LineItemsResult(
            items=items,
            model=model,
            prompt_hash="stub-line-items-v1",
            schema_hash="stub-line-items-v1",
            usage=_stub_usage(),
        )

    def _stub_tax_breakdown(self, *, text: str, model: str) -> TaxBreakdownResult:
        if self._is_failure_trigger(text):
            return TaxBreakdownResult(
                rows=[],
                model=model,
                prompt_hash="stub-tax-breakdown-v1",
                schema_hash="stub-tax-breakdown-v1",
                usage=_stub_usage(),
            )
        scenario = self._pick_scenario(text)
        rows_template = scenario.get("tax_breakdown", [])
        rows = [{**row, "confidence": 0.94, "page": 0} for row in rows_template]
        log.info(
            "llm.tax_breakdown.stub",
            model=model,
            scenario=scenario["vendor_name"],
            n_rows=len(rows),
        )
        return TaxBreakdownResult(
            rows=rows,
            model=model,
            prompt_hash="stub-tax-breakdown-v1",
            schema_hash="stub-tax-breakdown-v1",
            usage=_stub_usage(),
        )

    def _stub_structured_query(
        self, *, natural_language: str, model: str
    ) -> StructuredQueryResult:
        payload = _stub_translate_nl(natural_language)
        log.info(
            "llm.structured_query.stub",
            model=model,
            n_filters=len(payload.get("filters", []) or []),
            untranslated=bool(payload.get("untranslated_intent")),
        )
        return StructuredQueryResult(
            payload=payload,
            model=model,
            prompt_hash="stub-nl-translate-v1",
            schema_hash="stub-nl-translate-v1",
            usage=_stub_usage(),
        )

    @staticmethod
    def _is_failure_trigger(text: str) -> bool:
        lower = text.lower()
        return "[stub:fail]" in lower or "encrypted document" in lower

    @staticmethod
    def _failure_result(*, model: str, vision: bool) -> ExtractionResult:
        return ExtractionResult(
            fields={},
            self_reported_confidence={},
            extraction_failed=True,
            extraction_failure_reason="stub provider: failure-mode keyword detected",
            model=model,
            prompt_hash="stub-vision-v1" if vision else "stub-text-v1",
            schema_hash="stub-vision-v1" if vision else "stub-text-v1",
            usage=_stub_usage(),
        )

    @classmethod
    def _pick_scenario(cls, text: str) -> dict[str, Any]:
        lower = text.lower()
        for key, scenario in cls._SCENARIOS.items():
            if key == "default":
                continue
            if key in lower:
                return scenario
        return cls._SCENARIOS["default"]

    @staticmethod
    def _seed_from(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:4].upper()

    @staticmethod
    def _build_fields(scenario: dict[str, Any], *, model: str, seed: str) -> dict[str, Any]:

        is_tier_1 = "haiku" in model.lower()
        total = scenario["total_tier1"] if is_tier_1 else scenario["total_tier2"]
        return {
            "vendor_name": scenario["vendor_name"],
            "invoice_number": f"{scenario['invoice_number_prefix']}{seed}",
            "invoice_date": "2026-05-13",
            "subtotal": scenario["subtotal"],
            "tax": scenario["tax"],
            "total": total,
            "currency": scenario["currency"],
        }

def _apply_seed_overrides(fields: dict[str, Any], invoice_text: str, *, model: str) -> None:
    """Apply seed-script markers found in invoice_text in-place.

    Used by scripts/seed_demo.py to deterministically vary vendor/total per
    seeded PDF so vendor history can build with std > 0 (needed for anomaly
    detection). Markers in production invoice text are harmless — the regex
    won't match real OCR output.
    """
    v = _SEED_VENDOR_RE.search(invoice_text)
    if v:
        fields["vendor_name"] = v.group(1).strip()
    n = _SEED_NUMBER_RE.search(invoice_text)
    if n:
        fields["invoice_number"] = n.group(1).strip()
    t = _SEED_TOTAL_RE.search(invoice_text)
    if t:
        base = float(t.group(1))
        is_tier_1 = "haiku" in model.lower()
        fields["total"] = base + 1.0 if is_tier_1 else base
        fields["subtotal"] = round(base * 0.85, 2)
        fields["tax"] = round(base - base * 0.85, 2)

_NL_AMOUNT_RE = re.compile(
    r"(?:over|above|greater than|more than|>=|>)\s*\$?\s*([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
_NL_UNDER_RE = re.compile(
    r"(?:under|below|less than|<=|<)\s*\$?\s*([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
_NL_VENDOR_RE = re.compile(
    r"\bfrom\s+(?:vendor\s+)?([A-Z][\w&.'\- ]{2,30})",
    re.IGNORECASE,
)

_TODAY_PREFIX_RE = re.compile(r"^Today is \d{4}-\d{2}-\d{2}\.\s*Query:\s*", re.IGNORECASE)


def _stub_translate_nl(natural_language: str) -> dict[str, Any]:
    """Deterministic NL -> StructuredQuery payload for the stub provider.

    Intentionally narrow: covers the demo phrasings we control with seed
    data plus obvious fallbacks. Anything it can't translate flows to
    `untranslated_intent` so the UI can show the amber notice.
    """
    text = _TODAY_PREFIX_RE.sub("", natural_language.strip()).strip()
    lowered = text.lower()
    filters: list[dict[str, Any]] = []
    handled_spans: list[tuple[int, int]] = []

    def _mark(match: re.Match[str]) -> None:
        handled_spans.append((match.start(), match.end()))

    def _mark_words(*patterns: str) -> bool:
        hit = False
        for kw in patterns:
            for m in re.finditer(rf"\b\w*{re.escape(kw)}\w*\b", lowered):
                handled_spans.append((m.start(), m.end()))
                hit = True
        return hit

    if _mark_words("duplicate"):
        filters.append({"field": "triage_state", "op": "eq", "value": "likely_duplicate"})
    if _mark_words("anomal", "flagged"):
        filters.append({"field": "has_anomaly", "op": "eq", "value": True})
    for phrase in ("needs review", "pending review", "to review"):
        idx = lowered.find(phrase)
        if idx >= 0:
            filters.append({"field": "triage_state", "op": "eq", "value": "needs_review"})
            handled_spans.append((idx, idx + len(phrase)))
            break
    if _mark_words("confirmed"):
        filters.append({"field": "review_status", "op": "eq", "value": "confirmed"})
    if _mark_words("unprocessable", "encrypted"):
        filters.append({"field": "review_status", "op": "eq", "value": "unprocessable"})
    elif "failed to extract" in lowered:
        filters.append({"field": "review_status", "op": "eq", "value": "unprocessable"})
        idx = lowered.find("failed to extract")
        handled_spans.append((idx, idx + len("failed to extract")))

    over = _NL_AMOUNT_RE.search(text)
    if over:
        amount = float(over.group(1).replace(",", ""))
        filters.append({"field": "total", "op": "gt", "value": amount})
        _mark(over)
    under = _NL_UNDER_RE.search(text)
    if under:
        amount = float(under.group(1).replace(",", ""))
        filters.append({"field": "total", "op": "lt", "value": amount})
        _mark(under)

    vendor = _NL_VENDOR_RE.search(text)
    if vendor:
        name = vendor.group(1).strip().rstrip(".,;:")
        if name.lower() not in {
            "needs review",
            "the last",
            "this month",
            "this week",
        }:
            filters.append({"field": "vendor_name", "op": "eq", "value": name})
            _mark(vendor)

    handled_spans.sort()
    untranslated_chunks: list[str] = []
    cursor = 0
    for start, end in handled_spans:
        if start > cursor:
            chunk = text[cursor:start].strip()
            if chunk:
                untranslated_chunks.append(chunk)
        cursor = max(cursor, end)
    if cursor < len(text):
        chunk = text[cursor:].strip()
        if chunk:
            untranslated_chunks.append(chunk)

    cleaned = " ".join(untranslated_chunks).strip()
    _NOISE_WORDS = {
        "show",
        "me",
        "all",
        "find",
        "invoices",
        "invoice",
        "from",
        "the",
        "any",
        "give",
        "list",
        "of",
        "with",
        "where",
    }
    tokens = [t for t in re.split(r"\s+|[,.]", cleaned) if t and t.lower() not in _NOISE_WORDS]
    cleaned = " ".join(tokens).strip()

    return {
        "filters": filters,
        "limit": 50,
        "untranslated_intent": cleaned or None,
    }

def _stub_usage() -> dict[str, int]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }

class BudgetedLLMClient:
    """LLMClient wrapper that enforces the API spend cap.

    Before every call: refuses if total recorded cost has reached the cap.
    After every successful call: persists a usage row (own transaction).

    The wrapper is added unconditionally — for the stub provider its
    pricing computes to $0 so it's a no-op, and tests can still assert
    on the audit trail without a special path.
    """

    def __init__(
        self,
        inner: LLMClient,
        *,
        session_factory,
        limit_usd: float,
    ) -> None:
        self._inner = inner
        self._session_factory = session_factory
        self._limit_usd = limit_usd

    def call(
        self,
        spec: ExtractionSpec[T],
        *,
        model: str,
        text: str | None = None,
        page_pngs: list[bytes] | None = None,
    ) -> T:
        from app.services import usage_service

        with self._session_factory() as session:
            usage_service.assert_within_budget(session, limit_usd=self._limit_usd)

        result = self._inner.call(spec, model=model, text=text, page_pngs=page_pngs)

        usage = getattr(result, "usage", None)
        if isinstance(usage, dict):
            usage_service.record_usage(
                self._session_factory,
                model=getattr(result, "model", model),
                spec_name=spec.name,
                usage=usage,
            )
        return result


def make_llm_client(settings: Settings, *, session_factory=None) -> LLMClient:
    """Pick the LLMClient impl based on Settings.llm_provider.

    Default is `stub` so a fresh checkout can run the full pipeline with no
    API key. Set `SIFT_LLM_PROVIDER=anthropic` (and `ANTHROPIC_API_KEY=...`)
    for real model calls.

    The returned client is always wrapped in `BudgetedLLMClient` so the
    spend cap and audit trail apply uniformly. Callers that don't pass a
    `session_factory` (tests, scripts) get the SessionLocal default.
    """
    provider = settings.llm_provider
    if provider == "anthropic":
        inner: LLMClient = AnthropicLLMClient(api_key=settings.anthropic_api_key)
    elif provider == "stub":
        inner = StubLLMClient()
    else:
        raise ValueError(
            f"Unknown SIFT_LLM_PROVIDER={provider!r}. Expected 'stub' or 'anthropic'."
        )

    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal
    return BudgetedLLMClient(
        inner, session_factory=session_factory, limit_usd=settings.api_budget_usd
    )
