"""SQLAlchemy ORM models for the schema sketch in PLAN.md.

Tables: invoices, vendors, extractions, field_corrections.
See PLAN.md "Schema sketch" for the locked JSONB shapes documented in
domain/models.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import ClassVar

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    type_annotation_map: ClassVar[dict] = {dict: JSONB, list: JSONB}

class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    memory: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (Index("ix_vendors_normalized_name", "normalized_name"),)

    invoices: Mapped[list[Invoice]] = relationship(back_populates="vendor")

class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    perceptual_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    review_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)

    duplicate_dismissals: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    __table_args__ = (
        Index("ix_invoices_file_hash", "file_hash"),
        Index("ix_invoices_perceptual_hash", "perceptual_hash"),
        Index("ix_invoices_review_status", "review_status"),
    )

    vendor: Mapped[Vendor | None] = relationship(back_populates="invoices")
    extractions: Mapped[list[Extraction]] = relationship(
        back_populates="invoice", order_by="Extraction.created_at.desc()"
    )

class Extraction(Base):
    __tablename__ = "extractions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(64), nullable=False)

    cascade_trace: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    extracted_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    confidence_per_field: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    predicted_triage_state: Mapped[str] = mapped_column(String(32), nullable=False)
    predicted_triage_reasons: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    line_items: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    tax_breakdown: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (

        Index(
            "uq_extractions_one_current_per_invoice",
            "invoice_id",
            unique=True,
            postgresql_where="is_current = true",
        ),
        Index("ix_extractions_invoice_id", "invoice_id"),
        Index("ix_extractions_predicted_triage_state", "predicted_triage_state"),
    )

    invoice: Mapped[Invoice] = relationship(back_populates="extractions")
    corrections: Mapped[list[FieldCorrection]] = relationship(back_populates="extraction")

class FieldCorrection(Base):
    __tablename__ = "field_corrections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("extractions.id"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    original_value: Mapped[str | None] = mapped_column(String, nullable=True)
    corrected_value: Mapped[str] = mapped_column(String, nullable=False)
    corrected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_field_corrections_extraction_id", "extraction_id"),
        Index("ix_field_corrections_field_name", "field_name"),
    )

    extraction: Mapped[Extraction] = relationship(back_populates="corrections")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_auth_sessions_user_id", "user_id"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
    )

    user: Mapped[User] = relationship(back_populates="sessions")


class AnomalyAck(Base):
    __tablename__ = "anomaly_acks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    anomaly_subtype: Mapped[str] = mapped_column(Text, nullable=False)
    anomaly_field: Mapped[str] = mapped_column(Text, nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    acknowledged_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_anomaly_acks_invoice_id", "invoice_id"),
        UniqueConstraint(
            "invoice_id",
            "anomaly_subtype",
            "anomaly_field",
            name="uq_anomaly_acks_key",
        ),
    )
