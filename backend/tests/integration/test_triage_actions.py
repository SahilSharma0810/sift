"""Triage-action endpoints: confirm / dismiss-duplicate / mark-unprocessable / retry."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.adapters.llm_client import ExtractionResult
from tests.conftest import patch_make_llm_client

FIXTURES = Path(__file__).parents[1] / "fixtures"
CLEAN_PDF = FIXTURES / "digital_invoice_clean.pdf"

def _fake_llm(file_suffix: str = "") -> ExtractionResult:
    return ExtractionResult(
        fields={
            "vendor_name": f"Vega Logistics{file_suffix}",
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
        prompt_hash="h",
        schema_hash="h",
        usage={
            "input_tokens": 500,
            "output_tokens": 80,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    )

def _upload(client: TestClient, unique: str) -> str:
    """Upload a unique-bytes copy of CLEAN_PDF and return the new invoice_id."""
    body = CLEAN_PDF.read_bytes() + f"\n%{unique}\n".encode()
    with patch_make_llm_client(header=_fake_llm()):
        res = client.post(
            "/api/invoices",
            files={"file": (f"{unique}.pdf", body, "application/pdf")},
        )
    assert res.status_code == 201, res.text
    return res.json()["id"]

class TestTriageActions:
    def test_confirm_changes_status(self, api_client: TestClient) -> None:
        invoice_id = _upload(api_client, "confirm-1")
        res = api_client.post(f"/api/invoices/{invoice_id}/confirm")
        assert res.status_code == 200
        assert res.json()["review_status"] == "confirmed"

    def test_mark_unprocessable(self, api_client: TestClient) -> None:
        invoice_id = _upload(api_client, "unproc-1")
        res = api_client.post(f"/api/invoices/{invoice_id}/mark-unprocessable")
        assert res.status_code == 200
        assert res.json()["review_status"] == "unprocessable"

    def test_dismiss_duplicate_records_pair(self, api_client: TestClient) -> None:
        a = _upload(api_client, "dismiss-a-1")
        b = _upload(api_client, "dismiss-b-1")
        res = api_client.post(f"/api/invoices/{b}/dismiss-duplicate", json={"against_id": a})
        assert res.status_code == 200, res.text
        assert a in res.json().get("duplicate_dismissals", [])

    def test_retry_creates_new_extraction(self, api_client: TestClient) -> None:
        invoice_id = _upload(api_client, "retry-1")
        with patch_make_llm_client(header=_fake_llm()):
            res = api_client.post(f"/api/invoices/{invoice_id}/retry")
        assert res.status_code == 200
        body = res.json()
        assert body["current_extraction"] is not None
