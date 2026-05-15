from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.adapters.storage.session_repo import (
    create as create_session,
    delete as delete_session,
    get_active as get_active_session,
    touch_last_seen,
)
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


class TestSessionRepo:
    def _user(self, db_session: Session):
        return upsert_demo_user(
            db_session,
            email="sess-tests@example.test",
            password="x",
        )

    def test_create_inserts_a_row(self, db_session: Session) -> None:
        user = self._user(db_session)
        expires = datetime.now(UTC) + timedelta(hours=12)
        s = create_session(
            db_session,
            user_id=user.id,
            expires_at=expires,
            user_agent="pytest/1.0",
        )
        assert s.id is not None
        assert s.user_id == user.id
        assert s.expires_at == expires
        assert s.user_agent == "pytest/1.0"

    def test_get_active_returns_unexpired(self, db_session: Session) -> None:
        user = self._user(db_session)
        s = create_session(
            db_session,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            user_agent=None,
        )
        found = get_active_session(db_session, s.id)
        assert found is not None
        assert found.id == s.id

    def test_get_active_returns_none_for_expired(self, db_session: Session) -> None:
        user = self._user(db_session)
        s = create_session(
            db_session,
            user_id=user.id,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
            user_agent=None,
        )
        assert get_active_session(db_session, s.id) is None

    def test_get_active_returns_none_for_unknown_id(self, db_session: Session) -> None:
        assert get_active_session(db_session, uuid4()) is None

    def test_delete_removes_row_and_is_idempotent(self, db_session: Session) -> None:
        user = self._user(db_session)
        s = create_session(
            db_session,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            user_agent=None,
        )
        delete_session(db_session, s.id)
        assert get_active_session(db_session, s.id) is None
        delete_session(db_session, s.id)

    def test_touch_last_seen_updates_timestamp(self, db_session: Session) -> None:
        user = self._user(db_session)
        s = create_session(
            db_session,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            user_agent=None,
        )
        original = s.last_seen_at
        touch_last_seen(db_session, s.id)
        db_session.refresh(s)
        assert s.last_seen_at > original


class TestSeedDemoUser:
    def test_seed_demo_user_is_idempotent_and_does_not_change_password(
        self, db_session: Session
    ) -> None:
        from scripts.seed_demo import seed_demo_user
        from app.config import get_settings

        settings = get_settings()
        u1 = seed_demo_user(db_session)
        assert u1.email == settings.demo_email
        assert verify_password(settings.demo_password, u1.password_hash)

        u2 = seed_demo_user(db_session)
        assert u1.id == u2.id
