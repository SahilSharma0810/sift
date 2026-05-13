"""Anthropic SDK wrapper per ADR-0005.

One method per use case — never a generic call_claude. Prompt + tool-use
schema come from app.prompts (versioned, content-hashed). Adapter-layer
auto-retry on transient errors per ADR-0006.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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

from app.prompts import LoadedPrompt, load

log = structlog.get_logger(__name__)

# Header extraction fits comfortably under 1024 tokens. When extract_line_items
# lands, lift this per-method (line items can be 500-1000 tokens by themselves).
_HEADER_MAX_TOKENS = 1024


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


class LLMClient:
    """Adapter for Anthropic SDK. Imported only from services."""

    def __init__(self, api_key: str) -> None:
        self._client = Anthropic(api_key=api_key)

    @_retry_decorator
    def extract_header(
        self,
        *,
        invoice_text: str,
        model: str,
        prompt_name: str = "extraction_header_v1",
    ) -> ExtractionResult:
        """Extract header fields via tool-use. Prompt-cached system block.

        Per ADR-0006: tenacity retries on transient errors (timeout, 429, 5xx)
        — up to 3 attempts, exponential backoff.
        """
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
