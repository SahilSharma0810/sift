"""Storage repo tests — against real Postgres."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.adapters.storage.extraction_repo import (
    create_extraction,
    get_current_extraction,
    mark_current,
)
from app.adapters.storage.invoice_repo import (
    create_invoice,
    find_by_file_hash,
    list_invoices,
)
from app.adapters.storage.vendor_repo import (
    normalize_name,
    upsert_by_normalized_name,
)

class TestVendorRepo:
    def test_normalize_name_strips_punctuation(self) -> None:
        assert normalize_name("Acme, Inc.") == "acme inc"
        assert normalize_name("  Vega   Logistics  ") == "vega logistics"

    def test_upsert_creates_when_absent(self, db_session: Session) -> None:
        v = upsert_by_normalized_name(db_session, name="Vega Logistics A")
        assert v.id is not None
        assert v.name == "Vega Logistics A"
        assert v.normalized_name == "vega logistics a"
        assert v.memory == {}

    def test_upsert_returns_existing(self, db_session: Session) -> None:
        v1 = upsert_by_normalized_name(db_session, name="Vega Logistics B")
        v2 = upsert_by_normalized_name(db_session, name="vega logistics b ")
        assert v1.id == v2.id

    def test_normalize_treats_punctuation_variants_as_same_vendor(
        self, db_session: Session
    ) -> None:
        v1 = upsert_by_normalized_name(db_session, name="Acme Repo Inc.")
        v2 = upsert_by_normalized_name(db_session, name="Acme Repo Inc")
        assert v1.id == v2.id

class TestInvoiceRepo:
    def test_create_and_fetch(self, db_session: Session) -> None:
        v = upsert_by_normalized_name(db_session, name="Vega Inv A")
        inv = create_invoice(
            db_session,
            file_path="/data/uploads/abc.pdf",
            file_hash="hash-abc-1",
            vendor_id=v.id,
        )
        assert inv.id is not None
        assert inv.review_status == "pending"

        found = find_by_file_hash(db_session, "hash-abc-1")
        assert found is not None
        assert found.id == inv.id

    def test_find_by_file_hash_returns_none_when_absent(self, db_session: Session) -> None:
        assert find_by_file_hash(db_session, "definitely-not-there-xyz") is None

    def test_list_invoices_returns_recently_uploaded(self, db_session: Session) -> None:
        v = upsert_by_normalized_name(db_session, name="Vega List Test")
        a = create_invoice(db_session, file_path="/a", file_hash="ha-list-1", vendor_id=v.id)
        b = create_invoice(db_session, file_path="/b", file_hash="hb-list-1", vendor_id=v.id)
        invoices = list_invoices(db_session, limit=10)

        ids = {inv.id for inv in invoices[:5]}
        assert a.id in ids
        assert b.id in ids

class TestExtractionRepo:
    def _make_invoice(self, db_session: Session, hash_suffix: str):
        v = upsert_by_normalized_name(db_session, name=f"Vega Ext {hash_suffix}")
        return create_invoice(
            db_session,
            file_path=f"/x-{hash_suffix}",
            file_hash=f"hext-{hash_suffix}",
            vendor_id=v.id,
        )

    def test_create_and_get_current(self, db_session: Session) -> None:
        inv = self._make_invoice(db_session, "create")
        ext = create_extraction(
            db_session,
            invoice_id=inv.id,
            model="claude-haiku-4-5",
            extracted_fields={
                "vendor_name": {
                    "value": "Vega",
                    "confidence": 0.95,
                    "source": "pymupdf+haiku",
                    "bbox": None,
                    "page": 0,
                }
            },
            confidence_per_field={"vendor_name": 0.85},
            predicted_triage_state="confident",
            predicted_triage_reasons=[],
            cascade_trace={},
        )
        current = get_current_extraction(db_session, invoice_id=inv.id)
        assert current is not None
        assert current.id == ext.id

    def test_mark_current_demotes_previous(self, db_session: Session) -> None:
        inv = self._make_invoice(db_session, "demote")
        first = create_extraction(
            db_session,
            invoice_id=inv.id,
            model="claude-haiku-4-5",
            extracted_fields={},
            confidence_per_field={},
            predicted_triage_state="confident",
            predicted_triage_reasons=[],
            cascade_trace={},
        )
        second = create_extraction(
            db_session,
            invoice_id=inv.id,
            model="claude-sonnet-4-6",
            extracted_fields={},
            confidence_per_field={},
            predicted_triage_state="confident",
            predicted_triage_reasons=[],
            cascade_trace={},
        )

        db_session.refresh(first)
        db_session.refresh(second)
        assert first.is_current is False
        assert second.is_current is True

        current = get_current_extraction(db_session, invoice_id=inv.id)
        assert current is not None
        assert current.id == second.id

    def test_mark_current_promotes_explicit(self, db_session: Session) -> None:
        inv = self._make_invoice(db_session, "promote")
        first = create_extraction(
            db_session,
            invoice_id=inv.id,
            model="claude-haiku-4-5",
            extracted_fields={},
            confidence_per_field={},
            predicted_triage_state="confident",
            predicted_triage_reasons=[],
            cascade_trace={},
        )
        second = create_extraction(
            db_session,
            invoice_id=inv.id,
            model="claude-sonnet-4-6",
            extracted_fields={},
            confidence_per_field={},
            predicted_triage_state="needs_review",
            predicted_triage_reasons=[],
            cascade_trace={},
        )

        mark_current(db_session, extraction_id=first.id)
        db_session.refresh(first)
        db_session.refresh(second)
        assert first.is_current is True
        assert second.is_current is False

from app.adapters.storage.invoice_repo import (  # noqa: E402
    find_phash_candidates,
    record_duplicate_dismissal,
    set_perceptual_hash,
    update_review_status,
)

class TestInvoiceRepoExtensions:
    def _new_invoice(self, db_session, vendor_name: str, file_hash: str):
        from app.adapters.storage.invoice_repo import create_invoice
        from app.adapters.storage.vendor_repo import upsert_by_normalized_name

        v = upsert_by_normalized_name(db_session, name=vendor_name)
        return create_invoice(
            db_session, file_path=f"/x-{file_hash}", file_hash=file_hash, vendor_id=v.id
        )

    def test_phash_candidates_skip_null(self, db_session) -> None:
        a = self._new_invoice(db_session, "Vendor A D27", "phash-test-a")
        b = self._new_invoice(db_session, "Vendor B D27", "phash-test-b")
        set_perceptual_hash(db_session, invoice_id=a.id, perceptual_hash="ffffffffffffffff")
        cands = find_phash_candidates(db_session)
        ids = {c.id for c in cands}
        assert a.id in ids
        assert b.id not in ids

    def test_update_review_status(self, db_session) -> None:
        inv = self._new_invoice(db_session, "Status Vendor D27", "status-d27-1")
        out = update_review_status(db_session, invoice_id=inv.id, review_status="confirmed")
        assert out.review_status == "confirmed"

    def test_record_duplicate_dismissal_is_idempotent(self, db_session) -> None:
        a = self._new_invoice(db_session, "Dismiss A D27", "dismiss-d27-a")
        b = self._new_invoice(db_session, "Dismiss B D27", "dismiss-d27-b")
        record_duplicate_dismissal(db_session, invoice_id=a.id, dismissed_against_id=b.id)
        record_duplicate_dismissal(db_session, invoice_id=a.id, dismissed_against_id=b.id)
        db_session.refresh(a)
        assert a.duplicate_dismissals == [str(b.id)]
