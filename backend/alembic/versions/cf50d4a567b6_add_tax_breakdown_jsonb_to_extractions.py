"""add tax_breakdown jsonb to extractions

Revision ID: cf50d4a567b6
Revises: 74d06e0c35fc
Create Date: 2026-05-14 17:00:15.103421

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "cf50d4a567b6"
down_revision: str | Sequence[str] | None = "74d06e0c35fc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:

    op.add_column(
        "extractions",
        sa.Column(
            "tax_breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

def downgrade() -> None:

    op.drop_column("extractions", "tax_breakdown")

