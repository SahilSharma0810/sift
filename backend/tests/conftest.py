"""Shared pytest fixtures.

`db_session` opens a SQLAlchemy session bound to the running Postgres
container and rolls back at the end of each test — so tests can write
freely without polluting state.

`patch_make_llm_client` is the test helper used to inject a mocked
LLMClient. After the provider-pattern refactor the extraction service
calls `make_llm_client(settings)`; tests patch that factory rather than
a concrete class so they don't depend on which impl is wired in.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

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


def make_llm_mock(
    *,
    header: Any = None,
    vision: Any = None,
    header_seq: list[Any] | None = None,
    vision_seq: list[Any] | None = None,
) -> MagicMock:
    """Build a MagicMock satisfying the LLMClient Protocol.

    `header` / `vision` set a single return_value. `header_seq` / `vision_seq`
    set a side_effect list for tests that exercise the cascade and need
    sequential responses across tiers.
    """
    mock = MagicMock()
    if header is not None:
        mock.extract_header.return_value = header
    if header_seq is not None:
        mock.extract_header.side_effect = header_seq
    if vision is not None:
        mock.extract_header_vision.return_value = vision
    if vision_seq is not None:
        mock.extract_header_vision.side_effect = vision_seq
    return mock


@contextmanager
def patch_make_llm_client(
    *,
    header: Any = None,
    vision: Any = None,
    header_seq: list[Any] | None = None,
    vision_seq: list[Any] | None = None,
) -> Generator[MagicMock, None, None]:
    """Patch `make_llm_client` to return a configured mock.

    Yields the underlying MagicMock so tests can assert on call counts / args.
    """
    mock = make_llm_mock(header=header, vision=vision, header_seq=header_seq, vision_seq=vision_seq)
    with patch("app.services.extraction_service.make_llm_client", return_value=mock):
        yield mock
