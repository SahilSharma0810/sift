#!/usr/bin/env python3
"""Re-run triage derivation on existing extractions — no API calls.

After tuning triage logic (`domain/triage.py`, `domain/validators.py`),
this script re-derives the predicted_triage_state + predicted_triage_reasons
for every current extraction in the DB and shows a before/after table.

By default it's READ-ONLY: just prints what the new triage would be without
changing anything. Pass --write to actually update the DB rows.

Note on immutability: per ADR-0003, `predicted_triage_state` is supposed
to be immutable per extraction row (preserves eval ground truth). Updating
in-place violates that. For interview-submission verification this is OK
— if you want clean immutability semantics, use --write only AFTER you've
saved a snapshot of the prior eval (or just run `make reset-db` + re-extract).

Run inside the backend container:
  docker compose exec backend uv run python -m scripts.redrive_triage
  docker compose exec backend uv run python -m scripts.redrive_triage --write
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select, update

from app.db.models import Extraction, Invoice, Vendor
from app.db.session import SessionLocal
from app.domain.models import AnomalyReason, DuplicateOfReason
from app.domain.scoring import compute_composite_confidence
from app.domain.triage import derive_triage
from app.domain.validators import compute_structural_scores
from app.services.vendor_memory_service import compute_history_scores

def _flat_value(field_data):
    """Pull the bare value out of an ExtractedField-shaped dict."""
    if isinstance(field_data, dict) and "value" in field_data:
        return field_data["value"]
    return field_data

def _flat_fields(stored_fields: dict) -> dict:
    return {k: _flat_value(v) for k, v in (stored_fields or {}).items()}

def _confidence_map(stored: dict) -> dict[str, float]:
    return {k: float(v) for k, v in (stored or {}).items()}

def _was_duplicate(reasons: list) -> DuplicateOfReason | None:
    for r in reasons or []:
        if r.get("type") == "duplicate_of":
            return DuplicateOfReason(**{k: v for k, v in r.items() if k != "type"})
    return None


def _anomalies_from_reasons(reasons: list) -> list[AnomalyReason]:
    return [
        AnomalyReason(**{k: v for k, v in r.items() if k != "type"})
        for r in reasons or []
        if r.get("type") == "anomaly"
    ]

def _math_passed_from_fields(flat_fields: dict) -> bool:
    from app.domain.validators import math_reconciles

    def _f(v):
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return math_reconciles(
        subtotal=_f(flat_fields.get("subtotal")),
        tax=_f(flat_fields.get("tax")),
        total=_f(flat_fields.get("total")),
    )

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--write", action="store_true", help="Persist the new triage state to the DB")
    p.add_argument("--limit", type=int, default=100)
    args = p.parse_args()

    session = SessionLocal()
    try:
        stmt = (
            select(Extraction, Invoice, Vendor)
            .join(Invoice, Invoice.id == Extraction.invoice_id)
            .join(Vendor, Vendor.id == Invoice.vendor_id, isouter=True)
            .where(Extraction.is_current.is_(True))
            .limit(args.limit)
        )
        rows = session.execute(stmt).all()

        if not rows:
            print("No current extractions in DB. Run the smoke test first.")
            return 0

        flips = 0
        same = 0
        total = len(rows)

        print(f"{'invoice':<10}  {'before':<18}  {'after':<18}  {'change'}")
        print("-" * 80)
        for ext, inv, vendor in rows:
            flat = _flat_fields(ext.extracted_fields)
            old_state = ext.predicted_triage_state
            old_reasons = ext.predicted_triage_reasons or []

            dup = _was_duplicate(old_reasons)
            anomalies = _anomalies_from_reasons(old_reasons)
            math_passed = _math_passed_from_fields(flat)
            is_unseen = bool(
                (vendor is None)
                or vendor.memory == {}
                or not (vendor.memory or {}).get("stats", {}).get("total_seen", 0)
            )

            structural = compute_structural_scores(flat)
            history = compute_history_scores(vendor=vendor, fields=flat)
            confidence = compute_composite_confidence(structural, history=history)

            new_state, new_reasons = derive_triage(
                extracted_fields=flat,
                confidence=confidence,
                math_passed=math_passed,
                is_unseen_vendor=is_unseen,
                duplicate_of=dup,
                anomalies=anomalies,
            )

            change = "→" if new_state != old_state else "·"
            label = str(inv.id)[:8]
            new_reason_types = sorted({r.type for r in new_reasons})
            reason_str = ",".join(new_reason_types) if new_reason_types else "—"
            print(f"{label:<10}  {old_state:<18}  {new_state:<18}  {change}  reasons={reason_str}")

            if new_state != old_state:
                flips += 1
            else:
                same += 1

            if args.write:
                session.execute(
                    update(Extraction)
                    .where(Extraction.id == ext.id)
                    .values(
                        predicted_triage_state=new_state,
                        predicted_triage_reasons=[r.model_dump(mode="json") for r in new_reasons],
                        confidence_per_field=confidence,
                    )
                )

        print("-" * 80)
        print(f"Total: {total} · flipped: {flips} · unchanged: {same}")
        if args.write:
            session.commit()
            print("DB updated.")
        else:
            print("(read-only — pass --write to persist)")
    finally:
        session.close()

    return 0

if __name__ == "__main__":
    sys.exit(main())
