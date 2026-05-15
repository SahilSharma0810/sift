from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.adapters.storage.invoice_repo import create_invoice
from app.adapters.storage.user_repo import upsert_demo_user
from app.adapters.storage.vendor_repo import upsert_by_normalized_name
from app.db.models import Extraction, Invoice
from app.services.anomaly_service import (
    list_anomalies,
)


def _seed_invoice_with_anomaly(
    db_session: Session,
    *,
    vendor_name: str,
    file_hash: str,
    total: float,
    currency: str,
    z_score: float,
    avg: float,
    std: float,
    review_status: str = "pending",
    confirmed_history_totals: list[float] | None = None,
) -> Invoice:
    """Insert a vendor + invoice + current extraction with one anomaly reason.

    Optionally pre-seeds confirmed prior invoices for the same vendor so the
    sparkline-history query has data to return.
    """
    vendor = upsert_by_normalized_name(db_session, name=vendor_name)

    if confirmed_history_totals:
        for i, t in enumerate(confirmed_history_totals):
            prev_inv = create_invoice(
                db_session,
                file_path=f"/data/uploads/{file_hash}-prev-{i}.pdf",
                file_hash=f"{file_hash}-prev-{i}",
                vendor_id=vendor.id,
            )
            prev_inv.review_status = "confirmed"
            db_session.add(
                Extraction(
                    invoice_id=prev_inv.id,
                    model="stub",
                    cascade_trace={},
                    extracted_fields={"total": {"value": t, "confidence": 0.99, "source": "stub"}},
                    confidence_per_field={"total": 0.99},
                    predicted_triage_state="confident",
                    predicted_triage_reasons=[],
                    line_items=[],
                    tax_breakdown=[],
                    raw_text=None,
                    is_current=True,
                )
            )

    inv = create_invoice(
        db_session,
        file_path=f"/data/uploads/{file_hash}.pdf",
        file_hash=file_hash,
        vendor_id=vendor.id,
    )
    inv.review_status = review_status
    db_session.add(
        Extraction(
            invoice_id=inv.id,
            model="stub",
            cascade_trace={},
            extracted_fields={
                "total": {"value": total, "confidence": 0.99, "source": "stub"},
                "currency": {"value": currency, "confidence": 0.99, "source": "stub"},
            },
            confidence_per_field={"total": 0.99, "currency": 0.99},
            predicted_triage_state="needs_review",
            predicted_triage_reasons=[
                {
                    "type": "anomaly",
                    "field": "total",
                    "vendor_mean": avg,
                    "vendor_std": std,
                    "z_score": z_score,
                }
            ],
            line_items=[],
            tax_breakdown=[],
            raw_text=None,
            is_current=True,
        )
    )
    db_session.commit()
    return inv


class TestListAnomaliesEmpty:
    def test_empty_corpus_zero_counts(self, db_session: Session) -> None:
        resp = list_anomalies(db_session)
        assert resp.anomalies == []
        assert resp.counts.all == 0
        assert resp.counts.unreviewed == 0
        assert resp.aggregates.total_flagged_amount == 0
        assert resp.aggregates.vendors_affected == 0


class TestListAnomaliesPopulated:
    def test_amount_anomaly_surfaces_with_correct_shape(self, db_session: Session) -> None:
        _seed_invoice_with_anomaly(
            db_session,
            vendor_name="Halcyon Software",
            file_hash="halc-1",
            total=34062.50,
            currency="USD",
            z_score=4.2,
            avg=7900.0,
            std=1500.0,
            confirmed_history_totals=[6800, 7200, 8100, 7500, 9200, 6900, 7600, 8400, 7300, 8900, 7800],
        )
        resp = list_anomalies(db_session)
        assert len(resp.anomalies) == 1
        a = resp.anomalies[0]
        assert a.type == "amount"
        assert a.status == "unreviewed"
        assert a.vendor == "Halcyon Software"
        assert a.metric.value == 34062.50
        assert a.metric.currency == "USD"
        assert a.severity == "high"
        assert a.z_score == 4.2
        assert a.headline == "$34,062.50 invoice"
        assert "4.2σ" in a.sub
        assert "$7,900" in a.sub
        # 11 prior + 1 current = 12 history points
        assert len(a.history) == 12
        assert a.history[-1].current is True

    def test_severity_bands(self, db_session: Session) -> None:
        _seed_invoice_with_anomaly(
            db_session,
            vendor_name="Vendor A",
            file_hash="A-1",
            total=10000.0,
            currency="USD",
            z_score=4.5,
            avg=1000.0,
            std=500.0,
        )
        _seed_invoice_with_anomaly(
            db_session,
            vendor_name="Vendor B",
            file_hash="B-1",
            total=2200.0,
            currency="USD",
            z_score=3.0,
            avg=1000.0,
            std=400.0,
        )
        resp = list_anomalies(db_session)
        severities = {a.vendor: a.severity for a in resp.anomalies}
        assert severities["Vendor A"] == "high"
        assert severities["Vendor B"] == "medium"

    def test_aggregates_dominant_currency(self, db_session: Session) -> None:
        _seed_invoice_with_anomaly(
            db_session,
            vendor_name="USD Vendor 1",
            file_hash="usd-1",
            total=10000.0,
            currency="USD",
            z_score=3.5,
            avg=1000.0,
            std=500.0,
        )
        _seed_invoice_with_anomaly(
            db_session,
            vendor_name="USD Vendor 2",
            file_hash="usd-2",
            total=20000.0,
            currency="USD",
            z_score=4.0,
            avg=2000.0,
            std=500.0,
        )
        _seed_invoice_with_anomaly(
            db_session,
            vendor_name="EUR Vendor",
            file_hash="eur-1",
            total=5000.0,
            currency="EUR",
            z_score=3.2,
            avg=500.0,
            std=200.0,
        )
        resp = list_anomalies(db_session)
        assert resp.aggregates.total_flagged_currency == "USD"
        assert resp.aggregates.total_flagged_amount == 30000.0
        assert resp.aggregates.vendors_affected == 3
        assert resp.aggregates.highest_severity_z == 4.0

    def test_counts_breakdown(self, db_session: Session) -> None:
        _seed_invoice_with_anomaly(
            db_session,
            vendor_name="Count Vendor",
            file_hash="cnt-1",
            total=10000.0,
            currency="USD",
            z_score=3.5,
            avg=1000.0,
            std=500.0,
        )
        resp = list_anomalies(db_session)
        assert resp.counts.all == 1
        assert resp.counts.unreviewed == 1
        assert resp.counts.amount == 1
        assert resp.counts.frequency == 0
        assert resp.counts.pattern == 0
        assert resp.counts.acknowledged == 0
