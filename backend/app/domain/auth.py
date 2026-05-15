from __future__ import annotations

import uuid
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel, ConfigDict, EmailStr, Field

_HASHER = PasswordHasher()
_COOKIE_SALT = "sift.auth.session"

DUMMY_PASSWORD_HASH: str = _HASHER.hash("dummy-for-timing-only")


def hash_password(plaintext: str) -> str:
    return _HASHER.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        return _HASHER.verify(hashed, plaintext)
    except VerificationError:
        return False


def sign_session_id(session_id: uuid.UUID, *, secret: str) -> str:
    serializer = URLSafeSerializer(secret, salt=_COOKIE_SALT)
    return serializer.dumps(str(session_id))


def unsign_session_id(value: str, *, secret: str) -> uuid.UUID | None:
    if not value:
        return None
    serializer = URLSafeSerializer(secret, salt=_COOKIE_SALT)
    try:
        raw = serializer.loads(value)
    except BadSignature:
        return None
    try:
        return uuid.UUID(raw)
    except (ValueError, TypeError):
        return None


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1)
    remember: bool = False


class ClerkOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str
    display_name: str | None = None
