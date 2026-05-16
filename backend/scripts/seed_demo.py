"""Populate the demo inbox via the real extraction pipeline.

Generates ~7 curated PDFs, writes them to the upload directory, then
runs each through `extract_from_pdf` so they land in the DB exactly as
a user-uploaded PDF would. Stub-mode `[seed-*]` markers in the PDF
text steer the StubLLMClient toward specific vendors and totals so
each invoice tells a different part of the demo story:

  Halcyon Software x 3 (confirmed)    -> seeds vendor history (avg ~$34250)
  Halcyon Software x 1 (needs_review) -> ANOMALY ($89k vs $34k norm)
  Vega Logistics x 1 (confident)      -> ready-to-confirm beat
  Vega Logistics x 1 (likely_duplicate) -> DUPLICATE of the above (same phash)
  TidePoint Solar x 1 (unprocessable) -> EXTRACTION_FAILED beat

Run from inside the backend container:
    docker compose exec backend uv run python -m scripts.seed_demo

Or via Makefile:
    make seed-demo
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import pymupdf  # type: ignore[import-not-found]

from app.adapters.storage.user_repo import upsert_demo_user
from app.config import get_settings
from app.db.models import User
from app.db.session import SessionLocal
from app.services.clerk_actions import confirm_invoice, mark_unprocessable
from app.services.extraction_service import extract_from_pdf


def seed_demo_user(session) -> User:
    settings = get_settings()
    return upsert_demo_user(
        session,
        email=settings.demo_email,
        password=settings.demo_password,
    )

log = logging.getLogger("seed_demo")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")

@dataclass(frozen=True, slots=True)
class Seed:
    label: str
    body: str
    confirm: bool = False
    unprocessable: bool = False

SEEDS: list[Seed] = [

    Seed(
        label="halcyon-1",
        body=(
            "Halcyon Software Inc.\n"
            "Invoice 2026-04-12\n"
            "[seed-vendor:Halcyon Software] [seed-number:HAL-2026-101]\n"
            "[seed-total:34000]\n"
        ),
        confirm=True,
    ),
    Seed(
        label="halcyon-2",
        body=(
            "Halcyon Software Inc.\n"
            "Invoice 2026-04-19\n"
            "[seed-vendor:Halcyon Software] [seed-number:HAL-2026-102]\n"
            "[seed-total:34500]\n"
        ),
        confirm=True,
    ),
    Seed(
        label="halcyon-3",
        body=(
            "Halcyon Software Inc.\n"
            "Invoice 2026-04-26\n"
            "[seed-vendor:Halcyon Software] [seed-number:HAL-2026-103]\n"
            "[seed-total:34250]\n"
        ),
        confirm=True,
    ),

    Seed(
        label="halcyon-anomaly",
        body=(
            "Halcyon Software Inc.\n"
            "Invoice 2026-05-13 special engagement\n"
            "[seed-vendor:Halcyon Software] [seed-number:HAL-2026-104]\n"
            "[seed-total:89000]\n"
        ),
    ),

    Seed(
        label="vega-clean",
        body=(
            "Vega Logistics LLC\n"
            "Invoice INV-2026-2025\n"
            "Freight services last mile\n"
            "[seed-vendor:Vega Logistics] [seed-number:INV-2026-2025]\n"
            "[seed-total:1180]\n"
        ),
    ),

    Seed(
        label="vega-near-dup",
        body=(
            "Vega Logistics LLC\n"
            "Invoice INV-2026-2025\n"
            "Freight services last mile (reissue)\n"
            "[seed-vendor:Vega Logistics] [seed-number:INV-2026-2025]\n"
            "[seed-total:1180]\n"
            "near-duplicate of vega-clean\n"
        ),
    ),

    Seed(
        label="tidepoint-encrypted",
        body=(
            "[stub:fail] TidePoint Solar invoice could not be parsed\n"
            "(synthetic encrypted-scan stand-in for the demo)\n"
        ),
        unprocessable=True,
    ),
]

_VISUAL_MARKERS: dict[str, tuple[float, float, float, float]] = {
    "halcyon-1": (100, 220, 200, 110),
    "halcyon-2": (320, 220, 200, 110),
    "halcyon-3": (100, 420, 200, 110),
    "halcyon-anomaly": (320, 420, 200, 110),
    "vega-clean": (150, 300, 300, 140),
    "vega-near-dup": (150, 300, 300, 140),
    "tidepoint-encrypted": (220, 250, 240, 240),
}

def _make_pdf(text: str, dest: Path, *, marker: tuple[float, float, float, float]) -> None:
    """Write a single-page PDF with the given text body + a visual marker.

    The marker is a filled rectangle whose position+size is unique per seed
    label, so the perceptual hash of any two distinct seed PDFs differs
    enough that the duplicate detector doesn't fire on accident. The
    `vega-near-dup` seed reuses `vega-clean`'s marker so the duplicate
    detection beat actually demonstrates a real match.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72.0
    for line in text.splitlines():
        page.insert_text((72, y), line, fontsize=11)
        y += 14.0
    x, y_, w, h = marker
    page.draw_rect(pymupdf.Rect(x, y_, x + w, y_ + h), fill=(0.18, 0.32, 0.55))
    doc.save(str(dest))
    doc.close()

def _persist_pdf(body_bytes: bytes, upload_dir: Path) -> Path:
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_hash = hashlib.sha256(body_bytes).hexdigest()
    target = upload_dir / f"{file_hash}.pdf"
    if not target.exists():
        target.write_bytes(body_bytes)
    return target

def main() -> None:
    settings = get_settings()
    if settings.llm_provider != "stub":
        log.warning(
            "SIFT_LLM_PROVIDER is %r — seed_demo expects 'stub'. "
            "Real Anthropic calls will burn credits without producing "
            "the curated demo state.",
            settings.llm_provider,
        )

    upload_dir = settings.upload_dir
    session = SessionLocal()
    staging = Path("/tmp/seed_demo")

    try:
        seed_demo_user(session)
        log.info("seeded demo user %s", get_settings().demo_email)
        for seed in SEEDS:
            log.info("seeding %s ...", seed.label)
            staging.mkdir(parents=True, exist_ok=True)
            tmp_pdf = staging / f"{seed.label}.pdf"
            marker = _VISUAL_MARKERS.get(seed.label, (100, 200, 100, 100))
            _make_pdf(seed.body, tmp_pdf, marker=marker)
            body_bytes = tmp_pdf.read_bytes()
            final_path = _persist_pdf(body_bytes, upload_dir)
            tmp_pdf.unlink(missing_ok=True)

            result = extract_from_pdf(
                session, pdf_path=final_path, storage_key=final_path.name
            )

            if seed.confirm:
                confirm_invoice(session, invoice_id=result.invoice.id)
                log.info("  confirmed (vendor stats updated)")
            elif seed.unprocessable:
                mark_unprocessable(session, invoice_id=result.invoice.id)
                log.info("  marked unprocessable")
            else:
                log.info(
                    "  triage=%s reasons=%s",
                    result.extraction.predicted_triage_state,
                    [r["type"] for r in result.extraction.predicted_triage_reasons],
                )
    finally:
        session.close()
        if staging.exists():
            for f in staging.iterdir():
                f.unlink()
            staging.rmdir()

    log.info("done. %d invoices seeded.", len(SEEDS))

if __name__ == "__main__":
    main()
