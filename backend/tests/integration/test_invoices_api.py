"""API integration tests via FastAPI TestClient.

These exercise the route → service → repo → DB stack. The LLM client is
patched at the import site in services/extraction_service.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.llm_client import ExtractionResult
from app.main import app
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


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestUploadInvoice:
    def test_upload_returns_invoice_with_extraction(self, client: TestClient) -> None:
        with (
            patch_make_llm_client(header=_fake_llm_result()),
            CLEAN_PDF.open("rb") as fh,
        ):
            res = client.post(
                "/api/invoices",
                files={"file": ("clean.pdf", fh, "application/pdf")},
            )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["review_status"] == "pending"
        assert body["current_extraction"]["predicted_triage_state"] == "confident"
        assert "Vega Logistics" in str(body["current_extraction"]["extracted_fields"])

    def test_upload_rejects_non_pdf(self, client: TestClient) -> None:
        res = client.post(
            "/api/invoices",
            files={"file": ("oops.txt", b"hello", "text/plain")},
        )
        assert res.status_code == 415

    def test_list_returns_uploaded(self, client: TestClient) -> None:
        with (
            patch_make_llm_client(header=_fake_llm_result()),
            CLEAN_PDF.open("rb") as fh,
        ):
            client.post(
                "/api/invoices",
                files={"file": ("clean2.pdf", fh, "application/pdf")},
            )
        res = client.get("/api/invoices")
        assert res.status_code == 200
        body = res.json()
        assert len(body) >= 1
