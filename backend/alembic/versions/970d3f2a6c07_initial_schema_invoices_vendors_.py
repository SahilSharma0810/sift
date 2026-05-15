"""initial schema: invoices vendors extractions field_corrections

Revision ID: 970d3f2a6c07
Revises:
Create Date: 2026-05-13 16:02:59.896730

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "970d3f2a6c07"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:

    op.create_table(
        "vendors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("tax_id", sa.String(length=64), nullable=True),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("memory", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendors_normalized_name", "vendors", ["normalized_name"], unique=False)
    op.create_table(
        "invoices",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("perceptual_hash", sa.String(length=64), nullable=True),
        sa.Column("vendor_id", sa.UUID(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["vendor_id"],
            ["vendors.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invoices_file_hash", "invoices", ["file_hash"], unique=False)
    op.create_index("ix_invoices_perceptual_hash", "invoices", ["perceptual_hash"], unique=False)
    op.create_index("ix_invoices_review_status", "invoices", ["review_status"], unique=False)
    op.create_table(
        "extractions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("cascade_trace", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("extracted_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence_per_field", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("predicted_triage_state", sa.String(length=32), nullable=False),
        sa.Column(
            "predicted_triage_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_extractions_invoice_id", "extractions", ["invoice_id"], unique=False)
    op.create_index(
        "ix_extractions_predicted_triage_state",
        "extractions",
        ["predicted_triage_state"],
        unique=False,
    )
    op.create_index(
        "uq_extractions_one_current_per_invoice",
        "extractions",
        ["invoice_id"],
        unique=True,
        postgresql_where="is_current = true",
    )
    op.create_table(
        "field_corrections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("extraction_id", sa.UUID(), nullable=False),
        sa.Column("field_name", sa.String(length=128), nullable=False),
        sa.Column("original_value", sa.String(), nullable=True),
        sa.Column("corrected_value", sa.String(), nullable=False),
        sa.Column(
            "corrected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id"],
            ["extractions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_field_corrections_extraction_id", "field_corrections", ["extraction_id"], unique=False
    )
    op.create_index(
        "ix_field_corrections_field_name", "field_corrections", ["field_name"], unique=False
    )

def downgrade() -> None:

    op.drop_index("ix_field_corrections_field_name", table_name="field_corrections")
    op.drop_index("ix_field_corrections_extraction_id", table_name="field_corrections")
    op.drop_table("field_corrections")
    op.drop_index(
        "uq_extractions_one_current_per_invoice",
        table_name="extractions",
        postgresql_where="is_current = true",
    )
    op.drop_index("ix_extractions_predicted_triage_state", table_name="extractions")
    op.drop_index("ix_extractions_invoice_id", table_name="extractions")
    op.drop_table("extractions")
    op.drop_index("ix_invoices_review_status", table_name="invoices")
    op.drop_index("ix_invoices_perceptual_hash", table_name="invoices")
    op.drop_index("ix_invoices_file_hash", table_name="invoices")
    op.drop_table("invoices")
    op.drop_index("ix_vendors_normalized_name", table_name="vendors")
    op.drop_table("vendors")

