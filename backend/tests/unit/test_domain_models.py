"""Smoke tests on domain Pydantic models — proves shapes + discriminator.

These are the fastest tests in the suite (<10ms each) and exercise the
locked JSONB shapes from PLAN.md. The eval harness will sit on this seam.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from app.domain.models import (
    AnomalyReason,
    DuplicateOfReason,
    ExtractedField,
    ExtractionFailedReason,
    MathFailsReason,
    TriageReason,
    VendorMemory,
    VendorMemoryRule,
    VendorMemoryStats,
)


class TestExtractedField:
    def test_minimal_field(self) -> None:
        f = ExtractedField(value="Acme", confidence=0.92, source="pymupdf+haiku")
        assert f.value == "Acme"
        assert f.bbox is None
        assert f.page == 0

    def test_with_bbox(self) -> None:
        f = ExtractedField(
            value=1180.0,
            bbox=(120.0, 80.0, 340.0, 110.0),
            page=0,
            confidence=0.95,
            source="claude-vision",
        )
        assert f.bbox == (120.0, 80.0, 340.0, 110.0)

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedField(value="x", confidence=1.5, source="pymupdf+haiku")

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedField(
                value="x",
                confidence=0.5,
                source="pymupdf+haiku",
                rogue_key="oops",
            )


class TestTriageReasons:
    def test_math_fails(self) -> None:
        r = MathFailsReason(subtotal=1000.0, tax=180.0, total=1180.40, delta=0.40)
        assert r.type == "math_fails"

    def test_anomaly(self) -> None:
        r = AnomalyReason(field="total", vendor_mean=1180.0, vendor_std=142.5, z_score=12.4)
        assert r.type == "anomaly"

    def test_duplicate_of(self) -> None:
        r = DuplicateOfReason(
            invoice_id=uuid.uuid4(), similarity=0.98, match_method="perceptual_hash"
        )
        assert r.match_method == "perceptual_hash"

    def test_extraction_failed(self) -> None:
        r = ExtractionFailedReason(stage="cascade_exhausted", detail="x")
        assert r.stage == "cascade_exhausted"


class TestTriageReasonDiscriminator:
    """Discriminated union dispatch — drives the frontend ReasonCard map."""

    def test_dispatch_by_type(self) -> None:
        adapter = TypeAdapter(TriageReason)
        parsed = adapter.validate_python(
            {
                "type": "math_fails",
                "subtotal": 100,
                "tax": 18,
                "total": 118.40,
                "delta": 0.40,
            }
        )
        assert isinstance(parsed, MathFailsReason)

    def test_unknown_type_rejected(self) -> None:
        adapter = TypeAdapter(TriageReason)
        with pytest.raises(ValidationError):
            adapter.validate_python({"type": "made_up", "field": "x"})


class TestVendorMemory:
    def test_default_empty(self) -> None:
        m = VendorMemory()
        assert m.rules == []
        assert m.stats.total_seen == 0

    def test_with_rule(self) -> None:
        m = VendorMemory(
            rules=[
                VendorMemoryRule(
                    field="invoice_date",
                    pattern_type="date_format",
                    value="DD/MM/YYYY",
                    source_correction_id=uuid.uuid4(),
                    applied_count=3,
                    first_learned_at=datetime.now(),
                )
            ],
            stats=VendorMemoryStats(total_seen=6, avg_total=1180.0, std_total=142.5),
        )
        assert len(m.rules) == 1
        assert m.stats.avg_total == 1180.0
