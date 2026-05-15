"""Anomaly detection for extracted invoice fields.

Pure: no IO. Compares numeric fields against per-vendor stats (mean + std)
and emits `anomaly` reason payloads matching the AnomalyReason discriminator.
"""

from __future__ import annotations

from typing import Any

ANOMALY_FIELDS = ("total",)

MIN_VENDOR_HISTORY = 3

Z_THRESHOLD = 3.0

ACK_TOLERANCE_FRAC = 0.10


def detect_anomalies(
    *,
    fields: dict[str, Any],
    stats: dict[str, Any],
    acknowledged_outliers: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Return `anomaly` reason payloads for fields outside +-3 sigma of vendor history.

    `stats` shape: {"total_seen": int, "avg_total": float, "std_total": float}.
    Skips the check when vendor history is too small or std is degenerate.

    `acknowledged_outliers` maps field name → list of prior-acked values for
    that field. A new value within ACK_TOLERANCE_FRAC of any acked value is
    treated as a known outlier and is NOT emitted as an anomaly.
    """
    acks = acknowledged_outliers or {}
    out: list[dict[str, Any]] = []
    total_seen = int(stats.get("total_seen", 0) or 0)
    if total_seen < MIN_VENDOR_HISTORY:
        return out
    for field in ANOMALY_FIELDS:
        value = fields.get(field)
        if value is None:
            continue
        avg = float(stats.get(f"avg_{field}", 0.0) or 0.0)
        std = float(stats.get(f"std_{field}", 0.0) or 0.0)
        if std <= 0:
            continue
        try:
            z = abs(float(value) - avg) / std
        except (TypeError, ValueError):
            continue
        if z < Z_THRESHOLD:
            continue
        if _is_acked(float(value), acks.get(field, [])):
            continue
        out.append(
            {
                "field": field,
                "vendor_mean": avg,
                "vendor_std": std,
                "z_score": round(z, 2),
            }
        )
    return out


def _is_acked(value: float, acked: list[dict[str, Any]]) -> bool:
    for a in acked:
        a_val = float(a.get("value", 0.0) or 0.0)
        if a_val <= 0:
            continue
        if abs(value - a_val) / a_val < ACK_TOLERANCE_FRAC:
            return True
    return False
