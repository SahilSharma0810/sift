"""rename file_path to storage_key

Revision ID: 7d1a3d8498c9
Revises: 7c7aa1861858
Create Date: 2026-05-16 03:57:58.866870

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7d1a3d8498c9"
down_revision: str | Sequence[str] | None = "7c7aa1861858"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("storage_key", sa.String(length=80), nullable=True),
    )
    op.execute(
        "UPDATE invoices "
        "SET storage_key = substring(file_path FROM '[^/\\\\]+$')"
    )
    op.alter_column("invoices", "storage_key", nullable=False)
    op.drop_column("invoices", "file_path")


def downgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("file_path", sa.String(length=512), nullable=True),
    )
    op.execute("UPDATE invoices SET file_path = './uploads/' || storage_key")
    op.alter_column("invoices", "file_path", nullable=False)
    op.drop_column("invoices", "storage_key")
