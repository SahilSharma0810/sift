from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


AnomalySubtype = Literal["amount"]
AnomalyStatus = Literal["unreviewed", "acknowledged"]
AnomalySeverity = Literal["high", "medium", "low"]


class AnomalyMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float
    currency: str
    unit: str


class AnomalyHistoryPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float
    current: bool = False


class AnomalyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: AnomalySubtype
    status: AnomalyStatus
    vendor: str
    invoice_id: UUID
    detected_at: datetime
    headline: str
    sub: str
    z_score: float
    severity: AnomalySeverity
    metric: AnomalyMetric
    history: list[AnomalyHistoryPoint]
    avg: float
    diff: None = None
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None


class AnomalyCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    all: int
    unreviewed: int
    amount: int
    frequency: int
    pattern: int
    acknowledged: int


class AnomalyAggregates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_flagged_amount: float
    total_flagged_currency: str
    vendors_affected: int
    highest_severity_z: float | None = None
    highest_severity_vendor: str | None = None


class AnomaliesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anomalies: list[AnomalyOut]
    counts: AnomalyCounts
    aggregates: AnomalyAggregates


class BulkAcknowledgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anomaly_ids: list[str] = Field(min_length=1, max_length=200)


class BulkAcknowledgeFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    error: str


class BulkAcknowledgeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledged: list[AnomalyOut]
    failed: list[BulkAcknowledgeFailure]
