"""LLM client adapter — tests with Anthropic SDK mocked.

Live LLM calls are run by the eval harness, not the unit/integration suite.
This test verifies:
- Tool-use is correctly assembled from the versioned prompt + schema
- Prompt caching is enabled on the system block
- The extracted fields are returned cleanly
- Retry fires on transient errors per ADR-0006
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.adapters.llm_client import ExtractionResult, LLMClient


@pytest.fixture
def fake_tool_response() -> dict:
    return {
        "vendor_name": "Vega Logistics",
        "invoice_number": "INV-2026-0042",
        "invoice_date": "2026-05-13",
        "subtotal": 1000.0,
        "tax": 180.0,
        "total": 1180.0,
        "currency": "USD",
        "confidence": {
            "vendor_name": 0.95,
            "invoice_number": 0.99,
            "invoice_date": 0.98,
            "subtotal": 0.99,
            "tax": 0.99,
            "total": 0.99,
            "currency": 0.95,
        },
        "extraction_failed": False,
    }


def _make_messages_mock(tool_input: dict) -> MagicMock:
    """Build a MagicMock that mimics anthropic.Anthropic().messages.create."""
    response = MagicMock()
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.name = "extract_invoice_header"
    tool_use_block.input = tool_input
    response.content = [tool_use_block]
    response.usage = MagicMock(
        input_tokens=500,
        output_tokens=80,
        cache_creation_input_tokens=400,
        cache_read_input_tokens=0,
    )
    response.stop_reason = "tool_use"
    response.model = "claude-haiku-4-5"
    return response


class TestLLMClientExtractHeader:
    def test_extract_header_happy_path(self, fake_tool_response: dict) -> None:
        client_mock = MagicMock()
        client_mock.messages.create.return_value = _make_messages_mock(fake_tool_response)

        with patch("app.adapters.llm_client.Anthropic", return_value=client_mock):
            client = LLMClient(api_key="test")
            result = client.extract_header(invoice_text="any text", model="claude-haiku-4-5")

        assert isinstance(result, ExtractionResult)
        assert result.fields["vendor_name"] == "Vega Logistics"
        assert result.fields["total"] == 1180.0
        assert result.self_reported_confidence["total"] == 0.99
        assert result.model == "claude-haiku-4-5"
        assert result.prompt_hash != ""

    def test_prompt_caching_on_system_block(self, fake_tool_response: dict) -> None:
        client_mock = MagicMock()
        client_mock.messages.create.return_value = _make_messages_mock(fake_tool_response)

        with patch("app.adapters.llm_client.Anthropic", return_value=client_mock):
            client = LLMClient(api_key="test")
            client.extract_header(invoice_text="text", model="claude-haiku-4-5")

        kwargs = client_mock.messages.create.call_args.kwargs
        system = kwargs["system"]
        # System is a list of blocks; the cached block has cache_control.
        assert isinstance(system, list)
        assert any(b.get("cache_control") == {"type": "ephemeral"} for b in system)

    def test_retry_on_transient_error(self, fake_tool_response: dict) -> None:
        from anthropic import APITimeoutError

        client_mock = MagicMock()
        client_mock.messages.create.side_effect = [
            APITimeoutError(request=MagicMock()),
            _make_messages_mock(fake_tool_response),
        ]

        with patch("app.adapters.llm_client.Anthropic", return_value=client_mock):
            client = LLMClient(api_key="test")
            result = client.extract_header(invoice_text="text", model="claude-haiku-4-5")

        assert result.fields["vendor_name"] == "Vega Logistics"
        assert client_mock.messages.create.call_count == 2

    def test_does_not_retry_non_transient_error(self) -> None:
        """4xx errors are deterministic — must not retry per ADR-0006."""
        from anthropic import APIStatusError

        fake_response = MagicMock(status_code=401)
        client_mock = MagicMock()
        client_mock.messages.create.side_effect = APIStatusError(
            message="unauthorized", response=fake_response, body={"error": "x"}
        )

        with patch("app.adapters.llm_client.Anthropic", return_value=client_mock):
            client = LLMClient(api_key="test")
            with pytest.raises(APIStatusError):
                client.extract_header(invoice_text="text", model="claude-haiku-4-5")

        # Exactly one call — no retry on 4xx.
        assert client_mock.messages.create.call_count == 1

    def test_retry_exhausted_propagates_final_error(self) -> None:
        """When all 3 attempts fail with transient errors, the final one is re-raised."""
        from anthropic import APITimeoutError

        client_mock = MagicMock()
        client_mock.messages.create.side_effect = [
            APITimeoutError(request=MagicMock()),
            APITimeoutError(request=MagicMock()),
            APITimeoutError(request=MagicMock()),
        ]

        with patch("app.adapters.llm_client.Anthropic", return_value=client_mock):
            client = LLMClient(api_key="test")
            with pytest.raises(APITimeoutError):
                client.extract_header(invoice_text="text", model="claude-haiku-4-5")

        assert client_mock.messages.create.call_count == 3

    def test_missing_tool_use_block_raises(self) -> None:
        """If the model responds without the forced tool call, raise RuntimeError."""
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
            client = LLMClient(api_key="test")
            with pytest.raises(RuntimeError, match="tool call"):
                client.extract_header(invoice_text="text", model="claude-haiku-4-5")
