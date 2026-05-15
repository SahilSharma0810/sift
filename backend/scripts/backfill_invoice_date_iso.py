"""Backfill `iso_from` / `iso_to` on existing `extracted_fields.invoice_date`.

Same `parse_date_or_range` function the live extraction pipeline uses, so
old rows and new rows end up in the same canonical shape. Idempotent —
rows that already have populated ISO fields and re-parse to the same
endpoints are skipped silently.

Run from inside the backend container:
    docker compose exec backend uv run python -m scripts.backfill_invoice_date_iso

Or against a one-off DATABASE_URL:
    DATABASE_URL=postgresql+psycopg://... uv run python -m scripts.backfill_invoice_date_iso
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.db.models import Extraction
from app.db.session import SessionLocal
from app.domain.date_parser import parse_date_or_range

log = logging.getLogger("backfill_invoice_date_iso")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")


def _is_field_dict(value: Any) -> bool:
    return isinstance(value, dict) and "value" in value


def main() -> None:
    session = SessionLocal()
    seen = updated = skipped_already_set = skipped_unparseable = 0
    try:
        for ext in session.execute(select(Extraction)).scalars():
            seen += 1
            fields = ext.extracted_fields or {}
            date_field = fields.get("invoice_date")
            if not _is_field_dict(date_field):
                continue

            verbatim = date_field.get("value")
            iso_from_existing = date_field.get("iso_from")
            iso_to_existing = date_field.get("iso_to")
            iso_from, iso_to = parse_date_or_range(verbatim)

            if iso_from is None and iso_to is None:
                if iso_from_existing is None and iso_to_existing is None:
                    skipped_unparseable += 1
                    continue

            if iso_from == iso_from_existing and iso_to == iso_to_existing:
                skipped_already_set += 1
                continue

            date_field["iso_from"] = iso_from
            date_field["iso_to"] = iso_to
            fields["invoice_date"] = date_field
            ext.extracted_fields = fields
            flag_modified(ext, "extracted_fields")
            updated += 1

        session.commit()
    finally:
        session.close()

    log.info(
        "backfill complete: seen=%d updated=%d already_set=%d unparseable=%d",
        seen,
        updated,
        skipped_already_set,
        skipped_unparseable,
    )


if __name__ == "__main__":
    main()
