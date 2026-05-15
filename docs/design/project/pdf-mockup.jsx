/* global React */
// Mock PDF "papers" — hand-laid invoice layouts that we overlay bboxes on.
// Real product would render PDF.js + use stored bboxes from the extraction.

const { useRef, useEffect, useState } = window.React;

// Each pdfKind maps to a different visual layout, mirroring the kinds of
// invoices an AP clerk sees: clean digital, scanned, watermarked, encrypted.
// The bbox coords in data.jsx are normalized to whatever sits inside .pdf-paper.

function PdfPaper({ invoice, activeField, onFieldHover }) {
  if (invoice.pdfKind === "encrypted") {
    return (
      <div className="pdf-paper pdf-paper-encrypted">
        <div style={{
          width: 56, height: 56, borderRadius: 12,
          background: "var(--surface-recess)", display: "grid", placeItems: "center",
          color: "var(--ink-60)", marginBottom: 14,
        }}>
          <window.Icons.lock />
        </div>
        <div style={{ fontWeight: 600, color: "var(--ink)", fontSize: 15 }}>
          Encrypted PDF
        </div>
        <div className="muted" style={{ marginTop: 6, fontSize: 13, maxWidth: 320 }}>
          Sift couldn't read this file because it's password-protected.
          You can re-upload an unlocked copy, or enter the fields manually below.
        </div>
        <div className="mono" style={{
          marginTop: 18, fontSize: 11, color: "var(--ink-48)",
          padding: "6px 10px", background: "var(--surface-recess)",
          borderRadius: 4, border: "1px solid var(--hairline)",
        }}>
          TidePoint-May-2026.pdf  ·  142 KB
        </div>
      </div>
    );
  }
  return <PaperLayout invoice={invoice} activeField={activeField} onFieldHover={onFieldHover} />;
}

// Generic invoice layout. We vary the header color and a few details per pdfKind
// so it doesn't feel like the same PDF every time.
function PaperLayout({ invoice, activeField, onFieldHover }) {
  const paperRef = useRef(null);
  const [dims, setDims] = useState({ w: 0, h: 0 });

  useEffect(() => {
    if (!paperRef.current) return;
    const ro = new ResizeObserver(entries => {
      for (const e of entries) {
        setDims({ w: e.contentRect.width, h: e.contentRect.height });
      }
    });
    ro.observe(paperRef.current);
    return () => ro.disconnect();
  }, []);

  const PROFILE = {
    vega:      { ribbon: "oklch(0.92 0.07 150)", label: "freight invoice" },
    acme:      { ribbon: "oklch(0.92 0.05 25)",  label: "logistics" },
    bramble:   { ribbon: "oklch(0.91 0.08 70)",  label: "office subscription" },
    northwind: { ribbon: "oklch(0.90 0.04 250)", label: "materials (scanned)" },
    lyra:      { ribbon: "oklch(0.91 0.06 290)", label: "print services" },
    halcyon:   { ribbon: "oklch(0.91 0.06 200)", label: "software licensing" },
  };
  const prof = PROFILE[invoice.pdfKind] ?? PROFILE.vega;

  // Apply a subtle scanned-paper effect on Northwind to convey OCR ambiguity
  const isScan = invoice.pdfKind === "northwind";

  const f = invoice.fields;
  const fmt = window.formatNumber;

  return (
    <div className="pdf-paper" ref={paperRef} style={{
      filter: isScan ? "contrast(1.06) saturate(0.9)" : "none",
      background: isScan
        ? "linear-gradient(180deg, oklch(0.98 0.01 80) 0%, oklch(0.97 0.02 60) 100%)"
        : "var(--surface)",
      fontFamily: isScan ? "ui-monospace, 'SF Mono', monospace" : undefined,
      letterSpacing: isScan ? "0.005em" : undefined,
    }}>
      {/* Decorative ribbon */}
      <div style={{
        position: "absolute", left: 0, right: 0, top: 0, height: 6,
        background: prof.ribbon,
        borderTopLeftRadius: 6, borderTopRightRadius: 6,
      }} />

      {/* Header row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.01em", marginBottom: 2 }}>
            {invoice.vendor}
          </div>
          <div style={{ fontSize: 11, color: "oklch(0.45 0.01 250)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            {prof.label}
          </div>
          <div style={{ fontSize: 11, color: "oklch(0.4 0.01 250)", marginTop: 18, lineHeight: 1.6 }}>
            221B Vendor Street<br/>
            Wilmington, DE 19801<br/>
            billing@{invoice.vendor.toLowerCase().replace(/[^a-z]/g, "")}.com
          </div>
        </div>
        <div style={{ textAlign: "right", fontSize: 11, lineHeight: 1.9, minWidth: 160, whiteSpace: "nowrap" }}>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>INVOICE</div>
          <div><span style={{ color: "oklch(0.45 0.01 250)" }}>Invoice #</span>&nbsp;&nbsp;<b>{invoice.invoiceNumber}</b></div>
          <div><span style={{ color: "oklch(0.45 0.01 250)" }}>Date</span>&nbsp;&nbsp;<b>{invoice.date}</b></div>
          <div><span style={{ color: "oklch(0.45 0.01 250)" }}>Due</span>&nbsp;&nbsp;<b>net 30</b></div>
        </div>
      </div>

      {/* Bill-to */}
      <div style={{ marginTop: 38, fontSize: 11, lineHeight: 1.6 }}>
        <div style={{ color: "oklch(0.45 0.01 250)", textTransform: "uppercase", letterSpacing: "0.08em", fontSize: 10 }}>
          Bill to
        </div>
        <div style={{ marginTop: 4 }}>
          <b>Northwind Finance Operations</b><br/>
          900 Market Street, Suite 400<br/>
          San Francisco, CA 94103
        </div>
      </div>

      {/* Line items (illustrative only) */}
      <table style={{
        marginTop: 28, width: "100%", borderCollapse: "collapse",
        fontSize: 11.5, color: "oklch(0.25 0.01 250)",
      }}>
        <thead>
          <tr style={{
            borderBottom: "1px solid oklch(0.85 0.005 250)",
            textTransform: "uppercase", letterSpacing: "0.08em",
            fontSize: 9.5, color: "oklch(0.45 0.01 250)",
          }}>
            <th style={{ textAlign: "left",  padding: "8px 0" }}>Description</th>
            <th style={{ textAlign: "right", padding: "8px 0", width: 60 }}>Qty</th>
            <th style={{ textAlign: "right", padding: "8px 0", width: 100 }}>Unit</th>
            <th style={{ textAlign: "right", padding: "8px 0", width: 100 }}>Amount</th>
          </tr>
        </thead>
        <tbody>
          {(invoice.pdfKind === "halcyon" ? HALCYON_ITEMS :
            invoice.pdfKind === "bramble" ? BRAMBLE_ITEMS :
            invoice.pdfKind === "lyra"    ? LYRA_ITEMS :
            invoice.pdfKind === "acme"    ? ACME_ITEMS :
            invoice.pdfKind === "northwind" ? NORTHWIND_ITEMS :
            VEGA_ITEMS).map((it, i) => (
              <tr key={i} style={{ borderBottom: "1px solid oklch(0.93 0.005 250)" }}>
                <td style={{ padding: "8px 0" }}>{it.d}</td>
                <td style={{ padding: "8px 0", textAlign: "right" }}>{it.q}</td>
                <td style={{ padding: "8px 0", textAlign: "right" }} className="num">{fmt(it.u)}</td>
                <td style={{ padding: "8px 0", textAlign: "right" }} className="num">{fmt(it.q * it.u)}</td>
              </tr>
            ))}
        </tbody>
      </table>

      {/* Totals block */}
      <div style={{ marginTop: 18, display: "flex", justifyContent: "flex-end" }}>
        <div style={{ width: 220, fontSize: 12 }}>
          <Row label="Subtotal" value={fmt(invoice.subtotal)} />
          <Row label="Tax (18%)" value={fmt(invoice.tax)} />
          <Row label="Total" value={`${invoice.currency} ${fmt(invoice.total)}`} bold />
        </div>
      </div>

      {/* Watermark / footer */}
      <div style={{
        position: "absolute", bottom: 38, left: 64, right: 64,
        fontSize: 10, color: "oklch(0.5 0.01 250)", lineHeight: 1.6,
        borderTop: "1px solid oklch(0.9 0.005 250)", paddingTop: 16,
      }}>
        Wire transfer · ACH preferred · Routing 021000021 · Account 1234567890 ·
        Questions? finance@{invoice.vendor.toLowerCase().replace(/[^a-z]/g, "")}.com
      </div>

      {/* Bbox overlays */}
      {dims.w > 0 && Object.entries(f).map(([name, field]) => {
        if (!field?.bbox) return null;
        const [x0, y0, x1, y1] = field.bbox;
        const style = {
          left:  `${x0 * 100}%`,
          top:   `${y0 * 100}%`,
          width: `${(x1 - x0) * 100}%`,
          height:`${(y1 - y0) * 100}%`,
        };
        return (
          <div key={name}
               className="bbox"
               data-active={activeField === name ? "true" : "false"}
               style={style}
               onMouseEnter={() => onFieldHover?.(name)}
               onMouseLeave={() => onFieldHover?.(null)}
               title={`${name}: ${field.value}`} />
        );
      })}
    </div>
  );
}

function Row({ label, value, bold }) {
  return (
    <div style={{
      display: "flex", justifyContent: "space-between",
      padding: "6px 0",
      fontWeight: bold ? 700 : 400,
      borderTop: bold ? "1px solid oklch(0.85 0.005 250)" : "none",
      marginTop: bold ? 4 : 0,
      fontSize: bold ? 13 : 12,
    }}>
      <span style={{ color: bold ? "oklch(0.2 0.01 250)" : "oklch(0.45 0.01 250)" }}>{label}</span>
      <span className="num">{value}</span>
    </div>
  );
}

const VEGA_ITEMS = [
  { d: "Freight services, April 2026",                q: 1, u: 700.0 },
  { d: "Last-mile delivery surcharge",                 q: 1, u: 200.0 },
  { d: "Fuel adjustment",                              q: 1, u: 100.0 },
];
const ACME_ITEMS = [
  { d: "LTL freight (Pallets, NJ → CA)",               q: 3, u: 1100.0 },
  { d: "Hazmat handling",                              q: 2, u: 350.0 },
  { d: "Liftgate service",                             q: 1, u: 500.0 },
];
const BRAMBLE_ITEMS = [
  { d: "Office coffee — Brazil Cerrado, 5lb",          q: 4, u: 68.0 },
  { d: "Filters & supplies",                           q: 1, u: 80.0 },
  { d: "Same-day delivery",                            q: 1, u: 60.0 },
];
const NORTHWIND_ITEMS = [
  { d: "Steel sheet 4'x8' #18ga",                      q: 40, u: 47.5 },
  { d: "Galvanized fasteners, box of 500",             q: 6,  u: 56.0 },
  { d: "Cutting & finishing",                          q: 1,  u: 604.0 },
];
const LYRA_ITEMS = [
  { d: "Letterpress business cards, 500 ct",           q: 2, u: 220.0 },
  { d: "Foil stamping",                                q: 1, u: 160.0 },
  { d: "Rush production",                              q: 1, u: 80.0 },
];
const HALCYON_ITEMS = [
  { d: "Halcyon Enterprise Seats (annual)",            q: 50, u: 600.0 },
  { d: "Premium Support tier",                         q: 1,  u: 950.0 },
  { d: "API platform fee (annual)",                    q: 1,  u: 300.0 },
];

Object.assign(window, { PdfPaper });
