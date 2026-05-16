from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.adapters.storage.invoice_repo import create_invoice
from app.adapters.storage.user_repo import upsert_demo_user
from app.adapters.storage.vendor_repo import upsert_by_normalized_name
from app.db.models import Extraction, Invoice
from sqlalchemy import select

from app.db.models import Vendor
from app.services.anomaly_service import (
    acknowledge,
    acknowledge_bulk,
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
                storage_key=f"{file_hash}-prev-{i}.pdf",
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
        storage_key=f"{file_hash}.pdf",
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
        # Sub copy is plain-English ratio against vendor mean — no sigma jargon.
        # 34062.50 / 7900 = 4.31× → formatted as "4.3×".
        assert "4.3×" in a.sub
        assert "this vendor's average" in a.sub
        assert "$7,900" in a.sub
        assert "11 prior invoices" in a.sub
        assert "σ" not in a.sub
        # 11 prior + 1 current = 12 history points
        assert len(a.history) == 12
        assert a.history[-1].current is True

    def test_sub_copy_below_average_says_smaller(self, db_session: Session) -> None:
        _seed_invoice_with_anomaly(
            db_session,
            vendor_name="Below Avg Vendor",
            file_hash="below-1",
            total=50.0,
            currency="USD",
            z_score=3.5,
            avg=500.0,
            std=100.0,
            confirmed_history_totals=[450, 500, 550, 480, 520],
        )
        resp = list_anomalies(db_session)
        a = resp.anomalies[0]
        # 500 / 50 = 10× → formatted as "10×"
        assert "10×" in a.sub
        assert "smaller than this vendor's average" in a.sub
        assert "$500" in a.sub

    def test_sub_copy_huge_ratio_renders_as_thousands(self, db_session: Session) -> None:
        _seed_invoice_with_anomaly(
            db_session,
            vendor_name="Huge Ratio Vendor",
            file_hash="huge-1",
            total=472396.0,
            currency="USD",
            z_score=4541.5,
            avg=433.0,
            std=104.0,
            confirmed_history_totals=[313, 493, 493],
        )
        resp = list_anomalies(db_session)
        a = resp.anomalies[0]
        # 472396 / 433 ≈ 1091 → formatted with thousands separator as "1,091×"
        assert "1,091×" in a.sub
        assert "this vendor's average" in a.sub
        assert "$433" in a.sub
        assert "σ" not in a.sub

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


class TestAcknowledge:
    def test_acknowledge_inserts_ack_and_appends_vendor_memory(
        self, db_session: Session
    ) -> None:
        inv = _seed_invoice_with_anomaly(
            db_session,
            vendor_name="Ack Halcyon",
            file_hash="ack-halc-1",
            total=34062.50,
            currency="USD",
            z_score=4.2,
            avg=7900.0,
            std=1500.0,
        )
        user = upsert_demo_user(db_session, email="acker@example.test", password="x")

        anomaly_id = f"{inv.id}:amount:total"
        updated = acknowledge(
            db_session,
            anomaly_id=anomaly_id,
            user_id=user.id,
            notes=None,
        )
        assert updated.status == "acknowledged"
        assert updated.acknowledged_by == "acker@example.test"

        vendor = db_session.execute(
            select(Vendor).where(Vendor.id == inv.vendor_id)
        ).scalar_one()
        outliers = (vendor.memory or {}).get("acknowledged_outliers", {})
        assert "total" in outliers
        assert len(outliers["total"]) == 1
        assert outliers["total"][0]["value"] == 34062.50

    def test_acknowledge_is_idempotent(self, db_session: Session) -> None:
        inv = _seed_invoice_with_anomaly(
            db_session,
            vendor_name="Idem Vendor",
            file_hash="idem-1",
            total=20000.0,
            currency="USD",
            z_score=4.0,
            avg=2000.0,
            std=500.0,
        )
        user = upsert_demo_user(db_session, email="idem-acker@example.test", password="x")

        anomaly_id = f"{inv.id}:amount:total"
        first = acknowledge(db_session, anomaly_id=anomaly_id, user_id=user.id, notes=None)
        second = acknowledge(db_session, anomaly_id=anomaly_id, user_id=user.id, notes="extra")

        assert first.acknowledged_at == second.acknowledged_at

        vendor = db_session.execute(
            select(Vendor).where(Vendor.id == inv.vendor_id)
        ).scalar_one()
        outliers = (vendor.memory or {}).get("acknowledged_outliers", {})
        assert len(outliers["total"]) == 1

    def test_acknowledge_unknown_id_raises(self, db_session: Session) -> None:
        user = upsert_demo_user(db_session, email="nobody-acker@example.test", password="x")
        with pytest.raises(LookupError):
            acknowledge(
                db_session,
                anomaly_id="00000000-0000-0000-0000-000000000000:amount:total",
                user_id=user.id,
                notes=None,
            )

    def test_acknowledge_malformed_id_raises(self, db_session: Session) -> None:
        user = upsert_demo_user(db_session, email="mal-acker@example.test", password="x")
        with pytest.raises(ValueError):
            acknowledge(db_session, anomaly_id="not-a-real-id", user_id=user.id, notes=None)


class TestAcknowledgeBulk:
    def test_partial_success(self, db_session: Session) -> None:
        inv = _seed_invoice_with_anomaly(
            db_session,
            vendor_name="Bulk Vendor",
            file_hash="bulk-1",
            total=15000.0,
            currency="USD",
            z_score=3.5,
            avg=1500.0,
            std=400.0,
        )
        user = upsert_demo_user(db_session, email="bulk-acker@example.test", password="x")

        good = f"{inv.id}:amount:total"
        bad = "00000000-0000-0000-0000-000000000000:amount:total"
        result = acknowledge_bulk(
            db_session,
            anomaly_ids=[good, bad],
            user_id=user.id,
        )
        assert len(result.acknowledged) == 1
        assert result.acknowledged[0].vendor == "Bulk Vendor"
        assert len(result.failed) == 1
        assert result.failed[0].id == bad
        assert result.failed[0].error == "not_found"
