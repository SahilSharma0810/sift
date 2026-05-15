"""One-shot fixture generator. Run: uv run python tests/fixtures/generate_clean.py
The output PDF is checked into the repo; this script just regenerates it.
"""

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

OUT = Path(__file__).with_name("digital_invoice_clean.pdf")

def main() -> None:
    c = canvas.Canvas(str(OUT), pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 720, "Vega Logistics")
    c.setFont("Helvetica", 11)
    c.drawString(72, 700, "Invoice")
    c.drawString(72, 680, "Invoice #: INV-2026-0042")
    c.drawString(72, 660, "Date: 2026-05-13")
    c.drawString(72, 600, "Description: Freight services, April 2026")
    c.drawString(72, 540, "Subtotal: USD 1,000.00")
    c.drawString(72, 520, "Tax (18%): USD 180.00")
    c.drawString(72, 500, "Total: USD 1,180.00")
    c.save()
    print(f"Wrote {OUT}")

if __name__ == "__main__":
    main()
