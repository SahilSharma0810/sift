from __future__ import annotations

import pytest

from app.domain.auth import (
    DUMMY_PASSWORD_HASH,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_roundtrip(self) -> None:
        hashed = hash_password("correct-horse-battery-staple")
        assert verify_password("correct-horse-battery-staple", hashed) is True

    def test_hash_rejects_wrong_password(self) -> None:
        hashed = hash_password("correct-horse-battery-staple")
        assert verify_password("wrong-password", hashed) is False

    def test_dummy_hash_is_a_valid_argon2_hash(self) -> None:
        assert verify_password("anything", DUMMY_PASSWORD_HASH) is False

    def test_dummy_hash_takes_real_time_to_verify(self) -> None:
        import time

        start = time.perf_counter()
        verify_password("anything", DUMMY_PASSWORD_HASH)
        elapsed = time.perf_counter() - start
        assert elapsed > 0.001


import uuid


class TestCookieSigning:
    SECRET = "test-secret-do-not-use-in-prod"

    def test_sign_and_unsign_roundtrip(self) -> None:
        from app.domain.auth import sign_session_id, unsign_session_id

        sid = uuid.uuid4()
        signed = sign_session_id(sid, secret=self.SECRET)
        assert unsign_session_id(signed, secret=self.SECRET) == sid

    def test_unsign_rejects_tampered_value(self) -> None:
        from app.domain.auth import sign_session_id, unsign_session_id

        sid = uuid.uuid4()
        signed = sign_session_id(sid, secret=self.SECRET) + "x"
        assert unsign_session_id(signed, secret=self.SECRET) is None

    def test_unsign_rejects_wrong_secret(self) -> None:
        from app.domain.auth import sign_session_id, unsign_session_id

        sid = uuid.uuid4()
        signed = sign_session_id(sid, secret=self.SECRET)
        assert unsign_session_id(signed, secret="other-secret") is None

    def test_unsign_rejects_garbage(self) -> None:
        from app.domain.auth import unsign_session_id

        assert unsign_session_id("not-a-real-cookie", secret=self.SECRET) is None
        assert unsign_session_id("", secret=self.SECRET) is None


import uuid as _uuid

from pydantic import ValidationError


class TestDTOs:
    def test_login_in_accepts_valid(self) -> None:
        from app.domain.auth import LoginIn

        body = LoginIn(email="ap-clerk@sift.demo", password="secret", remember=True)
        assert body.email == "ap-clerk@sift.demo"
        assert body.password == "secret"
        assert body.remember is True

    def test_login_in_rejects_bad_email(self) -> None:
        from app.domain.auth import LoginIn

        with pytest.raises(ValidationError):
            LoginIn(email="not-an-email", password="secret", remember=False)

    def test_login_in_rejects_empty_password(self) -> None:
        from app.domain.auth import LoginIn

        with pytest.raises(ValidationError):
            LoginIn(email="ap-clerk@sift.demo", password="", remember=False)

    def test_clerk_out_shape(self) -> None:
        from app.domain.auth import ClerkOut

        out = ClerkOut(
            id=_uuid.uuid4(),
            email="ap-clerk@sift.demo",
            display_name=None,
        )
        assert out.display_name is None
