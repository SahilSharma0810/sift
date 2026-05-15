"""Anomaly detection per PLAN.md beat-2: Z-score on numeric fields vs vendor stats."""

from __future__ import annotations

from app.domain.anomalies import detect_anomalies
from app.domain.models import VendorMemoryStats


def _stats(*, n: int, mean: float, std: float) -> VendorMemoryStats:
    return VendorMemoryStats(total_seen=n, avg_total=mean, std_total=std)


class TestDetectAnomalies:
    def test_within_one_sigma_no_anomaly(self) -> None:
        anomalies = detect_anomalies(
            fields={"total": 1200.0},
            stats=_stats(n=10, mean=1180.0, std=50.0),
        )
        assert anomalies == []

    def test_three_sigma_is_anomaly(self) -> None:
        anomalies = detect_anomalies(
            fields={"total": 14231.0},
            stats=_stats(n=10, mean=1180.0, std=100.0),
        )
        assert len(anomalies) == 1
        a = anomalies[0]
        assert a.field == "total"
        assert a.vendor_mean == 1180.0
        assert a.vendor_std == 100.0
        assert a.z_score > 3.0

    def test_no_stats_skips_check(self) -> None:
        assert (
            detect_anomalies(
                fields={"total": 14231.0},
                stats=_stats(n=0, mean=0.0, std=0.0),
            )
            == []
        )

    def test_zero_std_skips_check(self) -> None:
        assert (
            detect_anomalies(
                fields={"total": 14231.0},
                stats=_stats(n=10, mean=1180.0, std=0.0),
            )
            == []
        )

    def test_low_count_skips_check(self) -> None:
        assert (
            detect_anomalies(
                fields={"total": 14231.0},
                stats=_stats(n=2, mean=1180.0, std=50.0),
            )
            == []
        )

    def test_only_total_checked_in_day2(self) -> None:
        anomalies = detect_anomalies(
            fields={"total": 1180.0, "subtotal": 9999.0},
            stats=_stats(n=10, mean=1180.0, std=50.0),
        )
        assert anomalies == []

    def test_missing_field_skips(self) -> None:
        assert (
            detect_anomalies(
                fields={},
                stats=_stats(n=10, mean=1180.0, std=50.0),
            )
            == []
        )

    def test_none_value_skips(self) -> None:
        assert (
            detect_anomalies(
                fields={"total": None},
                stats=_stats(n=10, mean=1180.0, std=50.0),
            )
            == []
        )

    def test_non_numeric_value_skips(self) -> None:
        assert (
            detect_anomalies(
                fields={"total": "N/A"},
                stats=_stats(n=10, mean=1180.0, std=50.0),
            )
            == []
        )


class TestDetectAnomaliesWithAcks:
    def test_acked_value_within_tolerance_skips_anomaly(self) -> None:
        anomalies = detect_anomalies(
            fields={"total": 34062.50},
            stats=_stats(n=10, mean=7900.0, std=1500.0),
            acknowledged_outliers={"total": [{"value": 33500.00}]},
        )
        assert anomalies == []

    def test_acked_value_outside_tolerance_still_emits_anomaly(self) -> None:
        anomalies = detect_anomalies(
            fields={"total": 50000.00},
            stats=_stats(n=10, mean=7900.0, std=1500.0),
            acknowledged_outliers={"total": [{"value": 34000.00}]},
        )
        assert len(anomalies) == 1
        assert anomalies[0].z_score > 3.0

    def test_empty_acknowledged_outliers_preserves_prior_behavior(self) -> None:
        anomalies = detect_anomalies(
            fields={"total": 14231.0},
            stats=_stats(n=10, mean=1180.0, std=100.0),
            acknowledged_outliers={},
        )
        assert len(anomalies) == 1
