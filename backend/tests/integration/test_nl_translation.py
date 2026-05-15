"""NL→StructuredQuery translator + /api/search/translate endpoint (Day 4).

Two layers:
- service: nl_translation_service.translate(...) validates the LLM payload
  against the StructuredQuery Pydantic model. Malformed payload → TranslationError.
- API: POST /api/search/translate exposes that service; malformed → 422.

Stub-mode regex translator is exercised by service tests; Anthropic provider
plumbing is exercised by integration tests against the mocked Anthropic SDK.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.adapters.llm_client import StructuredQueryResult
from app.domain.nl_schema import StructuredQuery
from app.main import app
from app.services.nl_translation_service import TranslationError, translate

class TestStubTranslator:
    def test_empty_input_returns_empty_query(self) -> None:
        result = translate(natural_language="   ")
        assert isinstance(result, StructuredQuery)
        assert result.filters == []
        assert result.untranslated_intent is None

    def test_duplicates_phrase(self) -> None:
        result = translate(natural_language="show me likely duplicates")
        assert any(
            f.field == "triage_state" and f.value == "likely_duplicate" for f in result.filters
        )

    def test_anomalies_phrase(self) -> None:
        result = translate(natural_language="anomalies this month")
        assert any(f.field == "has_anomaly" and f.value is True for f in result.filters)

        assert result.untranslated_intent is not None

    def test_total_over(self) -> None:
        result = translate(natural_language="invoices over $5,000")
        gt = [f for f in result.filters if f.field == "total" and f.op == "gt"]
        assert len(gt) == 1
        assert gt[0].value == 5000.0

    def test_total_under(self) -> None:
        result = translate(natural_language="invoices under $200")
        lt = [f for f in result.filters if f.field == "total" and f.op == "lt"]
        assert len(lt) == 1
        assert lt[0].value == 200.0

    def test_vendor_extraction(self) -> None:
        result = translate(natural_language="from Vega Logistics")
        vendor = [f for f in result.filters if f.field == "vendor_name"]
        assert len(vendor) == 1
        assert "Vega" in str(vendor[0].value)

    def test_combined_intents(self) -> None:
        result = translate(natural_language="anomalies from Halcyon Software over $10,000")
        fields = {f.field for f in result.filters}
        assert "has_anomaly" in fields
        assert "vendor_name" in fields
        assert "total" in fields

    def test_unprocessable_phrase(self) -> None:
        result = translate(natural_language="encrypted invoices")
        assert any(
            f.field == "review_status" and f.value == "unprocessable" for f in result.filters
        )

class TestTranslationErrorPath:
    def test_invalid_op_on_field_raises_translation_error(self) -> None:
        """If the LLM emits an op that violates FIELD_OP_COMPATIBILITY,
        the service must raise TranslationError — never silently coerce
        and never pass the bad payload to the SQL builder."""
        bad_payload = {
            "filters": [

                {"field": "total", "op": "contains", "value": "anything"},
            ],
            "limit": 50,
            "untranslated_intent": None,
        }

        bad_llm = MagicMock()
        bad_llm.call.return_value = StructuredQueryResult(
            payload=bad_payload,
            model="claude-sonnet-4-6",
            prompt_hash="x",
            schema_hash="x",
            usage={
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        )

        with pytest.raises(TranslationError) as ei:
            translate(natural_language="anything", llm=bad_llm)
        assert "validation" in str(ei.value).lower()
        assert ei.value.raw_payload == bad_payload

    def test_unknown_field_raises_translation_error(self) -> None:
        bad_payload = {
            "filters": [{"field": "this_field_does_not_exist", "op": "eq", "value": 1}],
            "limit": 50,
            "untranslated_intent": None,
        }
        bad_llm = MagicMock()
        bad_llm.call.return_value = StructuredQueryResult(
            payload=bad_payload,
            model="claude-sonnet-4-6",
            prompt_hash="x",
            schema_hash="x",
            usage={
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        )
        with pytest.raises(TranslationError):
            translate(natural_language="anything", llm=bad_llm)

@pytest.fixture
def client() -> TestClient:
    return TestClient(app)

class TestTranslateEndpoint:
    def test_successful_translation(self, client: TestClient) -> None:
        res = client.post("/api/search/translate", json={"query": "duplicates from Vega"})
        assert res.status_code == 200, res.text
        body = res.json()
        assert isinstance(body["filters"], list)
        fields = {f["field"] for f in body["filters"]}
        assert "triage_state" in fields
        assert "vendor_name" in fields

    def test_empty_query_returns_empty_filters(self, client: TestClient) -> None:
        res = client.post("/api/search/translate", json={"query": ""})
        assert res.status_code == 200
        body = res.json()
        assert body["filters"] == []

    def test_malformed_llm_payload_returns_422(self, client: TestClient) -> None:
        bad_payload = {
            "filters": [{"field": "total", "op": "contains", "value": "x"}],
            "limit": 50,
            "untranslated_intent": None,
        }
        bad_llm = MagicMock()
        bad_llm.call.return_value = StructuredQueryResult(
            payload=bad_payload,
            model="claude-sonnet-4-6",
            prompt_hash="x",
            schema_hash="x",
            usage={
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        )
        with patch("app.services.nl_translation_service.make_llm_client", return_value=bad_llm):
            res = client.post("/api/search/translate", json={"query": "anything"})
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "errors" in detail
        assert "raw_payload" in detail
