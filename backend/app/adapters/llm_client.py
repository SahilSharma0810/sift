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
        },
        "bramble": {
            "vendor_name": "Bramble Catering",
            "invoice_number_prefix": "BR-2026-",
            "subtotal": 635.59,
            "tax": 114.41,
            "total_tier1": 751.00,  # off by $1
            "total_tier2": 750.00,
            "currency": "USD",
        },
        "default": {
            "vendor_name": "Vega Logistics",
            "invoice_number_prefix": "INV-2026-",
            "subtotal": 1_000.00,
            "tax": 180.00,
            "total_tier1": 1_181.00,  # off by $1 → triggers cascade
            "total_tier2": 1_180.00,
            "currency": "USD",
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
