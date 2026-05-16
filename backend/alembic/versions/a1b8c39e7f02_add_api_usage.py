"""add api_usage

Revision ID: a1b8c39e7f02
Revises: 7c7aa1861858
Create Date: 2026-05-16 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b8c39e7f02"
down_revision: str | Sequence[str] | None = "7c7aa1861858"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_usage",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("spec_name", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "cache_creation_input_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "cache_read_input_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_usage_created_at", "api_usage", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_api_usage_created_at", table_name="api_usage")
    op.drop_table("api_usage")
