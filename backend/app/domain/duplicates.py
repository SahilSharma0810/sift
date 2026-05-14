"""Pure duplicate-detection logic per beat-2.

Two signals: content fingerprint (SHA-256 of file bytes, exact match) and
perceptual hash (imagehash.phash, Hamming distance over 64 bits). Combined
into a single (method, similarity) tuple by `classify_duplicate`.

NOTE: classify_duplicate may return "both" when both signals fire. The
DuplicateOfReason.match_method Literal in app/domain/models.py must include
"both" before this is consumed by extract_from_pdf (Day-2 Task D2-4).
"""

from __future__ import annotations

from typing import Literal

# 64-bit phash → distance <= 5 is the documented "visually identical" band.
PHASH_THRESHOLD = 5
PHASH_BITS = 64

MatchMethod = Literal["perceptual_hash", "content_fingerprint", "both"]


def hamming_distance(a: str, b: str) -> int:
    """Bit-level Hamming distance between two equal-length hex strings."""
    if len(a) != len(b):
        raise ValueError(f"hash length mismatch: {len(a)} vs {len(b)}")
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def phash_similarity(distance: int) -> float:
    """Normalize 0-64 Hamming distance into a 0-1 similarity score.

    Clamped so an out-of-range distance (e.g. computed against a hash of
    a different bit-size by mistake) cannot produce a negative similarity
    that would fail Pydantic validation on DuplicateOfReason.similarity.
    """
    return max(0.0, 1.0 - (distance / PHASH_BITS))


def classify_duplicate(
    *,
    content_match: bool,
    phash_distance: int | None,
) -> tuple[MatchMethod, float] | None:
    """Combine content + phash signals into (method, similarity) or None.

    - content_match True AND phash_distance <= threshold → "both", 1.0
    - content_match True alone → "content_fingerprint", 1.0
    - phash_distance <= threshold alone → "perceptual_hash", phash_similarity
    - neither → None
    """
    phash_match = phash_distance is not None and phash_distance <= PHASH_THRESHOLD
    if content_match and phash_match:
        return ("both", 1.0)
    if content_match:
        return ("content_fingerprint", 1.0)
    if phash_match and phash_distance is not None:
        return ("perceptual_hash", phash_similarity(phash_distance))
    return None
