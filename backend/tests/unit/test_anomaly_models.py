from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.anomalies_models import (
    AnomaliesResponse,
    AnomalyAggregates,
    AnomalyCounts,
    AnomalyHistoryPoint,
    AnomalyMetric,
    AnomalyOut,
    BulkAcknowledgeFailure,
    BulkAcknowledgeIn,
    BulkAcknowledgeOut,
)


def _sample_anomaly() -> AnomalyOut:
    return AnomalyOut(
        id="00000000-0000-0000-0000-000000000001:amount:total",
        type="amount",
        status="unreviewed",
        vendor="Halcyon Software",
        invoice_id=uuid4(),
        detected_at=datetime.now(UTC),
        headline="$34,062.50 invoice",
        sub="4.2σ above rolling average of $7,900",
        z_score=4.2,
        severity="high",
        metric=AnomalyMetric(value=34062.50, currency="USD", unit="$"),
        history=[
            AnomalyHistoryPoint(value=7800.0),
            AnomalyHistoryPoint(value=34062.50, current=True),
        ],
        avg=7900.0,
    )


class TestAnomalyOut:
    def test_round_trip(self) -> None:
        a = _sample_anomaly()
        loaded = AnomalyOut.model_validate(a.model_dump(mode="json"))
        assert loaded.id == a.id
        assert loaded.severity == "high"
        assert loaded.metric.currency == "USD"

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            AnomalyOut.model_validate({"foo": "bar"})


class TestBulkAcknowledgeIn:
    def test_accepts_valid(self) -> None:
        body = BulkAcknowledgeIn(anomaly_ids=["a:amount:total"])
        assert len(body.anomaly_ids) == 1

    def test_rejects_empty_list(self) -> None:
        with pytest.raises(ValidationError):
            BulkAcknowledgeIn(anomaly_ids=[])

    def test_rejects_too_many(self) -> None:
        with pytest.raises(ValidationError):
            BulkAcknowledgeIn(anomaly_ids=["x"] * 201)


class TestAggregatesResponse:
    def test_aggregates_round_trip(self) -> None:
        agg = AnomalyAggregates(
            total_flagged_amount=34062.50,
            total_flagged_currency="USD",
            vendors_affected=1,
            highest_severity_z=4.2,
            highest_severity_vendor="Halcyon Software",
        )
        loaded = AnomalyAggregates.model_validate(agg.model_dump())
        assert loaded.highest_severity_z == 4.2

    def test_response_round_trip(self) -> None:
        resp = AnomaliesResponse(
            anomalies=[_sample_anomaly()],
            counts=AnomalyCounts(
                all=1, unreviewed=1, amount=1, frequency=0, pattern=0, acknowledged=0
            ),
            aggregates=AnomalyAggregates(
                total_flagged_amount=34062.50,
                total_flagged_currency="USD",
                vendors_affected=1,
                highest_severity_z=4.2,
                highest_severity_vendor="Halcyon Software",
            ),
        )
        loaded = AnomaliesResponse.model_validate(resp.model_dump(mode="json"))
        assert loaded.counts.unreviewed == 1


class TestBulkOut:
    def test_partial_success_shape(self) -> None:
        out = BulkAcknowledgeOut(
            acknowledged=[_sample_anomaly()],
            failed=[BulkAcknowledgeFailure(id="bad:amount:total", error="not_found")],
        )
        assert len(out.acknowledged) == 1
        assert out.failed[0].error == "not_found"
