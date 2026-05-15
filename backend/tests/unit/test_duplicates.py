"""Duplicate detection — Hamming distance over 64-bit perceptual hashes,
similarity normalization, and signal combination with content fingerprint.

Hash strings come from imagehash.phash() which produces a 16-char hex string.
"""

from __future__ import annotations

import pytest

from app.domain.duplicates import (
    PHASH_THRESHOLD,
    classify_duplicate,
    hamming_distance,
    phash_similarity,
)

class TestHammingDistance:
    def test_identical(self) -> None:
        assert hamming_distance("ffffffffffffffff", "ffffffffffffffff") == 0

    def test_one_bit(self) -> None:

        assert hamming_distance("ffffffffffffffff", "fffffffffffffffe") == 1

    def test_full_difference(self) -> None:
        assert hamming_distance("ffffffffffffffff", "0000000000000000") == 64

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="length mismatch"):
            hamming_distance("ffff", "ffffffffffffffff")

class TestPhashSimilarity:
    def test_identical_is_one(self) -> None:
        assert phash_similarity(0) == 1.0

    def test_at_threshold(self) -> None:

        assert abs(phash_similarity(5) - (1 - 5 / 64)) < 1e-9

    def test_far_apart(self) -> None:
        assert phash_similarity(32) == 0.5

class TestClassifyDuplicate:
    def test_content_match_only_far_phash(self) -> None:

        assert classify_duplicate(content_match=True, phash_distance=20) == (
            "content_fingerprint",
            1.0,
        )

    def test_both_signals_fire(self) -> None:

        assert classify_duplicate(content_match=True, phash_distance=2) == ("both", 1.0)

    def test_phash_only(self) -> None:
        method, sim = classify_duplicate(content_match=False, phash_distance=3)
        assert method == "perceptual_hash"
        assert abs(sim - (1 - 3 / 64)) < 1e-9

    def test_phash_over_threshold_no_match(self) -> None:
        assert classify_duplicate(content_match=False, phash_distance=10) is None

    def test_neither_no_match(self) -> None:
        assert classify_duplicate(content_match=False, phash_distance=None) is None

    def test_phash_at_threshold_boundary(self) -> None:

        method, _sim = classify_duplicate(content_match=False, phash_distance=PHASH_THRESHOLD)
        assert method == "perceptual_hash"

    def test_phash_just_over_threshold_no_match(self) -> None:

        assert classify_duplicate(content_match=False, phash_distance=PHASH_THRESHOLD + 1) is None
