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
def _api_session() -> Generator[Session, None, None]:
    """Shared session for both API handler and test-side seeding."""
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


@pytest.fixture
def db_session(_api_session: Session) -> Session:
    """Override root db_session so API tests seed into the same connection."""
    return _api_session


@pytest.fixture
def api_client(_api_session: Session) -> Generator[TestClient, None, None]:
    """TestClient bound to an isolated session and authenticated as a test clerk."""
    from datetime import UTC, datetime, timedelta

    from app.adapters.storage.session_repo import create as create_session
    from app.adapters.storage.user_repo import upsert_demo_user
    from app.config import get_settings
    from app.domain.auth import sign_session_id

    def _override_get_session() -> Generator[Session, None, None]:
        yield _api_session

    app.dependency_overrides[get_session] = _override_get_session
    try:
        with TestClient(app) as client:
            user = upsert_demo_user(
                _api_session,
                email="test-clerk@sift.demo",
                password="test-password",
            )
            auth_session = create_session(
                _api_session,
                user_id=user.id,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                user_agent="pytest",
            )
            signed = sign_session_id(auth_session.id, secret=get_settings().secret_key)
            client.cookies.set("sift_session", signed)
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.fixture
def unauthed_client(_api_session: Session) -> Generator[TestClient, None, None]:
    """Bare TestClient with the same session override but no auth cookie."""
    def _override_get_session() -> Generator[Session, None, None]:
        yield _api_session

    app.dependency_overrides[get_session] = _override_get_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)
