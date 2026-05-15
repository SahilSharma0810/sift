from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.adapters.storage.user_repo import (
    get_by_email,
    update_last_login,
    upsert_demo_user,
)
from app.domain.auth import hash_password, verify_password


class TestUserRepo:
    def test_upsert_creates_when_absent(self, db_session: Session) -> None:
        u = upsert_demo_user(
            db_session,
            email="ap-clerk@example.test",
            password="secret-1",
        )
        assert u.id is not None
        assert verify_password("secret-1", u.password_hash)

    def test_upsert_is_idempotent_and_does_not_change_password(
        self, db_session: Session
    ) -> None:
        u1 = upsert_demo_user(
            db_session,
            email="ap-clerk@example.test",
            password="secret-1",
        )
        u2 = upsert_demo_user(
            db_session,
            email="ap-clerk@example.test",
            password="secret-2-different",
        )
        assert u1.id == u2.id
        assert verify_password("secret-1", u2.password_hash)
        assert not verify_password("secret-2-different", u2.password_hash)

    def test_get_by_email_is_case_insensitive(self, db_session: Session) -> None:
        upsert_demo_user(
            db_session,
            email="MixedCase@example.test",
            password="x",
        )
        found = get_by_email(db_session, "mixedcase@example.test")
        assert found is not None
        assert str(found.email).lower() == "mixedcase@example.test"

    def test_get_by_email_returns_none_when_absent(self, db_session: Session) -> None:
        assert get_by_email(db_session, "nobody@example.test") is None

    def test_update_last_login_writes_a_timestamp(self, db_session: Session) -> None:
        u = upsert_demo_user(
            db_session,
            email="lastlogin@example.test",
            password="x",
        )
        assert u.last_login_at is None
        update_last_login(db_session, user_id=u.id)
        db_session.refresh(u)
        assert u.last_login_at is not None
        assert (datetime.now(UTC) - u.last_login_at) < timedelta(seconds=5)
