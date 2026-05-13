"""Shared pytest fixtures.

`db_session` opens a SQLAlchemy session bound to the running Postgres
container and rolls back at the end of each test — so tests can write
freely without polluting state.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from app.db.session import SessionLocal


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()
