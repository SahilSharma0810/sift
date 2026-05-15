"""add anomaly_acks

Revision ID: 7c7aa1861858
Revises: 9b2c7070f362
Create Date: 2026-05-15 11:59:32.894024

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c7aa1861858"
down_revision: str | Sequence[str] | None = "9b2c7070f362"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "anomaly_acks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("anomaly_subtype", sa.Text(), nullable=False),
        sa.Column("anomaly_field", sa.Text(), nullable=False),
        sa.Column(
            "acknowledged_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("acknowledged_by_user_id", sa.UUID(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["acknowledged_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "invoice_id",
            "anomaly_subtype",
            "anomaly_field",
            name="uq_anomaly_acks_key",
        ),
    )
    op.create_index("ix_anomaly_acks_invoice_id", "anomaly_acks", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_anomaly_acks_invoice_id", table_name="anomaly_acks")
    op.drop_table("anomaly_acks")
