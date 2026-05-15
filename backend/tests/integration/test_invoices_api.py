"""API integration tests via FastAPI TestClient.

The `api_client` fixture (defined in tests/integration/conftest.py) wraps
every request in a SAVEPOINT so service-layer commits don't pollute the
dev DB. The LLM is patched at the factory site.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.adapters.llm_client import ExtractionResult
from tests.conftest import patch_make_llm_client

FIXTURES = Path(__file__).parents[1] / "fixtures"
CLEAN_PDF = FIXTURES / "digital_invoice_clean.pdf"

def _fake_llm_result() -> ExtractionResult:
    return ExtractionResult(
        fields={
            "vendor_name": "Vega Logistics",
            "invoice_number": "INV-2026-0042",
            "invoice_date": "2026-05-13",
            "subtotal": 1000.0,
            "tax": 180.0,
            "total": 1180.0,
            "currency": "USD",
        },
        self_reported_confidence={"total": 0.99},
        extraction_failed=False,
        extraction_failure_reason=None,
        model="claude-haiku-4-5",
        prompt_hash="hash",
        schema_hash="hash",
        usage={
            "input_tokens": 500,
            "output_tokens": 80,
            "cache_creation_input_tokens": 400,
            "cache_read_input_tokens": 0,
        },
    )

class TestUploadInvoice:
    def test_upload_returns_invoice_with_extraction(self, api_client: TestClient) -> None:
        with (
            patch_make_llm_client(header=_fake_llm_result()),
            CLEAN_PDF.open("rb") as fh,
        ):
            res = api_client.post(
                "/api/invoices",
                files={"file": ("clean.pdf", fh, "application/pdf")},
            )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["review_status"] == "pending"
        assert body["current_extraction"]["predicted_triage_state"] == "confident"
        assert "Vega Logistics" in str(body["current_extraction"]["extracted_fields"])

    def test_upload_rejects_non_pdf(self, api_client: TestClient) -> None:
        res = api_client.post(
            "/api/invoices",
            files={"file": ("oops.txt", b"hello", "text/plain")},
        )
        assert res.status_code == 415

    def test_list_returns_uploaded(self, api_client: TestClient) -> None:
        with (
            patch_make_llm_client(header=_fake_llm_result()),
            CLEAN_PDF.open("rb") as fh,
        ):
            api_client.post(
                "/api/invoices",
                files={"file": ("clean2.pdf", fh, "application/pdf")},
            )
        res = api_client.get("/api/invoices")
        assert res.status_code == 200
        body = res.json()
        assert len(body) >= 1


class TestAuthGate:
    def test_list_requires_auth(self, unauthed_client) -> None:
        res = unauthed_client.get("/api/invoices")
        assert res.status_code == 401

    def test_upload_requires_auth(self, unauthed_client) -> None:
        res = unauthed_client.post(
            "/api/invoices",
            files={"file": ("x.pdf", b"%PDF-", "application/pdf")},
        )
        assert res.status_code == 401
