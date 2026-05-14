"""add raw_text + raw_text_tsv FTS to extractions

Day-4 FTS surface for the `raw_text fts_matches` clause in StructuredQuery.

- `raw_text` is a plain text column populated by the service layer from the
  concatenation of every extracted field value + line-item descriptions +
  tax-breakdown jurisdictions. Service does the concatenation so vision/stub
  paths produce identical FTS content shape.
- `raw_text_tsv` is a Postgres GENERATED column carrying the tsvector — the
  database maintains it automatically on insert/update. SQLAlchemy never
  writes to it.
- A GIN index on the tsvector makes the FTS path fast at any future scale.

Revision ID: 8c3c0a978b23
Revises: cf50d4a567b6
Create Date: 2026-05-14 17:11:11.713723

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8c3c0a978b23"
down_revision: str | Sequence[str] | None = "cf50d4a567b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain text column — service writes the concatenation.
    op.add_column("extractions", sa.Column("raw_text", sa.Text(), nullable=True))

    # Generated tsvector column. The expression keeps NULL-safe semantics so
    # rows with no raw_text yet end up with an empty tsvector (matches nothing).
    op.execute(
        """
        ALTER TABLE extractions
        ADD COLUMN raw_text_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('english', coalesce(raw_text, ''))) STORED;
        """
    )

    op.execute("CREATE INDEX ix_extractions_raw_text_tsv ON extractions USING gin (raw_text_tsv);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_extractions_raw_text_tsv;")
    op.execute("ALTER TABLE extractions DROP COLUMN IF EXISTS raw_text_tsv;")
    op.drop_column("extractions", "raw_text")
