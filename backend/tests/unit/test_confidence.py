"""Composite Confidence module per ADR-0003.

Tests the unified `compute_confidence` entry point: structural + history
+ agreement override into a single ConfidenceReport with per-field
provenance.

The lower-level primitives (compute_structural_scores,
compute_composite_confidence, apply_agreement_overrides) have their own
unit tests in test_validators.py and test_scoring.py - these tests focus
on the integration into a single artifact and the trace shape.
"""

from __future__ import annotations

from app.domain.confidence import (
    ConfidenceReport,
    FieldConfidence,
    compute_confidence,
    compute_history_scores_from_stats,
)

CLEAN_FIELDS = {
    "vendor_name": "Vega Logistics",
    "invoice_number": "INV-2026-0042",
    "invoice_date": "2026-05-13",
    "subtotal": 1000.0,
    "tax": 180.0,
    "total": 1180.0,
    "currency": "USD",
}

class TestComputeConfidence:
    def test_cold_start_vendor_returns_history_default(self) -> None:
        """No vendor stats -> history component absent, composite floors
        to the 0.85 cold-start default per ADR-0003."""
        report = compute_confidence(extracted_fields=CLEAN_FIELDS, vendor_stats=None)
        assert isinstance(report, ConfidenceReport)
        assert report.has_vendor_history is False

        assert report.composite["total"] == 0.85
        assert report.fields["total"].history is None
        assert report.fields["total"].structural == 1.0

    def test_math_failure_pins_amounts_at_floor(self) -> None:
        """ADR-0003: math fail -> amount fields' structural score is 0.2.
        Composite must respect that floor even with perfect history."""
        broken = {**CLEAN_FIELDS, "total": 1500.0}
        report = compute_confidence(extracted_fields=broken, vendor_stats=None)
        assert report.math_passed is False
        assert report.composite["total"] == 0.2
        assert report.fields["total"].structural == 0.2

    def test_vendor_history_with_outlier_drops_total_history(self) -> None:
        """Total far from vendor mean -> history bucket 0.3 -> composite 0.3."""
        stats = {
            "total_seen": 10,
            "avg_total": 1180.0,
            "std_total": 50.0,
        }
        outlier = {**CLEAN_FIELDS, "total": 5000.0}
        report = compute_confidence(extracted_fields=outlier, vendor_stats=stats)
        assert report.has_vendor_history is True

    def test_vendor_history_governs_when_math_passes(self) -> None:
        """Math passes -> structural is 1.0 for total; vendor history outlier
        drops the composite to the history bucket."""
        stats = {
            "total_seen": 10,
            "avg_total": 1180.0,
            "std_total": 50.0,
        }

        outlier = {
            **CLEAN_FIELDS,
            "subtotal": 4500.0,
            "tax": 500.0,
            "total": 5000.0,
        }
        report = compute_confidence(extracted_fields=outlier, vendor_stats=stats)
        assert report.math_passed is True
        assert report.composite["total"] == 0.3
        assert report.fields["total"].history == 0.3
        assert report.fields["total"].structural == 1.0

    def test_agreement_overrides_replace_disputed_composite(self) -> None:
        """Cascade dispute -> composite for that field becomes min(prior, 0.3)."""
        overrides = {"total": 0.3}
        report = compute_confidence(
            extracted_fields=CLEAN_FIELDS,
            vendor_stats=None,
            agreement_overrides=overrides,
        )

        assert report.composite["total"] == 0.3
        assert report.fields["total"].agreement_override == 0.3

    def test_per_field_trace_components(self) -> None:
        """ConfidenceReport.fields surfaces structural / history / override per field."""
        stats = {
            "total_seen": 10,
            "avg_total": 1180.0,
            "std_total": 50.0,
        }
        report = compute_confidence(
            extracted_fields=CLEAN_FIELDS,
            vendor_stats=stats,
            agreement_overrides={"vendor_name": 0.3},
        )
        total = report.fields["total"]
        assert isinstance(total, FieldConfidence)
        assert total.structural == 1.0
        assert total.history == 1.0
        assert total.agreement_override is None
        vendor = report.fields["vendor_name"]
        assert vendor.agreement_override == 0.3

class TestComputeHistoryScoresFromStats:
    def test_empty_stats_returns_empty(self) -> None:
        assert compute_history_scores_from_stats(
            extracted_fields={"total": 1000.0}, vendor_stats=None
        ) == {}
        assert compute_history_scores_from_stats(
            extracted_fields={"total": 1000.0}, vendor_stats={}
        ) == {}

    def test_low_sample_size_suppresses_history(self) -> None:
        """Fewer than MIN_HISTORY_SAMPLES seen -> no history score yet."""
        stats = {"total_seen": 2, "avg_total": 1000.0, "std_total": 50.0}
        out = compute_history_scores_from_stats(
            extracted_fields={"total": 1000.0}, vendor_stats=stats
        )
        assert out == {}

    def test_z_score_bucketing(self) -> None:
        stats = {"total_seen": 10, "avg_total": 1000.0, "std_total": 100.0}

        assert compute_history_scores_from_stats(
            extracted_fields={"total": 1050.0}, vendor_stats=stats
        )["total"] == 1.0

        assert compute_history_scores_from_stats(
            extracted_fields={"total": 1150.0}, vendor_stats=stats
        )["total"] == 0.85

        assert compute_history_scores_from_stats(
            extracted_fields={"total": 1250.0}, vendor_stats=stats
        )["total"] == 0.6

        assert compute_history_scores_from_stats(
            extracted_fields={"total": 1500.0}, vendor_stats=stats
        )["total"] == 0.3

    def test_zero_std_skips_field(self) -> None:
        """A vendor with stddev 0 means we have no spread signal — skip."""
        stats = {"total_seen": 10, "avg_total": 1000.0, "std_total": 0.0}
        out = compute_history_scores_from_stats(
            extracted_fields={"total": 1000.0}, vendor_stats=stats
        )
        assert out == {}
