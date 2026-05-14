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
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.session import engine


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Per-test session bound to a SAVEPOINT inside an outer transaction.

    Service-layer `session.commit()` calls only commit the savepoint; the
    outer transaction stays open. On teardown we roll the outer transaction
    back so nothing this test wrote persists to the dev database. The
    `after_transaction_end` listener restarts the savepoint after each
    inner commit so the same session stays usable across multiple service
    calls within one test.
    """
    connection = engine.connect()
    outer_txn = connection.begin()
    session = Session(bind=connection, autocommit=False, autoflush=False, expire_on_commit=False)
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(_session: Session, transaction) -> None:
        nonlocal nested
        if transaction.nested and not transaction._parent.nested:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        if outer_txn.is_active:
            outer_txn.rollback()
        connection.close()


def make_llm_mock(
    *,
    header: Any = None,
    vision: Any = None,
    header_seq: list[Any] | None = None,
    vision_seq: list[Any] | None = None,
    line_items: Any = None,
) -> MagicMock:
    """Build a MagicMock satisfying the LLMClient Protocol.

    `header` / `vision` set a single return_value. `header_seq` / `vision_seq`
    set a side_effect list for tests that exercise the cascade and need
    sequential responses across tiers. `line_items` sets the return_value
    for `extract_line_items`; if omitted, a default empty LineItemsResult
    is wired in so existing tests keep working without specifying line-item
    behavior explicitly.
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
    if line_items is None:
        from app.adapters.llm_client import LineItemsResult

        line_items = LineItemsResult(
            items=[],
            model="stub",
            prompt_hash="stub",
            schema_hash="stub",
            usage={
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        )
    mock.extract_line_items.return_value = line_items
    return mock


@contextmanager
def patch_make_llm_client(
    *,
    header: Any = None,
    vision: Any = None,
    header_seq: list[Any] | None = None,
    vision_seq: list[Any] | None = None,
    line_items: Any = None,
) -> Generator[MagicMock, None, None]:
    """Patch `make_llm_client` to return a configured mock.

    Yields the underlying MagicMock so tests can assert on call counts / args.
    """
    mock = make_llm_mock(
        header=header,
        vision=vision,
        header_seq=header_seq,
        vision_seq=vision_seq,
        line_items=line_items,
    )
    with patch("app.services.extraction_service.make_llm_client", return_value=mock):
        yield mock
