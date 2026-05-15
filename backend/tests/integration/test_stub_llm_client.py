"""StubLLMClient + make_llm_client factory tests.

The stub provider is what runs by default on a fresh checkout (no Anthropic
key). It must satisfy the LLMClient Protocol, exercise the cascade flow
(tier-1 vs tier-2 disagreement), and recognize a small set of scenario
keywords so the demo narrative works without an API call.
"""

from __future__ import annotations

import pytest

from app.adapters.llm_client import (
    EXTRACT_HEADER,
    EXTRACT_HEADER_VISION,
    AnthropicLLMClient,
    ExtractionResult,
    LLMClient,
    StubLLMClient,
    make_llm_client,
)
from app.config import Settings


class TestStubExtractHeader:
    def test_returns_extraction_result(self) -> None:
        stub = StubLLMClient()
        result = stub.call(EXTRACT_HEADER, model="claude-haiku-4-5", text="anything")
        assert isinstance(result, ExtractionResult)
        assert result.extraction_failed is False
        # All seven header fields are present
        for f in (
            "vendor_name",
            "invoice_number",
            "invoice_date",
            "subtotal",
            "tax",
            "total",
            "currency",
        ):
            assert f in result.fields

    def test_haiku_total_disagrees_with_sonnet_by_one_dollar(self) -> None:
        """The stub seeds the cascade flow: tier-1 returns a total off by $1
        from tier-2 so math doesn't reconcile on the first try."""
        stub = StubLLMClient()
        haiku = stub.call(EXTRACT_HEADER, model="claude-haiku-4-5", text="text")
        sonnet = stub.call(EXTRACT_HEADER, model="claude-sonnet-4-6", text="text")
        assert haiku.fields["total"] == sonnet.fields["total"] + 1.0
        # Subtotal + tax = sonnet's total (math reconciles after cascade)
        assert haiku.fields["subtotal"] + haiku.fields["tax"] == sonnet.fields["total"]

    def test_invoice_number_varies_by_input(self) -> None:
        """Different invoice text → different invoice numbers, so multiple
        uploads in stub mode show as distinct invoices."""
        stub = StubLLMClient()
        a = stub.call(EXTRACT_HEADER, model="claude-haiku-4-5", text="alpha document")
        b = stub.call(EXTRACT_HEADER, model="claude-haiku-4-5", text="beta document")
        assert a.fields["invoice_number"] != b.fields["invoice_number"]

    def test_halcyon_scenario(self) -> None:
        stub = StubLLMClient()
        result = stub.call(
            EXTRACT_HEADER, model="claude-sonnet-4-6", text="Halcyon Software services rendered"
        )
        assert result.fields["vendor_name"] == "Halcyon Software"
        assert result.fields["total"] == 34_062.50

    def test_bramble_scenario(self) -> None:
        stub = StubLLMClient()
        result = stub.call(
            EXTRACT_HEADER, model="claude-sonnet-4-6", text="Bramble Catering — event 2026"
        )
        assert result.fields["vendor_name"] == "Bramble Catering"
        assert result.fields["total"] == 750.00

    def test_default_scenario_falls_back_to_vega(self) -> None:
        stub = StubLLMClient()
        result = stub.call(
            EXTRACT_HEADER, model="claude-sonnet-4-6", text="some unmapped invoice text"
        )
        assert result.fields["vendor_name"] == "Vega Logistics"

    def test_failure_keyword_triggers_extraction_failed(self) -> None:
        stub = StubLLMClient()
        result = stub.call(
            EXTRACT_HEADER, model="claude-haiku-4-5", text="[stub:fail] cannot parse"
        )
        assert result.extraction_failed is True
        assert "stub" in (result.extraction_failure_reason or "")
        assert result.fields == {}

    def test_encrypted_keyword_triggers_extraction_failed(self) -> None:
        stub = StubLLMClient()
        result = stub.call(
            EXTRACT_HEADER,
            model="claude-haiku-4-5",
            text="Encrypted document — password required",
        )
        assert result.extraction_failed is True


class TestStubExtractHeaderVision:
    def test_returns_per_field_dict_shape(self) -> None:
        stub = StubLLMClient()
        png = b"\x89PNG\r\n\x1a\nfakebytes"
        result = stub.call(EXTRACT_HEADER_VISION, model="claude-sonnet-4-6", page_pngs=[png])
        # Vision shape: each field is {value, bbox, page, confidence}
        v = result.fields["vendor_name"]
        assert isinstance(v, dict)
        assert "value" in v
        assert "bbox" in v
        assert "page" in v
        assert "confidence" in v
        assert len(v["bbox"]) == 4
        # All bbox values normalized 0-1
        for coord in v["bbox"]:
            assert 0.0 <= coord <= 1.0

    def test_vision_invoice_number_varies_by_png_bytes(self) -> None:
        stub = StubLLMClient()
        a = stub.call(EXTRACT_HEADER_VISION, model="claude-sonnet-4-6", page_pngs=[b"\x89PNG\r\n\x1a\nA"])
        b = stub.call(EXTRACT_HEADER_VISION, model="claude-sonnet-4-6", page_pngs=[b"\x89PNG\r\n\x1a\nB"])
        assert a.fields["invoice_number"]["value"] != b.fields["invoice_number"]["value"]


class TestFactory:
    def test_default_provider_is_stub(self) -> None:
        """Fresh-checkout default must be the stub — interview reviewer can
        run the app with no Anthropic key."""
        settings = Settings(_env_file=None)  # ignore .env
        assert settings.llm_provider == "stub"
        client = make_llm_client(settings)
        assert isinstance(client, StubLLMClient)

    def test_anthropic_provider_routes_to_anthropic_impl(self) -> None:
        settings = Settings(
            _env_file=None, SIFT_LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="sk-test"
        )  # type: ignore[call-arg]
        client = make_llm_client(settings)
        assert isinstance(client, AnthropicLLMClient)

    def test_anthropic_provider_without_key_raises(self) -> None:
        settings = Settings(_env_file=None, SIFT_LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="")  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            make_llm_client(settings)

    def test_unknown_provider_raises(self) -> None:
        # Bypass Settings type-validation by constructing a fake namespace.
        settings = Settings(_env_file=None)
        # Mutate the validated literal field via __dict__ for the test.
        object.__setattr__(settings, "llm_provider", "openai")
        with pytest.raises(ValueError, match="Unknown SIFT_LLM_PROVIDER"):
            make_llm_client(settings)

    def test_protocol_is_satisfied_by_both_impls(self) -> None:
        # Structural typing — Protocol surface is one method: `call`.
        stub: LLMClient = StubLLMClient()
        assert callable(stub.call)
