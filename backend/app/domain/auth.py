from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_HASHER = PasswordHasher()

DUMMY_PASSWORD_HASH: str = _HASHER.hash("dummy-for-timing-only")


def hash_password(plaintext: str) -> str:
    return _HASHER.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        return _HASHER.verify(hashed, plaintext)
    except VerificationError:
        return False
