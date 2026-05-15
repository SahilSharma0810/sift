"""Anomaly detection per PLAN.md beat-2: Z-score on numeric fields vs vendor stats."""

from __future__ import annotations

from app.domain.anomalies import detect_anomalies

class TestDetectAnomalies:
    def test_within_one_sigma_no_anomaly(self) -> None:
        anomalies = detect_anomalies(
            fields={"total": 1200.0},
            stats={"total_seen": 10, "avg_total": 1180.0, "std_total": 50.0},
        )
        assert anomalies == []

    def test_three_sigma_is_anomaly(self) -> None:
        anomalies = detect_anomalies(
            fields={"total": 14231.0},
            stats={"total_seen": 10, "avg_total": 1180.0, "std_total": 100.0},
        )
        assert len(anomalies) == 1
        a = anomalies[0]
        assert a["field"] == "total"
        assert a["vendor_mean"] == 1180.0
        assert a["vendor_std"] == 100.0
        assert a["z_score"] > 3.0

    def test_no_stats_skips_check(self) -> None:
        assert (
            detect_anomalies(
                fields={"total": 14231.0},
                stats={"total_seen": 0, "avg_total": 0.0, "std_total": 0.0},
            )
            == []
        )

    def test_zero_std_skips_check(self) -> None:

        assert (
            detect_anomalies(
                fields={"total": 14231.0},
                stats={"total_seen": 10, "avg_total": 1180.0, "std_total": 0.0},
            )
            == []
        )

    def test_low_count_skips_check(self) -> None:

        assert (
            detect_anomalies(
                fields={"total": 14231.0},
                stats={"total_seen": 2, "avg_total": 1180.0, "std_total": 50.0},
            )
            == []
        )

    def test_only_total_checked_in_day2(self) -> None:

        anomalies = detect_anomalies(
            fields={"total": 1180.0, "subtotal": 9999.0},
            stats={"total_seen": 10, "avg_total": 1180.0, "std_total": 50.0},
        )
        assert anomalies == []

    def test_missing_field_skips(self) -> None:

        assert (
            detect_anomalies(
                fields={},
                stats={"total_seen": 10, "avg_total": 1180.0, "std_total": 50.0},
            )
            == []
        )

    def test_none_value_skips(self) -> None:

        assert (
            detect_anomalies(
                fields={"total": None},
                stats={"total_seen": 10, "avg_total": 1180.0, "std_total": 50.0},
            )
            == []
        )

    def test_non_numeric_value_skips(self) -> None:

        assert (
            detect_anomalies(
                fields={"total": "N/A"},
                stats={"total_seen": 10, "avg_total": 1180.0, "std_total": 50.0},
            )
            == []
        )
