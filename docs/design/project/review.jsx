/* global React */
// Review — split view: PDF mockup left, fields panel + reason cards right.
// Bidirectional hover: field row hover highlights bbox, bbox hover highlights row.

const { useState, useMemo } = window.React;

const FIELDS = [
  { key: "vendor_name",    label: "Vendor" },
  { key: "invoice_number", label: "Invoice #" },
  { key: "invoice_date",   label: "Date" },
  { key: "subtotal",       label: "Subtotal" },
  { key: "tax",            label: "Tax" },
  { key: "total",          label: "Total" },
  { key: "currency",       label: "Currency" },
];

function ReviewScreen({ invoiceId, onBack, onOpen }) {
  const { INVOICES } = window.SIFT_DATA;
  const invoice = INVOICES.find(i => i.id === invoiceId) ?? INVOICES[0];
  const byId = useMemo(
    () => Object.fromEntries(INVOICES.map(i => [i.id, i])),
    [INVOICES],
  );

  const [activeField, setActiveField] = useState(null);
  const [editingField, setEditingField] = useState(null);
  // Local field overrides — to demonstrate manual corrections without mutating data.
  const [overrides, setOverrides] = useState({});

  const isUnprocessable = invoice.triage_state === "unprocessable";
  const [manualMode, setManualMode] = useState(isUnprocessable);

  // Merge real values with manual overrides.
  const fields = useMemo(() => {
    const out = { ...invoice.fields };
    for (const [k, v] of Object.entries(overrides)) {
      out[k] = { ...(out[k] ?? { confidence: 1, source: "manual", bbox: null }), value: v, confidence: 1, source: "manual" };
    }
    return out;
  }, [invoice.fields, overrides]);

  const handleReason = (action, payload) => {
    if (action === "edit_total")    setEditingField("total");
    if (action === "edit_field")    setEditingField(payload);
    if (action === "add_field")     setEditingField(payload);
    if (action === "manual_entry")  setManualMode(true);
    if (action === "view_dup")      onOpen?.(payload);
  };

  const commitField = (name, value) => {
    setOverrides(o => ({ ...o, [name]: value }));
    setEditingField(null);
  };

  return (
    <div className="review-grid">
      {/* LEFT: PDF */}
      <div className="pdf-stage">
        <window.PdfPaper
          invoice={invoice}
          activeField={activeField}
          onFieldHover={setActiveField}
        />
      </div>

      {/* RIGHT: Side panel */}
      <div className="review-side">
        <ReviewHeader invoice={invoice} onBack={onBack} />

        {/* Reasons block — only when there are reasons */}
        {invoice.reasons.length > 0 && (
          <div className="review-side-section">
            <div className="review-side-section-title">
              Why this needs attention
              <span className="mono" style={{ marginLeft: 6, color: "var(--ink-48)" }}>
                {invoice.reasons.length} {invoice.reasons.length === 1 ? "reason" : "reasons"}
              </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {invoice.reasons.map((r, i) => (
                <window.ReasonCard key={i} reason={r} byId={byId} onAction={handleReason} />
              ))}
            </div>
          </div>
        )}

        {/* Fields */}
        <div className="review-side-section">
          <div className="review-side-section-title" style={{ display: "flex", alignItems: "center" }}>
            <span>Extracted fields</span>
            {manualMode && (
              <span className="source" data-kind="manual" style={{ marginLeft: 8 }}>
                <window.Icons.pen />
                <span>Manual entry mode</span>
              </span>
            )}
            <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--ink-48)" }}>
              cascade: {invoice.cascade.length ? invoice.cascade.join(" → ") : "—"}
            </span>
          </div>

          <div className="card" style={{ marginBottom: 12 }}>
            {FIELDS.map(({ key, label }) => (
              <window.FieldRow
                key={key}
                name={key}
                label={label}
                field={fields[key] ?? null}
                isActive={activeField === key}
                onActivate={setActiveField}
                isEditing={editingField === key}
                onEdit={manualMode || invoice.review_status === "pending" ? setEditingField : null}
                onCommit={commitField}
              />
            ))}
          </div>
        </div>

        {/* Vendor memory */}
        {invoice.vendorMemory && (
          <div className="review-side-section">
            <div className="review-side-section-title">Vendor memory</div>
            <VendorMemoryCard memory={invoice.vendorMemory} vendor={invoice.vendor} />
          </div>
        )}

        {/* Cascade trace — depth signal */}
        {invoice.cascade.length > 0 && (
          <div className="review-side-section">
            <div className="review-side-section-title">Cascade trace</div>
            <CascadeTrace cascade={invoice.cascade} />
          </div>
        )}

        <div style={{ height: 24 }} />
      </div>
    </div>
  );
}

function ReviewHeader({ invoice, onBack }) {
  return (
    <div style={{
      padding: "14px 16px",
      borderBottom: "1px solid var(--hairline)",
      background: "var(--canvas)",
      position: "sticky",
      top: 0,
      zIndex: 4,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <button className="btn" data-variant="ghost" data-size="sm" onClick={onBack}>
          <window.Icons.arrowL />
          <span>Inbox</span>
        </button>
        <window.TriagePill variant={invoice.triage_state} pct={invoice.minConfidence} />
        <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          <window.Btn size="sm" variant="ghost" icon={window.Icons.refresh} title="Retry extraction" />
        </div>
      </div>

      <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: "-0.01em" }}>
        {invoice.vendor}
      </div>
      <div className="muted" style={{ fontSize: 12, marginTop: 2, display: "flex", gap: 10 }}>
        <span className="mono">{invoice.invoiceNumber ?? "no invoice #"}</span>
        <span>·</span>
        <span>{invoice.uploaded}</span>
        {invoice.total != null && (
          <>
            <span>·</span>
            <span className="num" style={{ color: "var(--ink)", fontWeight: 500 }}>
              {invoice.currency} {window.formatNumber(invoice.total)}
            </span>
          </>
        )}
      </div>

      {/* Primary actions */}
      <div style={{ display: "flex", gap: 6, marginTop: 12 }}>
        <window.Btn variant="primary" icon={window.Icons.check}>
          Confirm
          <span style={{
            marginLeft: 4, padding: "0 4px", background: "rgba(255,255,255,0.12)",
            borderRadius: 3, fontFamily: "var(--font-mono)", fontSize: 10,
          }}>C</span>
        </window.Btn>
        <window.Btn icon={window.Icons.x}>Dismiss</window.Btn>
        <window.Btn variant="ghost" icon={window.Icons.cascade}>Force Opus</window.Btn>
      </div>
    </div>
  );
}

function VendorMemoryCard({ memory, vendor }) {
  if (memory.invoicesSeen === 0) {
    return (
      <div className="card" style={{ padding: 14, fontSize: 12.5, color: "var(--ink-80)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <window.Icons.vendor />
          <b>No history yet</b>
        </div>
        <div className="muted" style={{ fontSize: 12 }}>
          This is the first invoice from <b>{vendor}</b>. Confirming will seed the vendor memory:
          format hints, typical totals, payment cadence.
        </div>
      </div>
    );
  }
  return (
    <div className="card">
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", borderBottom: "1px solid var(--hairline)" }}>
        <Cell label="Invoices seen" value={memory.invoicesSeen} mono />
        <Cell label="Avg total" value={`$${window.formatNumber(memory.avgTotal ?? 0)}`} mono right />
      </div>
      <div style={{ padding: "10px 14px" }}>
        <div className="muted" style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
          Patterns learned
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          {memory.patterns.map((p, i) => (
            <div key={i} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12.5 }}>
              <span style={{
                width: 14, height: 14, borderRadius: 3,
                background: "oklch(0.95 0.04 290)", color: "oklch(0.4 0.13 290)",
                display: "grid", placeItems: "center", flexShrink: 0,
              }}>
                <window.Icons.brain />
              </span>
              <span style={{ color: "var(--ink-80)" }}>{p}</span>
            </div>
          ))}
        </div>
        {memory.lastSeen && (
          <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--hairline)", fontSize: 11.5, color: "var(--ink-60)" }}>
            Last seen <span className="mono">{memory.lastSeen}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function Cell({ label, value, mono, right }) {
  return (
    <div style={{
      padding: "10px 14px",
      borderRight: !right ? "1px solid var(--hairline)" : "none",
    }}>
      <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-48)" }}>
        {label}
      </div>
      <div className={mono ? "num" : ""} style={{
        fontSize: 15, fontWeight: 500, color: "var(--ink)", marginTop: 2,
        textAlign: right ? "right" : "left",
      }}>
        {value}
      </div>
    </div>
  );
}

const TIER_META = {
  haiku:  { label: "Haiku 4.5",  color: "var(--ink-60)",  bg: "var(--surface-recess)",  cost: "$0.001" },
  sonnet: { label: "Sonnet 4.6", color: "#1d6280",        bg: "#e7f1f6",  cost: "$0.012" },
  opus:   { label: "Opus 4.7",   color: "#6b3b8c",        bg: "#f3e9f9",  cost: "$0.060" },
};
function CascadeTrace({ cascade }) {
  return (
    <div className="card" style={{ padding: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
        {cascade.map((tier, i) => {
          const m = TIER_META[tier];
          return (
            <React.Fragment key={tier}>
              <div style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "4px 8px", borderRadius: 6,
                background: m.bg, color: m.color,
                border: "1px solid var(--hairline)",
                fontSize: 12, fontFamily: "var(--font-mono)",
              }}>
                <span style={{ width: 6, height: 6, borderRadius: 50, background: m.color }} />
                <span>{m.label}</span>
                <span style={{ opacity: 0.6 }}>{m.cost}</span>
              </div>
              {i < cascade.length - 1 && <span style={{ color: "var(--ink-48)" }}>→</span>}
            </React.Fragment>
          );
        })}
      </div>
      <div className="muted" style={{ fontSize: 11.5, marginTop: 8, lineHeight: 1.5 }}>
        {cascade.length === 1
          ? "First tier returned high composite confidence — no escalation needed."
          : cascade.length === 2
            ? "Haiku's output triggered the cascade (math fails or low confidence). Sonnet's values shown above."
            : "Sonnet disagreed with Haiku on disputed fields. Opus broke the tie — agreement scores merged into composite."}
      </div>
    </div>
  );
}

Object.assign(window, { ReviewScreen });
