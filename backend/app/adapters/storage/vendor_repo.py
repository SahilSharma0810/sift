"""Vendor repository. Imported by services, not by api directly."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Vendor

_PUNCT_RE = re.compile(r"[^\w\s]+")
_SPACES_RE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Lowercase + strip punctuation + collapse whitespace.

    The normalized form is the join key for upsert. The original is preserved
    in `vendors.name` (display value).
    """
    n = name.strip().lower()
    n = _PUNCT_RE.sub("", n)
    n = _SPACES_RE.sub(" ", n).strip()
    return n


def upsert_by_normalized_name(session: Session, *, name: str, tax_id: str | None = None) -> Vendor:
    """Insert if absent, return existing otherwise. Match by normalized_name."""
    normalized = normalize_name(name)
    existing = session.execute(
        select(Vendor).where(Vendor.normalized_name == normalized)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    vendor = Vendor(name=name, normalized_name=normalized, tax_id=tax_id)
    session.add(vendor)
    session.flush()
    return vendor
