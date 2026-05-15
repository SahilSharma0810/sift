"""Search service + /api/search endpoint (Day 4).

Exercises every supported (field, op) combination per ADR-0004 + the FTS
path via raw_text_tsv. Uses the api_client fixture so writes roll back.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.adapters.llm_client import ExtractionResult
from tests.conftest import patch_make_llm_client

FIXTURES = Path(__file__).parents[1] / "fixtures"
CLEAN_PDF = FIXTURES / "digital_invoice_clean.pdf"

def _llm_result(vendor: str, number: str, total: float, currency: str = "USD") -> ExtractionResult:
    return ExtractionResult(
        fields={
            "vendor_name": vendor,
            "invoice_number": number,
            "invoice_date": "2026-05-13",
            "subtotal": round(total * 0.85, 2),
            "tax": round(total - total * 0.85, 2),
            "total": total,
            "currency": currency,
        },
        self_reported_confidence={"total": 0.99},
        extraction_failed=False,
        extraction_failure_reason=None,
        model="claude-haiku-4-5",
        prompt_hash="h",
        schema_hash="h",
        usage={
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    )

def _upload(
    client: TestClient, marker: str, vendor: str, total: float, currency: str = "USD"
) -> str:
    body = CLEAN_PDF.read_bytes() + f"\n%{marker}\n".encode()
    with patch_make_llm_client(header=_llm_result(vendor, f"INV-{marker}", total, currency)):
        res = client.post(
            "/api/invoices",
            files={"file": (f"{marker}.pdf", body, "application/pdf")},
        )
    assert res.status_code == 201, res.text
    return res.json()["id"]

class TestSearchByVendor:
    def test_vendor_eq(self, api_client: TestClient) -> None:
        _upload(api_client, "vega-1", "QA SearchVendor Vega Logistics", 1180.0)
        _upload(api_client, "halcyon-1", "QA SearchVendor Halcyon Software", 34062.50)

        res = api_client.post(
            "/api/search",
            json={
                "filters": [
                    {"field": "vendor_name", "op": "eq", "value": "QA SearchVendor Vega Logistics"}
                ],
                "limit": 50,
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert len(body) == 1
        assert (
            body[0]["current_extraction"]["extracted_fields"]["vendor_name"]["value"]
            == "QA SearchVendor Vega Logistics"
        )

class TestSearchByTotal:
    def test_total_gt(self, api_client: TestClient) -> None:
        _upload(api_client, "low", "QA SearchVendor Vega Logistics", 500.0)
        _upload(api_client, "mid", "QA SearchVendor Vega Logistics", 5000.0)
        _upload(api_client, "high", "QA SearchVendor Vega Logistics", 50000.0)

        res = api_client.post(
            "/api/search",
            json={
                "filters": [
                    {"field": "vendor_name", "op": "eq", "value": "QA SearchVendor Vega Logistics"},
                    {"field": "total", "op": "gt", "value": 1000},
                ],
                "limit": 50,
            },
        )
        assert res.status_code == 200
        body = res.json()
        totals = sorted(
            float(b["current_extraction"]["extracted_fields"]["total"]["value"]) for b in body
        )
        assert totals == [5000.0, 50000.0]

    def test_total_between(self, api_client: TestClient) -> None:
        _upload(api_client, "low", "QA SearchVendor Vega Logistics", 500.0)
        _upload(api_client, "mid", "QA SearchVendor Vega Logistics", 5000.0)
        _upload(api_client, "high", "QA SearchVendor Vega Logistics", 50000.0)

        res = api_client.post(
            "/api/search",
            json={
                "filters": [
                    {"field": "vendor_name", "op": "eq", "value": "QA SearchVendor Vega Logistics"},
                    {"field": "total", "op": "between", "value": [1000, 10000]},
                ],
                "limit": 50,
            },
        )
        body = res.json()
        assert len(body) == 1
        assert float(body[0]["current_extraction"]["extracted_fields"]["total"]["value"]) == 5000.0

class TestSearchByTriage:
    def test_likely_duplicate(self, api_client: TestClient) -> None:

        _upload(api_client, "dup-a", "Vendor A", 100.0)
        _upload(api_client, "dup-b", "Vendor B", 100.0)

        res = api_client.post(
            "/api/search",
            json={
                "filters": [{"field": "triage_state", "op": "eq", "value": "likely_duplicate"}],
                "limit": 50,
            },
        )

        body = res.json()
        for inv in body:
            assert inv["current_extraction"]["predicted_triage_state"] == "likely_duplicate"

class TestSearchFTS:
    def test_fts_matches_vendor_name(self, api_client: TestClient) -> None:

        _upload(api_client, "fts-1", "QA SearchVendor VegaToken", 1180.0)
        _upload(api_client, "fts-2", "QA SearchVendor HalcyonToken", 34062.50)

        res = api_client.post(
            "/api/search",
            json={
                "filters": [{"field": "raw_text", "op": "fts_matches", "value": "halcyontoken"}],
                "limit": 50,
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert len(body) == 1
        assert (
            body[0]["current_extraction"]["extracted_fields"]["vendor_name"]["value"]
            == "QA SearchVendor HalcyonToken"
        )

    def test_fts_contains_substring(self, api_client: TestClient) -> None:
        """`contains` falls back to ILIKE for substring matching."""

        _upload(api_client, "fts-c-1", "QA SearchFTS UniqXyzpdq", 100.0)
        _upload(api_client, "fts-c-2", "QA SearchFTS OtherLmnopq", 100.0)

        res = api_client.post(
            "/api/search",
            json={
                "filters": [{"field": "raw_text", "op": "contains", "value": "UniqXyz"}],
                "limit": 50,
            },
        )
        body = res.json()
        assert len(body) == 1
        assert (
            body[0]["current_extraction"]["extracted_fields"]["vendor_name"]["value"]
            == "QA SearchFTS UniqXyzpdq"
        )

class TestSearchMalformedQuery:
    def test_missing_field_in_clause_422(self, api_client: TestClient) -> None:
        """Body validation by FastAPI/Pydantic — missing required field
        on a FilterClause yields 422 before the search service sees it."""
        res = api_client.post(
            "/api/search",
            json={
                "filters": [{"op": "eq", "value": "x"}],
                "limit": 50,
            },
        )
        assert res.status_code == 422

    def test_disallowed_op_on_field_422(self, api_client: TestClient) -> None:
        """FIELD_OP_COMPATIBILITY is enforced in nl_schema.FilterClause."""
        res = api_client.post(
            "/api/search",
            json={
                "filters": [{"field": "total", "op": "contains", "value": "x"}],
                "limit": 50,
            },
        )
        assert res.status_code == 422

class TestSearchExport:
    def test_csv_export_includes_audit_header_and_rows(self, api_client: TestClient) -> None:
        _upload(api_client, "exp-csv-1", "QA Export Vega", 1180.0)

        res = api_client.post(
            "/api/search/export?format=csv",
            json={
                "filters": [{"field": "vendor_name", "op": "eq", "value": "QA Export Vega"}],
                "limit": 50,
            },
        )
        assert res.status_code == 200
        text = res.text

        assert text.startswith("# Sift export")
        assert "# Query:" in text

        assert "invoice_id,vendor_name" in text

        assert "QA Export Vega" in text

        assert res.headers["content-disposition"].startswith("attachment;")
        assert res.headers["content-type"].startswith("text/csv")

    def test_json_export_wraps_with_metadata(self, api_client: TestClient) -> None:
        _upload(api_client, "exp-json-1", "QA Export JsonVendor", 250.0)

        res = api_client.post(
            "/api/search/export?format=json",
            json={
                "filters": [{"field": "vendor_name", "op": "eq", "value": "QA Export JsonVendor"}],
                "limit": 50,
            },
        )
        assert res.status_code == 200
        import json as _json

        body = _json.loads(res.text)
        assert body["row_count"] == len(body["rows"]) == 1
        assert body["query"]["filters"][0]["field"] == "vendor_name"
        assert body["rows"][0]["vendor_name"] == "QA Export JsonVendor"

class TestSearchEmptyQuery:
    def test_empty_filters_returns_everything(self, api_client: TestClient) -> None:
        _upload(api_client, "empty-1", "QA SearchVendor Vega Logistics", 100.0)
        _upload(api_client, "empty-2", "QA SearchVendor Halcyon Software", 200.0)

        res = api_client.post("/api/search", json={"filters": [], "limit": 50})
        assert res.status_code == 200
        body = res.json()
        assert len(body) >= 2


class TestAuthGate:
    def test_search_requires_auth(self, unauthed_client) -> None:
        res = unauthed_client.post("/api/search", json={"filters": []})
        assert res.status_code == 401

    def test_translate_requires_auth(self, unauthed_client) -> None:
        res = unauthed_client.post("/api/search/translate", json={"query": "x"})
        assert res.status_code == 401
