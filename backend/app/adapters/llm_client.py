"""LLM provider adapter — Protocol + concrete impls + factory.

ADR-0005: services depend on the `LLMClient` Protocol, never on a concrete
implementation. The factory picks the impl based on `Settings.llm_provider`.

Implementations:
- `AnthropicLLMClient` — real provider. Tool-use + prompt-cache + tenacity
  retries on transient errors.
- `StubLLMClient` — deterministic offline stub for demos / interview review.
  Returns canned ExtractionResults that vary slightly by input hash and
  model tier so cascade traces look realistic without any API calls.

One method per use case per ADR-0005. Never a generic `call_claude`.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol

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

# Header extraction fits comfortably under 1024 tokens. When extract_line_items
# lands, lift this per-method (line items can be 500-1000 tokens by themselves).
_HEADER_MAX_TOKENS = 1024


# ---------- Public surface ---------------------------------------------------


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
    """Output of extract_line_items — list of raw line-item dicts.

    Each dict matches the schema in prompts/schemas/extraction_line_items_schema.json:
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
    """Output of extract_structured_query — raw payload matching the
    StructuredQuery schema (filters/sort/limit/untranslated_intent).

    Service-layer code validates the payload against the Pydantic
    StructuredQuery model (FIELD_OP_COMPATIBILITY enforced there) before
    handing it to the search builder. Malformed LLM output is rejected
    via ValueError, never silently passed through to SQL.
    """

    payload: dict[str, Any]
    model: str
    prompt_hash: str
    schema_hash: str
    usage: dict[str, int]


@dataclass(frozen=True, slots=True)
class TaxBreakdownResult:
    """Output of extract_tax_breakdown — list of raw per-jurisdiction rows.

    Each dict matches the schema in prompts/schemas/extraction_tax_breakdown_schema.json:
    {jurisdiction, rate?, amount, confidence?}.
    """

    rows: list[dict[str, Any]]
    model: str
    prompt_hash: str
    schema_hash: str
    usage: dict[str, int]


class LLMClient(Protocol):
    """Structural interface for LLM adapters. Services depend on this Protocol."""

    def extract_header(
        self,
        *,
        invoice_text: str,
        model: str,
        prompt_name: str = "extraction_header_v1",
    ) -> ExtractionResult: ...

    def extract_header_vision(
        self,
        *,
        page_pngs: list[bytes],
        model: str,
        prompt_name: str = "extraction_header_vision_v1",
    ) -> ExtractionResult: ...

    def extract_line_items(
        self,
        *,
        invoice_text: str,
        model: str,
        prompt_name: str = "extraction_line_items_v1",
    ) -> LineItemsResult: ...

    def extract_tax_breakdown(
        self,
        *,
        invoice_text: str,
        model: str,
        prompt_name: str = "extraction_tax_breakdown_v1",
    ) -> TaxBreakdownResult: ...

    def extract_structured_query(
        self,
        *,
        natural_language: str,
        model: str,
        prompt_name: str = "nl_to_structured_query_v1",
    ) -> StructuredQueryResult: ...


# ---------- Anthropic implementation -----------------------------------------


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
    retries on transient errors per ADR-0006 (timeout / 429 / 5xx, 3 attempts,
    exponential backoff). Auth errors (401/403) and 4xx schema errors
    fast-fail without retry.
    """

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError(
                "AnthropicLLMClient requires ANTHROPIC_API_KEY. "
                "Set SIFT_LLM_PROVIDER=stub to run without a real key."
            )
        self._client = Anthropic(api_key=api_key)

    @_retry_decorator
    def extract_header(
        self,
        *,
        invoice_text: str,
        model: str,
        prompt_name: str = "extraction_header_v1",
    ) -> ExtractionResult:
        """Extract header fields via tool-use. Prompt-cached system block."""
        prompt: LoadedPrompt = load(prompt_name)

        system = [
            {
                "type": "text",
                "text": prompt.body,
                "cache_control": {"type": "ephemeral"},  # prompt-cache the system block
            }
        ]

        tool = {
            "name": prompt.schema["name"],
            "description": prompt.schema["description"],
            "input_schema": prompt.schema["input_schema"],
        }

        log.info(
            "llm.extract_header.start",
            model=model,
            prompt_hash=prompt.body_hash,
            schema_hash=prompt.schema_hash,
            input_chars=len(invoice_text),
        )

        response = self._client.messages.create(
            model=model,
            max_tokens=_HEADER_MAX_TOKENS,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": invoice_text}],
        )

        tool_input: dict[str, Any] | None = None
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool["name"]:
                tool_input = dict(block.input)  # detach from SDK before mutation
                break

        if tool_input is None:
            raise RuntimeError(f"LLM did not emit the {tool['name']} tool call")

        confidence = tool_input.pop("confidence", {}) or {}
        failed = bool(tool_input.pop("extraction_failed", False))
        failure_reason = tool_input.pop("extraction_failure_reason", None)

        usage_obj = getattr(response, "usage", None)
        usage = {
            "input_tokens": getattr(usage_obj, "input_tokens", 0),
            "output_tokens": getattr(usage_obj, "output_tokens", 0),
            "cache_creation_input_tokens": getattr(usage_obj, "cache_creation_input_tokens", 0),
            "cache_read_input_tokens": getattr(usage_obj, "cache_read_input_tokens", 0),
        }

        log.info(
            "llm.extract_header.done",
            model=model,
            prompt_hash=prompt.body_hash,
            usage=usage,
            extraction_failed=failed,
        )

        return ExtractionResult(
            fields=tool_input,
            self_reported_confidence=confidence,
            extraction_failed=failed,
            extraction_failure_reason=failure_reason,
            model=response.model,
            prompt_hash=prompt.body_hash,
            schema_hash=prompt.schema_hash,
            usage=usage,
        )

    @_retry_decorator
    def extract_line_items(
        self,
        *,
        invoice_text: str,
        model: str,
        prompt_name: str = "extraction_line_items_v1",
    ) -> LineItemsResult:
        """Extract every line item via tool-use. Day-3.

        Same prompt-cache + tenacity-retry shape as extract_header. Returns
        a LineItemsResult; service-layer converts the raw dicts to LineItem.
        """
        prompt: LoadedPrompt = load(prompt_name)
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
            "llm.extract_line_items.start",
            model=model,
            prompt_hash=prompt.body_hash,
            input_chars=len(invoice_text),
        )

        response = self._client.messages.create(
            model=model,
            max_tokens=_HEADER_MAX_TOKENS,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": invoice_text}],
        )

        tool_input: dict[str, Any] | None = None
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool["name"]:
                tool_input = dict(block.input)
                break

        if tool_input is None:
            raise RuntimeError(f"LLM did not emit the {tool['name']} tool call")

        items = list(tool_input.get("items") or [])
        usage_obj = getattr(response, "usage", None)
        usage = {
            "input_tokens": getattr(usage_obj, "input_tokens", 0),
            "output_tokens": getattr(usage_obj, "output_tokens", 0),
            "cache_creation_input_tokens": getattr(usage_obj, "cache_creation_input_tokens", 0),
            "cache_read_input_tokens": getattr(usage_obj, "cache_read_input_tokens", 0),
        }

        log.info(
            "llm.extract_line_items.done",
            model=model,
            prompt_hash=prompt.body_hash,
            n_items=len(items),
            usage=usage,
        )

        return LineItemsResult(
            items=items,
            model=response.model,
            prompt_hash=prompt.body_hash,
            schema_hash=prompt.schema_hash,
            usage=usage,
        )

    @_retry_decorator
    def extract_tax_breakdown(
        self,
        *,
        invoice_text: str,
        model: str,
        prompt_name: str = "extraction_tax_breakdown_v1",
    ) -> TaxBreakdownResult:
        """Extract per-jurisdiction tax rows via tool-use. Day-4.

        Same prompt-cache + tenacity-retry shape as extract_header /
        extract_line_items. Service-layer wraps the raw dicts into
        domain.TaxBreakdownLine before persisting.
        """
        prompt: LoadedPrompt = load(prompt_name)
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
            "llm.extract_tax_breakdown.start",
            model=model,
            prompt_hash=prompt.body_hash,
            input_chars=len(invoice_text),
        )

        response = self._client.messages.create(
            model=model,
            max_tokens=_HEADER_MAX_TOKENS,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": invoice_text}],
        )

        tool_input: dict[str, Any] | None = None
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool["name"]:
                tool_input = dict(block.input)
                break

        if tool_input is None:
            raise RuntimeError(f"LLM did not emit the {tool['name']} tool call")

        rows = list(tool_input.get("rows") or [])
        usage_obj = getattr(response, "usage", None)
        usage = {
            "input_tokens": getattr(usage_obj, "input_tokens", 0),
            "output_tokens": getattr(usage_obj, "output_tokens", 0),
            "cache_creation_input_tokens": getattr(usage_obj, "cache_creation_input_tokens", 0),
            "cache_read_input_tokens": getattr(usage_obj, "cache_read_input_tokens", 0),
        }

        log.info(
            "llm.extract_tax_breakdown.done",
            model=model,
            prompt_hash=prompt.body_hash,
            n_rows=len(rows),
            usage=usage,
        )

        return TaxBreakdownResult(
            rows=rows,
            model=response.model,
            prompt_hash=prompt.body_hash,
            schema_hash=prompt.schema_hash,
            usage=usage,
        )

    @_retry_decorator
    def extract_structured_query(
        self,
        *,
        natural_language: str,
        model: str,
        prompt_name: str = "nl_to_structured_query_v1",
    ) -> StructuredQueryResult:
        """Translate NL to a StructuredQuery payload via tool-use.

        Returns the raw tool input dict. The translator service validates it
        against the Pydantic StructuredQuery model (FIELD_OP_COMPATIBILITY,
        sortable-field set, value-type compatibility) before any SQL builder
        sees it — malformed LLM output is rejected here per ADR-0004.
        """
        prompt: LoadedPrompt = load(prompt_name)
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
            "llm.translate_nl.start",
            model=model,
            prompt_hash=prompt.body_hash,
            input_chars=len(natural_language),
        )

        response = self._client.messages.create(
            model=model,
            max_tokens=_HEADER_MAX_TOKENS,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": natural_language}],
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
            "llm.translate_nl.done",
            model=model,
            n_filters=len(tool_input.get("filters") or []),
            usage=usage,
        )

        return StructuredQueryResult(
            payload=tool_input,
            model=response.model,
            prompt_hash=prompt.body_hash,
            schema_hash=prompt.schema_hash,
            usage=usage,
        )

    @_retry_decorator
    def extract_header_vision(
        self,
        *,
        page_pngs: list[bytes],
        model: str,
        prompt_name: str = "extraction_header_vision_v1",
    ) -> ExtractionResult:
        """Vision tool-use for scanned PDFs. Each PNG → base64 image block."""
        prompt = load(prompt_name)
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
        user_content: list[dict[str, Any]] = []
        for png in page_pngs:
            user_content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.b64encode(png).decode(),
                    },
                }
            )
        user_content.append({"type": "text", "text": "Extract the header fields."})

        log.info(
            "llm.extract_header_vision.start",
            model=model,
            prompt_hash=prompt.body_hash,
            n_pages=len(page_pngs),
        )

        response = self._client.messages.create(
            model=model,
            max_tokens=_HEADER_MAX_TOKENS,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": user_content}],
        )

        tool_input = None
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool["name"]:
                tool_input = dict(block.input)  # detach from SDK before mutation
                break
        if tool_input is None:
            raise RuntimeError(f"LLM did not emit the {tool['name']} tool call")

        failed = bool(tool_input.pop("extraction_failed", False))
        failure_reason = tool_input.pop("extraction_failure_reason", None)
        usage_obj = getattr(response, "usage", None)
        usage = {
            "input_tokens": getattr(usage_obj, "input_tokens", 0),
            "output_tokens": getattr(usage_obj, "output_tokens", 0),
            "cache_creation_input_tokens": getattr(usage_obj, "cache_creation_input_tokens", 0),
            "cache_read_input_tokens": getattr(usage_obj, "cache_read_input_tokens", 0),
        }

        # Confidence dict is per-field on this path — pull it from each field.
        self_conf = {
            k: float(v.get("confidence", 0.0)) for k, v in tool_input.items() if isinstance(v, dict)
        }

        return ExtractionResult(
            fields=tool_input,
            self_reported_confidence=self_conf,
            extraction_failed=failed,
            extraction_failure_reason=failure_reason,
            model=response.model,
            prompt_hash=prompt.body_hash,
            schema_hash=prompt.schema_hash,
            usage=usage,
        )


# ---------- Stub implementation (offline / demo) -----------------------------


_SEED_VENDOR_RE = re.compile(r"\[seed-vendor:([^\]]+)\]")
_SEED_TOTAL_RE = re.compile(r"\[seed-total:([\d.]+)\]")
_SEED_NUMBER_RE = re.compile(r"\[seed-number:([^\]]+)\]")


class StubLLMClient:
    """Deterministic offline LLM stub.

    Default provider for local dev / interview review — produces realistic
    ExtractionResults without any network or API key. Scenarios are chosen
    by keyword in the invoice text; the cascade flow is exercised because
    haiku and sonnet return slightly different `total` values, triggering
    the agreement-score override path in extraction_service._run_cascade.

    Override scenarios by including a keyword in the source document:
      "halcyon"   → big-spend invoice (drives anomaly demo with vendor history)
      "bramble"   → near-duplicate-friendly fixture
      "[stub:fail]" or "encrypted" → extraction_failed=True
      default     → Vega Logistics, ~$1180, math reconciles on tier-2+

    Seed markers (used by scripts/seed_demo.py to populate the demo inbox):
      [seed-vendor:Name] → force vendor_name
      [seed-total:N]     → force total to N (subtotal/tax derived 85/15)
      [seed-number:X]    → force invoice_number to X
    """

    # Scenarios keyed by the substring that appears in the invoice text (or
    # in the fake "vision" placeholder text we synthesize from page count).
    _SCENARIOS: ClassVar[dict[str, dict[str, Any]]] = {
        "halcyon": {
            "vendor_name": "Halcyon Software",
            "invoice_number_prefix": "HAL-2026-",
            "subtotal": 28_900.00,
            "tax": 5_162.50,
            "total_tier1": 34_063.50,  # off by $1 vs tier-2
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
            "total_tier1": 751.00,  # off by $1
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
            "total_tier1": 1_181.00,  # off by $1 → triggers cascade
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

    def extract_header(
        self,
        *,
        invoice_text: str,
        model: str,
        prompt_name: str = "extraction_header_v1",
    ) -> ExtractionResult:
        if self._is_failure_trigger(invoice_text):
            return self._failure_result(model=model, vision=False)
        scenario = self._pick_scenario(invoice_text)
        seed = self._seed_from(invoice_text)
        fields = self._build_fields(scenario, model=model, seed=seed)
        _apply_seed_overrides(fields, invoice_text, model=model)
        confidence = {k: 0.95 for k in fields}
        log.info(
            "llm.extract_header.stub",
            model=model,
            scenario=scenario["vendor_name"],
        )
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

    def extract_header_vision(
        self,
        *,
        page_pngs: list[bytes],
        model: str,
        prompt_name: str = "extraction_header_vision_v1",
    ) -> ExtractionResult:
        # Use the PNG bytes as the seed so different scans → different invoice numbers.
        seed_text = hashlib.sha256(b"".join(page_pngs)).hexdigest()
        scenario = self._SCENARIOS["default"]  # vision path: always default scenario
        seed = self._seed_from(seed_text)
        flat = self._build_fields(scenario, model=model, seed=seed)
        # Seed markers don't apply to the vision path — PNGs don't carry text.
        # Seed-mode invoices use the digital path so the markers above suffice.
        # Vision returns per-field {value, bbox, page, confidence} shapes.
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
        log.info("llm.extract_header_vision.stub", model=model, n_pages=len(page_pngs))
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

    def extract_line_items(
        self,
        *,
        invoice_text: str,
        model: str,
        prompt_name: str = "extraction_line_items_v1",
    ) -> LineItemsResult:
        """Return canned line items for the matched scenario.

        Failure-mode keyword still returns an empty list (the failure surface
        is owned by extract_header — line items just go quiet on failure).
        """
        if self._is_failure_trigger(invoice_text):
            return LineItemsResult(
                items=[],
                model=model,
                prompt_hash="stub-line-items-v1",
                schema_hash="stub-line-items-v1",
                usage=_stub_usage(),
            )
        scenario = self._pick_scenario(invoice_text)
        items_template = scenario.get("line_items", [])
        items = [{**item, "confidence": 0.92, "page": 0} for item in items_template]
        log.info(
            "llm.extract_line_items.stub",
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

    def extract_tax_breakdown(
        self,
        *,
        invoice_text: str,
        model: str,
        prompt_name: str = "extraction_tax_breakdown_v1",
    ) -> TaxBreakdownResult:
        """Return canned per-jurisdiction tax rows for the matched scenario.

        Failure-mode keyword returns an empty list. Header-extraction owns
        the document-level failure surface.
        """
        if self._is_failure_trigger(invoice_text):
            return TaxBreakdownResult(
                rows=[],
                model=model,
                prompt_hash="stub-tax-breakdown-v1",
                schema_hash="stub-tax-breakdown-v1",
                usage=_stub_usage(),
            )
        scenario = self._pick_scenario(invoice_text)
        rows_template = scenario.get("tax_breakdown", [])
        rows = [{**row, "confidence": 0.94, "page": 0} for row in rows_template]
        log.info(
            "llm.extract_tax_breakdown.stub",
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

    def extract_structured_query(
        self,
        *,
        natural_language: str,
        model: str,
        prompt_name: str = "nl_to_structured_query_v1",
    ) -> StructuredQueryResult:
        """Deterministic NL translation for the demo path.

        Regex-keyed translation hits every demo phrasing without burning
        tokens. The downstream service still validates the payload against
        the Pydantic StructuredQuery model — same code path as the real
        Anthropic provider — so behaviour matches.
        """
        payload = _stub_translate_nl(natural_language)
        log.info(
            "llm.translate_nl.stub",
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

    # ---- helpers ----

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
        # Tier-1 (haiku) returns a total that's off by $1 vs tier-2+. The
        # cascade then triggers (math doesn't reconcile), sonnet/opus return
        # the correct total, agreement_score moves the disputed field to 0.3,
        # and the demo gets a real cascade trace + agreement-override.
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
        # Tier-1 keeps the cascade-triggering $1 disagreement.
        is_tier_1 = "haiku" in model.lower()
        fields["total"] = base + 1.0 if is_tier_1 else base
        # Split 85/15 so subtotal+tax reconciles to the tier-2 base value.
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


def _stub_translate_nl(natural_language: str) -> dict[str, Any]:
    """Deterministic NL → StructuredQuery payload, used by the stub provider.

    Intentionally narrow: it covers the demo phrasings we control with seed
    data, plus a couple of obvious fallbacks. Anything it can't translate
    flows to `untranslated_intent` so the UI can show the amber notice.
    """
    text = natural_language.strip()
    lowered = text.lower()
    filters: list[dict[str, Any]] = []
    handled_spans: list[tuple[int, int]] = []

    def _mark(match: re.Match[str]) -> None:
        handled_spans.append((match.start(), match.end()))

    def _mark_words(*patterns: str) -> bool:
        """Find any of `patterns` as full words (regex \\b boundaries). Returns
        True if at least one matched. Marks the matched span so it doesn't
        leak into untranslated_intent. Each pattern is treated as a literal
        substring, but consecutive word characters around the match are also
        consumed (so 'anomal' eats 'anomalies' / 'anomaly')."""
        hit = False
        for kw in patterns:
            for m in re.finditer(rf"\b\w*{re.escape(kw)}\w*\b", lowered):
                handled_spans.append((m.start(), m.end()))
                hit = True
        return hit

    # Triage / review-status synonyms
    if _mark_words("duplicate"):
        filters.append({"field": "triage_state", "op": "eq", "value": "likely_duplicate"})
    if _mark_words("anomal", "flagged"):
        filters.append({"field": "has_anomaly", "op": "eq", "value": True})
    # Multi-word phrases are matched verbatim
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

    # Amount thresholds
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

    # Vendor name
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

    # Build the untranslated_intent from spans not handled
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

    # Filter out trivial stop tokens so we don't surface noise as "untranslated".
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


# ---------- Factory ----------------------------------------------------------


def make_llm_client(settings: Settings) -> LLMClient:
    """Pick the LLMClient impl based on Settings.llm_provider.

    Default is `stub` so a fresh checkout can run the full pipeline with no
    API key. Set `SIFT_LLM_PROVIDER=anthropic` (and `ANTHROPIC_API_KEY=...`)
    for real model calls.
    """
    provider = settings.llm_provider
    if provider == "anthropic":
        return AnthropicLLMClient(api_key=settings.anthropic_api_key)
    if provider == "stub":
        return StubLLMClient()
    raise ValueError(f"Unknown SIFT_LLM_PROVIDER={provider!r}. Expected 'stub' or 'anthropic'.")
