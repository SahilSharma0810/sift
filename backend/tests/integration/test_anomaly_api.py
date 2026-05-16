from __future__ import annotations

from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.adapters.storage.invoice_repo import create_invoice
from app.adapters.storage.vendor_repo import upsert_by_normalized_name
from app.db.models import Extraction


def _seed_anomaly_invoice(db_session: Session) -> str:
    vendor = upsert_by_normalized_name(db_session, name="API Halcyon")
    inv = create_invoice(
        db_session,
        storage_key="api-halc.pdf",
        file_hash="api-halc-1",
        vendor_id=vendor.id,
    )
    inv.review_status = "pending"
    db_session.add(
        Extraction(
            invoice_id=inv.id,
            model="stub",
            cascade_trace={},
            extracted_fields={
                "total": {"value": 34062.50, "confidence": 0.99, "source": "stub"},
                "currency": {"value": "USD", "confidence": 0.99, "source": "stub"},
            },
            confidence_per_field={"total": 0.99},
            predicted_triage_state="needs_review",
            predicted_triage_reasons=[
                {
                    "type": "anomaly",
                    "field": "total",
                    "vendor_mean": 7900.0,
                    "vendor_std": 1500.0,
                    "z_score": 4.2,
                }
            ],
            line_items=[],
            tax_breakdown=[],
            raw_text=None,
            is_current=True,
        )
    )
    db_session.commit()
    return str(inv.id)


class TestGetAnomalies:
    def test_unauthenticated_returns_401(self, unauthed_client: TestClient) -> None:
        res = unauthed_client.get("/api/anomalies")
        assert res.status_code == 401

    def test_authed_empty_corpus(self, api_client: TestClient) -> None:
        res = api_client.get("/api/anomalies")
        assert res.status_code == 200
        body = res.json()
        assert body["anomalies"] == []
        assert body["counts"]["unreviewed"] == 0
        assert body["aggregates"]["vendors_affected"] == 0

    def test_authed_with_seed(self, api_client: TestClient, db_session: Session) -> None:
        invoice_id = _seed_anomaly_invoice(db_session)
        res = api_client.get("/api/anomalies")
        assert res.status_code == 200
        body = res.json()
        assert len(body["anomalies"]) == 1
        a = body["anomalies"][0]
        assert a["type"] == "amount"
        assert a["id"] == f"{invoice_id}:amount:total"
        assert a["severity"] == "high"
        assert body["counts"]["unreviewed"] == 1
        assert body["aggregates"]["total_flagged_currency"] == "USD"


class TestAcknowledge:
    def test_unauthenticated_returns_401(self, unauthed_client: TestClient) -> None:
        res = unauthed_client.post(
            "/api/anomalies/00000000-0000-0000-0000-000000000000:amount:total/acknowledge"
        )
        assert res.status_code == 401

    def test_unknown_id_returns_404(self, api_client: TestClient) -> None:
        res = api_client.post(
            "/api/anomalies/00000000-0000-0000-0000-000000000000:amount:total/acknowledge"
        )
        assert res.status_code == 404

    def test_malformed_id_returns_422(self, api_client: TestClient) -> None:
        res = api_client.post("/api/anomalies/not-a-real-id/acknowledge")
        assert res.status_code == 422

    def test_acknowledge_round_trip(self, api_client: TestClient, db_session: Session) -> None:
        invoice_id = _seed_anomaly_invoice(db_session)
        anomaly_id = f"{invoice_id}:amount:total"
        res = api_client.post(f"/api/anomalies/{anomaly_id}/acknowledge")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "acknowledged"
        assert body["acknowledged_by"] == "test-clerk@sift.demo"


class TestAcknowledgeBulk:
    def test_unauthenticated_returns_401(self, unauthed_client: TestClient) -> None:
        res = unauthed_client.post(
            "/api/anomalies/acknowledge-bulk",
            json={"anomaly_ids": ["00000000-0000-0000-0000-000000000000:amount:total"]},
        )
        assert res.status_code == 401

    def test_empty_list_returns_422(self, api_client: TestClient) -> None:
        res = api_client.post("/api/anomalies/acknowledge-bulk", json={"anomaly_ids": []})
        assert res.status_code == 422

    def test_oversize_list_returns_422(self, api_client: TestClient) -> None:
        res = api_client.post(
            "/api/anomalies/acknowledge-bulk",
            json={"anomaly_ids": ["x"] * 201},
        )
        assert res.status_code == 422

    def test_partial_success(self, api_client: TestClient, db_session: Session) -> None:
        invoice_id = _seed_anomaly_invoice(db_session)
        good = f"{invoice_id}:amount:total"
        bad = "00000000-0000-0000-0000-000000000000:amount:total"
        res = api_client.post(
            "/api/anomalies/acknowledge-bulk",
            json={"anomaly_ids": [good, bad]},
        )
        assert res.status_code == 200
        body = res.json()
        assert len(body["acknowledged"]) == 1
        assert len(body["failed"]) == 1
        assert body["failed"][0]["id"] == bad
