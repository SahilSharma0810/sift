"""Integration test isolation — savepoint-wrapped sessions for API tests.

Background: most integration tests use the function-scoped `db_session`
fixture from the root conftest, which rolls back at the end of the test.
But API tests use `fastapi.testclient.TestClient`, and TestClient drives
real HTTP requests through FastAPI's dependency system. The `get_session`
dependency yields a *new* Session that the service layer commits — that
commit lands in the dev database and never gets rolled back.

The result was 15+ rows of test pollution accumulating in the dev DB
across runs. This conftest fixes it with the canonical SQLAlchemy
"join an external transaction" pattern:

  1. Open a connection + begin an outer transaction
  2. Bind a Session to that connection + begin a nested SAVEPOINT
  3. Override FastAPI's `get_session` dependency to yield this Session
  4. When the service calls `session.commit()`, only the SAVEPOINT
     commits — the outer transaction is still uncommitted
  5. The `after_transaction_end` listener restarts the savepoint so
     subsequent service-layer commits keep working within the same test
  6. On teardown, rollback the outer transaction → nothing persists

Tests get a `api_client` fixture (a configured TestClient) instead of
constructing one themselves. The cleanup is automatic.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.session import engine, get_session
from app.main import app

@pytest.fixture
def api_client() -> Generator[TestClient, None, None]:
    """TestClient bound to an isolated, rolled-back session.

    Service-layer `session.commit()` calls inside the request handler only
    commit the savepoint, which is discarded at fixture teardown. No data
    written by this test persists to the dev database.
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

    def _override_get_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = _override_get_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)
        session.close()
        if outer_txn.is_active:
            outer_txn.rollback()
        connection.close()
