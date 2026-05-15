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


_PRESERVE_TOKENS = frozenset(
    {
        "LLC", "INC", "LTD", "PLC", "LLP", "CORP", "LP", "CO",
        "GMBH", "AG", "KG", "SE", "SA", "SARL", "BV", "NV",
        "PTY", "PTE", "KK", "AB",
        "USA", "UK", "EU", "US", "UAE",
    }
)


def _is_screaming_caps(name: str) -> bool:
    letters = [c for c in name if c.isalpha()]
    if len(letters) < 6:
        return False
    return all(c.isupper() for c in letters)


def display_name(name: str) -> str:
    """De-shout an all-caps vendor name; otherwise pass through unchanged.

    The LLM often extracts vendor names verbatim from stylized letterheads
    ("MANAGEMENT SCIENCE ASSOCIATES, INC."). Storing that verbatim means
    the AP clerk reads it in all-caps forever. This title-cases long
    words but preserves a curated set of legal suffixes and country
    codes (LLC, INC, GMBH, USA, etc.) so they remain readable.
    """
    if not _is_screaming_caps(name):
        return name
    out: list[str] = []
    for word in name.split(" "):
        bare = word.rstrip(".,;:").upper()
        if bare in _PRESERVE_TOKENS:
            out.append(word)
            continue
        out.append(word.capitalize())
    return " ".join(out)


def upsert_by_normalized_name(session: Session, *, name: str, tax_id: str | None = None) -> Vendor:
    """Insert if absent, return existing otherwise. Match by normalized_name."""
    normalized = normalize_name(name)
    existing = session.execute(
        select(Vendor).where(Vendor.normalized_name == normalized)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    vendor = Vendor(name=display_name(name), normalized_name=normalized, tax_id=tax_id)
    session.add(vendor)
    session.flush()
    return vendor
