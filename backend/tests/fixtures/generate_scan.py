"""Rasterize digital_invoice_clean.pdf into an image-only PDF for vision tests.

Run: docker compose exec backend uv run python tests/fixtures/generate_scan.py
"""

from pathlib import Path

from pdf2image import convert_from_path

HERE = Path(__file__).parent
SRC = HERE / "digital_invoice_clean.pdf"
OUT = HERE / "scan_invoice.pdf"

def main() -> None:
    pages = convert_from_path(str(SRC), dpi=120)
    if not pages:
        raise RuntimeError(f"no pages rendered from {SRC}")
    pages[0].save(str(OUT), "PDF", resolution=120.0, save_all=True, append_images=pages[1:])
    print(f"Wrote {OUT}")

if __name__ == "__main__":
    main()
