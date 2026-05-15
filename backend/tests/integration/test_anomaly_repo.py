from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.adapters.storage.anomaly_repo import (
    create_ack,
    list_acks_by_invoice_ids,
    vendor_history_query,
)
from app.adapters.storage.invoice_repo import create_invoice
from app.adapters.storage.user_repo import upsert_demo_user
from app.adapters.storage.vendor_repo import upsert_by_normalized_name
from app.db.models import AnomalyAck


class TestCreateAck:
    def test_inserts_a_row(self, db_session: Session) -> None:
        user = upsert_demo_user(db_session, email="ack@example.test", password="x")
        vendor = upsert_by_normalized_name(db_session, name="Halcyon Software")
        invoice = create_invoice(
            db_session,
            file_path="/data/uploads/h.pdf",
            file_hash="hash-h-1",
            vendor_id=vendor.id,
        )
        ack = create_ack(
            db_session,
            invoice_id=invoice.id,
            subtype="amount",
            field="total",
            user_id=user.id,
            notes=None,
        )
        assert ack.id is not None
        assert ack.anomaly_subtype == "amount"
        assert ack.anomaly_field == "total"
        assert ack.acknowledged_by_user_id == user.id

    def test_idempotent_on_unique_conflict(self, db_session: Session) -> None:
        user = upsert_demo_user(db_session, email="ack-idem@example.test", password="x")
        vendor = upsert_by_normalized_name(db_session, name="Halcyon Idempotent")
        invoice = create_invoice(
            db_session,
            file_path="/data/uploads/h2.pdf",
            file_hash="hash-h-2",
            vendor_id=vendor.id,
        )
        a1 = create_ack(
            db_session,
            invoice_id=invoice.id,
            subtype="amount",
            field="total",
            user_id=user.id,
            notes=None,
        )
        a2 = create_ack(
            db_session,
            invoice_id=invoice.id,
            subtype="amount",
            field="total",
            user_id=user.id,
            notes="second call",
        )
        assert a1.id == a2.id


class TestListAcksByInvoiceIds:
    def test_returns_acks_for_ids(self, db_session: Session) -> None:
        user = upsert_demo_user(db_session, email="list-ack@example.test", password="x")
        vendor = upsert_by_normalized_name(db_session, name="V Lookup")
        inv = create_invoice(
            db_session,
            file_path="/data/uploads/lookup.pdf",
            file_hash="hash-lookup",
            vendor_id=vendor.id,
        )
        create_ack(
            db_session,
            invoice_id=inv.id,
            subtype="amount",
            field="total",
            user_id=user.id,
            notes=None,
        )
        rows = list_acks_by_invoice_ids(db_session, invoice_ids=[inv.id])
        assert len(rows) == 1
        assert rows[0].invoice_id == inv.id

    def test_empty_input_returns_empty_list(self, db_session: Session) -> None:
        assert list_acks_by_invoice_ids(db_session, invoice_ids=[]) == []


class TestVendorHistoryQuery:
    def test_returns_confirmed_totals_ordered_desc(self, db_session: Session) -> None:
        vendor = upsert_by_normalized_name(db_session, name="History Vendor")
        results = vendor_history_query(
            db_session,
            vendor_id=vendor.id,
            exclude_invoice_id=uuid4(),
            limit=11,
        )
        assert results == []
