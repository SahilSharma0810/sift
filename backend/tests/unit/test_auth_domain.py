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
