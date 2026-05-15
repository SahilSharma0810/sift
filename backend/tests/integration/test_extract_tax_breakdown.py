"""extract_tax_breakdown on both AnthropicLLMClient + StubLLMClient (Day 4).

Mirrors test_extract_line_items.py — same tool-use plumbing, same
prompt-cache + retry pattern.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.adapters.llm_client import (
    EXTRACT_TAX_BREAKDOWN,
    AnthropicLLMClient,
    StubLLMClient,
    TaxBreakdownResult,
)

def _fake_response(rows: list[dict], model: str = "claude-haiku-4-5") -> MagicMock:
    response = MagicMock()
    block = MagicMock()
    block.type = "tool_use"
    block.name = "extract_invoice_tax_breakdown"
    block.input = {"rows": rows}
    response.content = [block]
    response.usage = MagicMock(
        input_tokens=300,
        output_tokens=80,
        cache_creation_input_tokens=250,
        cache_read_input_tokens=0,
    )
    response.model = model
    return response

class TestAnthropicExtractTaxBreakdown:
    def test_happy_path_returns_rows(self) -> None:
        canned = [
            {"jurisdiction": "CA Sales", "rate": 7.25, "amount": 72.50, "confidence": 0.95},
            {"jurisdiction": "City of SF", "rate": 1.0, "amount": 10.00, "confidence": 0.93},
        ]
        client_mock = MagicMock()
        client_mock.messages.create.return_value = _fake_response(canned)
        with patch("app.adapters.llm_client.Anthropic", return_value=client_mock):
            client = AnthropicLLMClient(api_key="test")
            result = client.call(EXTRACT_TAX_BREAKDOWN, model="claude-haiku-4-5", text="anything")
        assert isinstance(result, TaxBreakdownResult)
        assert len(result.rows) == 2
        assert result.rows[0]["jurisdiction"] == "CA Sales"
        assert result.model == "claude-haiku-4-5"

    def test_prompt_caching_on_system_block(self) -> None:
        client_mock = MagicMock()
        client_mock.messages.create.return_value = _fake_response([])
        with patch("app.adapters.llm_client.Anthropic", return_value=client_mock):
            AnthropicLLMClient(api_key="test").call(
                EXTRACT_TAX_BREAKDOWN, model="claude-haiku-4-5", text="x"
            )
        kwargs = client_mock.messages.create.call_args.kwargs
        system = kwargs["system"]
        assert isinstance(system, list)
        assert any(b.get("cache_control") == {"type": "ephemeral"} for b in system)

    def test_empty_rows_handled(self) -> None:
        client_mock = MagicMock()
        client_mock.messages.create.return_value = _fake_response([])
        with patch("app.adapters.llm_client.Anthropic", return_value=client_mock):
            client = AnthropicLLMClient(api_key="test")
            result = client.call(
                EXTRACT_TAX_BREAKDOWN, model="claude-haiku-4-5", text="single header tax line only"
            )
        assert result.rows == []

    def test_missing_tool_use_raises(self) -> None:
        response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        response.content = [text_block]
        response.usage = MagicMock(
            input_tokens=10,
            output_tokens=5,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )
        response.model = "claude-haiku-4-5"
        client_mock = MagicMock()
        client_mock.messages.create.return_value = response
        with patch("app.adapters.llm_client.Anthropic", return_value=client_mock):
            client = AnthropicLLMClient(api_key="test")
            with pytest.raises(RuntimeError, match="tool call"):
                client.call(EXTRACT_TAX_BREAKDOWN, model="claude-haiku-4-5", text="x")

class TestStubExtractTaxBreakdown:
    def test_default_scenario_returns_vega_two_rows(self) -> None:
        result = StubLLMClient().call(
            EXTRACT_TAX_BREAKDOWN, model="claude-haiku-4-5", text="anything"
        )
        assert isinstance(result, TaxBreakdownResult)
        assert len(result.rows) == 2
        jurisdictions = {r["jurisdiction"] for r in result.rows}
        assert "Federal Excise" in jurisdictions

    def test_halcyon_scenario_three_rows(self) -> None:
        result = StubLLMClient().call(
            EXTRACT_TAX_BREAKDOWN, model="claude-sonnet-4-6", text="Halcyon Software services 2026"
        )
        assert len(result.rows) == 3
        assert any("California" in r["jurisdiction"] for r in result.rows)

    def test_bramble_scenario_single_gst(self) -> None:
        result = StubLLMClient().call(
            EXTRACT_TAX_BREAKDOWN, model="claude-sonnet-4-6", text="Bramble Catering event 2026"
        )
        assert len(result.rows) == 1
        assert result.rows[0]["jurisdiction"] == "GST"

    def test_failure_keyword_returns_empty(self) -> None:
        result = StubLLMClient().call(
            EXTRACT_TAX_BREAKDOWN, model="claude-haiku-4-5", text="[stub:fail] no breakdown"
        )
        assert result.rows == []

    def test_each_row_has_confidence_and_page(self) -> None:
        result = StubLLMClient().call(
            EXTRACT_TAX_BREAKDOWN, model="claude-haiku-4-5", text="freight"
        )
        for row in result.rows:
            assert "confidence" in row
            assert "page" in row
            assert "jurisdiction" in row
            assert "amount" in row
