"""Anomaly detection for extracted invoice fields.

Pure: no IO. Compares numeric fields against per-vendor stats (mean + std)
and emits `AnomalyReason` payloads matching the discriminated union in
app.domain.models.
"""

from __future__ import annotations

from typing import TypedDict

from app.domain.models import AnomalyReason, FieldValue, VendorMemoryStats

ANOMALY_FIELDS = ("total",)

MIN_VENDOR_HISTORY = 3

Z_THRESHOLD = 3.0

ACK_TOLERANCE_FRAC = 0.10


class AcknowledgedOutlier(TypedDict, total=False):
    value: float


def detect_anomalies(
    *,
    fields: dict[str, FieldValue],
    stats: VendorMemoryStats,
    acknowledged_outliers: dict[str, list[AcknowledgedOutlier]] | None = None,
) -> list[AnomalyReason]:
    """Return `AnomalyReason` payloads for fields outside +-3 sigma of vendor history.

    Skips the check when vendor history is too small or std is degenerate.
    `acknowledged_outliers` maps field name → list of prior-acked values for
    that field. A new value within ACK_TOLERANCE_FRAC of any acked value is
    treated as a known outlier and is NOT emitted as an anomaly.
    """
    out: list[AnomalyReason] = []
    if stats.total_seen < MIN_VENDOR_HISTORY:
        return out

    acks = acknowledged_outliers or {}
    value = fields.get("total")
    if value is None or stats.std_total <= 0:
        return out
    try:
        x = float(value)
    except (TypeError, ValueError):
        return out

    z = abs(x - stats.avg_total) / stats.std_total
    if z < Z_THRESHOLD:
        return out
    if _is_acked(x, acks.get("total", [])):
        return out

    out.append(
        AnomalyReason(
            field="total",
            vendor_mean=stats.avg_total,
            vendor_std=stats.std_total,
            z_score=round(z, 2),
        )
    )
    return out


def _is_acked(value: float, acked: list[AcknowledgedOutlier]) -> bool:
    for a in acked:
        a_val = float(a.get("value", 0.0) or 0.0)
        if a_val <= 0:
            continue
        if abs(value - a_val) / a_val < ACK_TOLERANCE_FRAC:
            return True
    return False
