"""Vendor-memory service per ADR-0003.

`update_stats_from_extraction` is called only after a clerk confirms an
extraction — see ADR-0003 + Day-2 Plan-agent recommendation (stats built
from confirmed rows are semantically sound; unconfirmed rows can pollute).

`compute_history_scores` is a thin wrapper that extracts vendor.memory.stats
and delegates to domain.confidence — the pure math lives in the domain
layer (single source of truth for Composite Confidence). This wrapper
exists so callers (and tests) can stay in ORM terms.

Critical: SQLAlchemy ORM does not detect in-place dict/list mutations on
JSONB columns. After mutating `vendor.memory`, we MUST call
`flag_modified(vendor, "memory")` or the change silently doesn't persist.
"""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.db.models import Extraction, Vendor
from app.domain.confidence import (
    NUMERIC_HISTORY_FIELDS,
    compute_history_scores_from_stats,
)


def update_stats_from_extraction(
    session: Session, *, vendor: Vendor, extraction: Extraction
) -> None:
    """Recompute Welford-style running mean + std for numeric fields.

    Called from the /confirm API endpoint (and from any future automated
    confirmer). Never called from `extract_from_pdf` — that path runs
    before clerk validation and would corrupt stats with wrong extractions.
    """
    memory = dict(vendor.memory or {})
    stats = dict(memory.get("stats", {}) or {})
    rules = list(memory.get("rules", []) or [])

    fields = extraction.extracted_fields or {}
    for fname in NUMERIC_HISTORY_FIELDS:
        spec = fields.get(fname) or {}
        value = spec.get("value") if isinstance(spec, dict) else None
        if value is None:
            continue
        try:
            x = float(value)
        except (TypeError, ValueError):
            continue
        n = int(stats.get("total_seen", 0) or 0)
        prev_mean = float(stats.get(f"avg_{fname}", 0.0) or 0.0)
        prev_var_n = float(stats.get(f"_var_n_{fname}", 0.0) or 0.0)
        n_new = n + 1
        new_mean = prev_mean + (x - prev_mean) / n_new
        new_var_n = prev_var_n + (x - prev_mean) * (x - new_mean)
        sample_std = math.sqrt(new_var_n / (n_new - 1)) if n_new > 1 else 0.0
        stats["total_seen"] = n_new
        stats[f"avg_{fname}"] = round(new_mean, 4)
        stats[f"std_{fname}"] = round(sample_std, 4)
        stats[f"_var_n_{fname}"] = new_var_n

    memory["stats"] = stats
    memory["rules"] = rules
    vendor.memory = memory
    flag_modified(vendor, "memory")  # JSONB mutation needs explicit dirty flag
    session.flush()


def compute_history_scores(
    *,
    vendor: Vendor | None,
    fields: dict[str, Any],
) -> dict[str, float]:
    """ORM-aware wrapper for the domain history-score computation.

    Pulls the stats dict out of `vendor.memory` and delegates. Returning
    `{}` for `None` vendor preserves the cold-start contract.
    """
    if vendor is None:
        return {}
    stats = (vendor.memory or {}).get("stats") or {}
    return compute_history_scores_from_stats(
        extracted_fields=fields, vendor_stats=stats
    )
