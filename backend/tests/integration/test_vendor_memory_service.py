"""Vendor-memory service: running stats from confirmed extractions."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.adapters.storage.vendor_repo import upsert_by_normalized_name
from app.services.vendor_memory_service import (
    compute_history_scores,
    update_stats_from_extraction,
)

def _build_extraction_row(db_session, vendor, fields):
    """Helper: create a minimal Extraction row via the repo."""
    from app.adapters.storage.extraction_repo import create_extraction
    from app.adapters.storage.invoice_repo import create_invoice

    inv = create_invoice(
        db_session,
        storage_key="x.pdf",
        file_hash=f"vm-{vendor.id}-{fields.get('total', 0)}",
        vendor_id=vendor.id,
    )
    return create_extraction(
        db_session,
        invoice_id=inv.id,
        model="claude-haiku-4-5",
        extracted_fields={
            k: {"value": v, "bbox": None, "page": 0, "confidence": 1.0, "source": "manual-entry"}
            for k, v in fields.items()
        },
        confidence_per_field={k: 1.0 for k in fields},
        predicted_triage_state="confident",
        predicted_triage_reasons=[],
        cascade_trace={},
    )

class TestUpdateStatsFromExtraction:
    def test_first_extraction_seeds_stats(self, db_session: Session) -> None:
        v = upsert_by_normalized_name(db_session, name="VendorMem-Stats-1")
        ext = _build_extraction_row(db_session, v, {"total": 1180.0})
        update_stats_from_extraction(db_session, vendor=v, extraction=ext)
        db_session.refresh(v)
        assert v.memory["stats"]["total_seen"] == 1
        assert v.memory["stats"]["avg_total"] == 1180.0
        assert v.memory["stats"]["std_total"] == 0.0

    def test_second_extraction_updates_stats(self, db_session: Session) -> None:
        v = upsert_by_normalized_name(db_session, name="VendorMem-Stats-2")
        e1 = _build_extraction_row(db_session, v, {"total": 1000.0})
        e2 = _build_extraction_row(db_session, v, {"total": 1500.0})
        update_stats_from_extraction(db_session, vendor=v, extraction=e1)
        update_stats_from_extraction(db_session, vendor=v, extraction=e2)
        db_session.refresh(v)
        assert v.memory["stats"]["total_seen"] == 2
        assert v.memory["stats"]["avg_total"] == 1250.0

        assert abs(v.memory["stats"]["std_total"] - 353.55339) < 0.01

class TestComputeHistoryScores:
    def test_cold_start_returns_empty(self, db_session: Session) -> None:
        v = upsert_by_normalized_name(db_session, name="VendorMem-History-1")
        scores = compute_history_scores(vendor=v, fields={"total": 1180.0})
        assert scores == {}

    def test_close_to_mean_high_score(self, db_session: Session) -> None:
        v = upsert_by_normalized_name(db_session, name="VendorMem-History-2")
        v.memory = {
            "stats": {"total_seen": 10, "avg_total": 1180.0, "std_total": 50.0},
            "rules": [],
        }
        scores = compute_history_scores(vendor=v, fields={"total": 1200.0})

        assert scores["total"] == 1.0

    def test_far_from_mean_low_score(self, db_session: Session) -> None:
        v = upsert_by_normalized_name(db_session, name="VendorMem-History-3")
        v.memory = {
            "stats": {"total_seen": 10, "avg_total": 1180.0, "std_total": 50.0},
            "rules": [],
        }
        scores = compute_history_scores(vendor=v, fields={"total": 14231.0})

        assert scores["total"] == 0.3
