"""AnthropicLLMClient.extract_line_items + StubLLMClient.extract_line_items.

Mirror of test_llm_client.py for the Day-3 method. Live calls are out of
scope; we mock the Anthropic SDK response and assert the prompt + tool-use
plumbing is correct.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.adapters.llm_client import (
    EXTRACT_LINE_ITEMS,
    AnthropicLLMClient,
    LineItemsResult,
    StubLLMClient,
)

def _fake_response(items: list[dict], model: str = "claude-haiku-4-5") -> MagicMock:
    response = MagicMock()
    block = MagicMock()
    block.type = "tool_use"
    block.name = "extract_invoice_line_items"
    block.input = {"items": items}
    response.content = [block]
    response.usage = MagicMock(
        input_tokens=400,
        output_tokens=120,
        cache_creation_input_tokens=300,
        cache_read_input_tokens=0,
    )
    response.model = model
    return response

class TestAnthropicExtractLineItems:
    def test_happy_path_returns_items(self) -> None:
        canned = [
            {
                "description": "Last-mile delivery",
                "quantity": 12,
                "unit_price": 65.0,
                "line_total": 780.0,
                "confidence": 0.95,
            },
            {
                "description": "Pallet handling",
                "quantity": 4,
                "unit_price": 35.0,
                "line_total": 140.0,
                "confidence": 0.93,
            },
        ]
        client_mock = MagicMock()
        client_mock.messages.create.return_value = _fake_response(canned)
        with patch("app.adapters.llm_client.Anthropic", return_value=client_mock):
            client = AnthropicLLMClient(api_key="test")
            result = client.call(EXTRACT_LINE_ITEMS, model="claude-haiku-4-5", text="any")
        assert isinstance(result, LineItemsResult)
        assert len(result.items) == 2
        assert result.items[0]["description"] == "Last-mile delivery"
        assert result.items[1]["line_total"] == 140.0
        assert result.model == "claude-haiku-4-5"

    def test_prompt_caching_on_system_block(self) -> None:
        client_mock = MagicMock()
        client_mock.messages.create.return_value = _fake_response([])
        with patch("app.adapters.llm_client.Anthropic", return_value=client_mock):
            AnthropicLLMClient(api_key="test").call(
                EXTRACT_LINE_ITEMS, model="claude-haiku-4-5", text="x"
            )
        kwargs = client_mock.messages.create.call_args.kwargs
        system = kwargs["system"]
        assert isinstance(system, list)
        assert any(b.get("cache_control") == {"type": "ephemeral"} for b in system)

    def test_empty_items_array_handled(self) -> None:
        client_mock = MagicMock()
        client_mock.messages.create.return_value = _fake_response([])
        with patch("app.adapters.llm_client.Anthropic", return_value=client_mock):
            client = AnthropicLLMClient(api_key="test")
            result = client.call(EXTRACT_LINE_ITEMS, model="claude-haiku-4-5", text="flat fee")
        assert result.items == []

    def test_missing_tool_use_raises(self) -> None:
        bad_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        bad_response.content = [text_block]
        bad_response.usage = MagicMock(
            input_tokens=10,
            output_tokens=5,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )
        bad_response.model = "claude-haiku-4-5"
        client_mock = MagicMock()
        client_mock.messages.create.return_value = bad_response
        with patch("app.adapters.llm_client.Anthropic", return_value=client_mock):
            client = AnthropicLLMClient(api_key="test")
            import pytest

            with pytest.raises(RuntimeError, match="tool call"):
                client.call(EXTRACT_LINE_ITEMS, model="claude-haiku-4-5", text="x")

class TestStubExtractLineItems:
    def test_default_scenario_returns_vega_freight(self) -> None:
        result = StubLLMClient().call(
            EXTRACT_LINE_ITEMS, model="claude-haiku-4-5", text="anything"
        )
        assert isinstance(result, LineItemsResult)

        assert len(result.items) == 3
        descs = [i["description"] for i in result.items]
        assert any("Last-Mile Delivery" in d for d in descs)

    def test_halcyon_scenario(self) -> None:
        result = StubLLMClient().call(
            EXTRACT_LINE_ITEMS, model="claude-sonnet-4-6", text="Halcyon Software services 2026"
        )
        assert len(result.items) == 2
        assert "Annual Platform License" in result.items[0]["description"]

    def test_bramble_scenario(self) -> None:
        result = StubLLMClient().call(
            EXTRACT_LINE_ITEMS, model="claude-sonnet-4-6", text="Bramble Catering event 2026"
        )
        assert len(result.items) == 5

        total = sum(i["line_total"] for i in result.items)
        assert abs(total - 635.59) < 0.05

    def test_failure_keyword_returns_empty(self) -> None:
        result = StubLLMClient().call(
            EXTRACT_LINE_ITEMS, model="claude-haiku-4-5", text="[stub:fail] no items"
        )
        assert result.items == []

    def test_each_item_has_confidence_and_page(self) -> None:
        result = StubLLMClient().call(
            EXTRACT_LINE_ITEMS, model="claude-haiku-4-5", text="freight"
        )
        for item in result.items:
            assert "confidence" in item
            assert "page" in item
            assert "description" in item
            assert "line_total" in item
