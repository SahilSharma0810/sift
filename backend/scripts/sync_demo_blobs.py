"""One-shot rescue: push the deterministic demo PDFs to the configured blob
store without touching Postgres.

Use case: the staging deploy was seeded before `seed_demo.py` was fixed to
use the blob-store abstraction (it wrote PDFs to local disk only). The
Postgres rows reference `storage_key={sha256}.pdf` keys that don't exist
in R2. This script regenerates the same PDFs deterministically (same body
text + same visual marker -> same hash) and uploads any missing key to
the blob store. Existing DB rows then resolve correctly without a wipe.

Run locally with the staging R2 credentials (no DB access needed):

    cd backend
    SIFT_BLOB_STORE=r2 \\
      SIFT_R2_ACCOUNT_ID=... \\
      SIFT_R2_ACCESS_KEY_ID=... \\
      SIFT_R2_SECRET_ACCESS_KEY=... \\
      SIFT_R2_BUCKET=... \\
      uv run python -m scripts.sync_demo_blobs

Idempotent: re-running is safe — already-present keys are skipped.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from app.adapters.storage.blob_store import get_blob_store
from app.config import get_settings
from scripts.seed_demo import SEEDS, _VISUAL_MARKERS, _make_pdf

log = logging.getLogger("sync_demo_blobs")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")


def main() -> None:
    settings = get_settings()
    store = get_blob_store()
    staging = Path("/tmp/sync_demo_blobs")
    staging.mkdir(parents=True, exist_ok=True)

    log.info("blob store backend: %s", settings.blob_store)
    if settings.blob_store == "r2":
        log.info("  bucket=%s account=%s", settings.r2_bucket, settings.r2_account_id)

    uploaded = 0
    skipped = 0
    try:
        for seed in SEEDS:
            tmp_pdf = staging / f"{seed.label}.pdf"
            marker = _VISUAL_MARKERS.get(seed.label, (100, 200, 100, 100))
            _make_pdf(seed.body, tmp_pdf, marker=marker)

            file_hash = hashlib.sha256(tmp_pdf.read_bytes()).hexdigest()
            storage_key = f"{file_hash}.pdf"

            if store.exists(storage_key):
                log.info("  [skip] %-22s %s already present", seed.label, storage_key)
                skipped += 1
            else:
                store.put_path(storage_key, tmp_pdf)
                log.info("  [push] %-22s %s -> %s", seed.label, storage_key, settings.blob_store)
                uploaded += 1
    finally:
        for f in staging.glob("*.pdf"):
            f.unlink(missing_ok=True)
        staging.rmdir()

    log.info("done. %d uploaded, %d already present, %d total", uploaded, skipped, len(SEEDS))


if __name__ == "__main__":
    main()
