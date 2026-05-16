"""merge api_usage and storage_key heads

Revision ID: 31913f6a10d6
Revises: 7d1a3d8498c9, a1b8c39e7f02
Create Date: 2026-05-16 11:46:31.150740

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "31913f6a10d6"
down_revision: str | Sequence[str] | None = ("7d1a3d8498c9", "a1b8c39e7f02")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
