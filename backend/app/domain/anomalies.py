"""Anomaly detection for extracted invoice fields.

Pure: no IO. Compares numeric fields against per-vendor stats (mean + std)
and emits `anomaly` reason payloads matching the AnomalyReason discriminator.
"""

from __future__ import annotations

from typing import Any

# Field set checked for anomalies in Day 2. `subtotal` and `tax` are not
# checked because they're typically scale-coupled to `total` — a 3-sigma total
# anomaly already implies anomalous subtotal/tax. Day-3+ may extend.
ANOMALY_FIELDS = ("total",)

# Need at least this many prior extractions before Z-score is meaningful.
MIN_VENDOR_HISTORY = 3

# Trigger threshold — values outside ±Z_THRESHOLD sigma are anomalies.
Z_THRESHOLD = 3.0


def detect_anomalies(
    *,
    fields: dict[str, Any],
    stats: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return `anomaly` reason payloads for fields outside +-3 sigma of vendor history.

    `stats` shape: {"total_seen": int, "avg_total": float, "std_total": float}.
    Skips the check when vendor history is too small or std is degenerate.
    """
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
        if z >= Z_THRESHOLD:
            out.append(
                {
                    "field": field,
                    "vendor_mean": avg,
                    "vendor_std": std,
                    "z_score": round(z, 2),
                }
            )
    return out
