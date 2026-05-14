/* global React */
// Search palette — opens on ⌘K. NL → typed chips → results.
// Chips ARE the state (ADR-0004). Untranslated intent surfaces above results.

const { useState, useEffect, useRef, useMemo } = window.React;

// Hand-curated translation map — illustrates the NL → StructuredQuery surface
// without invoking a real LLM. Each entry maps a regex on the input to a query.
const TRANSLATIONS = [
  {
    test: (s) => /vega/i.test(s) && /3\s*month/i.test(s) && /(\$|usd)?\s*5\s*k/i.test(s),
    chips: [
      { field: "vendor_name", op: "eq",      value: "Vega Logistics" },
      { field: "invoice_date", op: "between", value: ["2026-02-13", "2026-05-13"] },
      { field: "total",        op: "gte",     value: 5000 },
    ],
    untranslated: null,
  },
  {
    test: (s) => /duplicate/i.test(s) && /(this month|may)/i.test(s),
    chips: [
      { field: "is_duplicate", op: "eq", value: "true" },
      { field: "invoice_date", op: "between", value: ["2026-05-01", "2026-05-31"] },
    ],
    untranslated: null,
  },
  {
    test: (s) => /needs review/i.test(s) && /acme/i.test(s),
    chips: [
      { field: "triage_state", op: "eq", value: "needs_review" },
      { field: "vendor_name",  op: "contains", value: "Acme" },
    ],
    untranslated: null,
  },
  {
    test: (s) => /high(est)?\s*spend|biggest invoices?|largest/i.test(s),
    chips: [
      { field: "total", op: "gte", value: 10000 },
    ],
    untranslated: "sort by total descending — top N",
  },
  {
    test: (s) => /math.*(fail|wrong|off)/i.test(s),
    chips: [
      { field: "triage_state", op: "eq", value: "needs_review" },
    ],
    untranslated: "filter to math-reconciliation reason only",
  },
  {
    test: (s) => /halcyon|software/i.test(s),
    chips: [
      { field: "vendor_name", op: "contains", value: "Halcyon" },
    ],
    untranslated: null,
  },
];

function translate(q) {
  for (const t of TRANSLATIONS) {
    if (t.test(q)) return { chips: t.chips, untranslated: t.untranslated };
  }
  return { chips: [], untranslated: null };
}

const SUGGESTED = [
  "Vega invoices last 3 months over $5k",
  "duplicates this month",
  "needs review from Acme",
  "biggest invoices this quarter",
  "show extractions where math failed",
];

function SearchPalette({ onClose, onOpen }) {
  const [q, setQ] = useState("Vega invoices last 3 months over $5k");
  const [chips, setChips] = useState([]);
  const [untranslated, setUntranslated] = useState(null);
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  // Translate on q change with a short pause to feel like a real call.
  useEffect(() => {
    if (q.trim() === "") {
      setChips([]); setUntranslated(null); return;
    }
    const id = setTimeout(() => {
      const { chips, untranslated } = translate(q);
      setChips(chips);
      setUntranslated(untranslated);
    }, 220);
    return () => clearTimeout(id);
  }, [q]);

  const results = useMemo(() => filterByChips(window.SIFT_DATA.INVOICES, chips), [chips]);
  const hasQuery = q.trim() !== "";

  return (
    <div className="scrim" onClick={onClose}>
      <div className="palette" onClick={(e) => e.stopPropagation()}>
        {/* Input */}
        <div className="palette-input">
          <window.Icons.search />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search invoices, or ask in plain English…"
            onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}
          />
          <window.Kbd>esc</window.Kbd>
        </div>

        {/* Chips bar */}
        {hasQuery && chips.length > 0 && (
          <div className="palette-chips">
            {chips.map((c, i) => (
              <window.Chip key={i} field={c.field} op={c.op} value={c.value}
                onRemove={() => setChips(cs => cs.filter((_, j) => j !== i))} />
            ))}
            <span className="chip chip-add" onClick={() => {}}>
              <window.Icons.plus />
              <span>Add filter</span>
            </span>
          </div>
        )}

        {/* Untranslated intent */}
        {untranslated && (
          <div className="palette-untranslated">
            <window.Icons.warn />
            <div>
              <b>Partially translated.</b>{" "}
              Couldn't express this in structured query: <span className="mono-snip" style={{
                background: "rgba(255,255,255,0.7)", padding: "0 5px",
                borderRadius: 3, fontFamily: "var(--font-mono)",
              }}>"{untranslated}"</span>{" "}
              — results below ignore that constraint.
            </div>
          </div>
        )}

        {/* Empty-state / suggestions / results */}
        {!hasQuery ? (
          <PaletteSuggestions onPick={setQ} />
        ) : chips.length === 0 ? (
          <div style={{ padding: "28px 18px", fontSize: 13, color: "var(--ink-60)", textAlign: "center" }}>
            No translation yet — try one of the suggestions above, or rephrase.
          </div>
        ) : (
          <PaletteResults results={results} onOpen={(id) => { onOpen?.(id); onClose(); }} />
        )}

        {/* Footer */}
        <div style={{
          display: "flex", alignItems: "center", gap: 14,
          padding: "8px 18px", borderTop: "1px solid var(--hairline)",
          fontSize: 11.5, color: "var(--ink-48)", background: "var(--surface-recess)",
        }}>
          <span><window.Kbd>↑</window.Kbd><window.Kbd>↓</window.Kbd> navigate</span>
          <span><window.Kbd>↵</window.Kbd> open</span>
          <span><window.Kbd>tab</window.Kbd> edit chip</span>
          <span style={{ marginLeft: "auto" }}>{results.length} match{results.length === 1 ? "" : "es"}</span>
        </div>
      </div>
    </div>
  );
}

function PaletteSuggestions({ onPick }) {
  return (
    <div className="palette-section">
      <div className="palette-section-head">Try</div>
      {SUGGESTED.map((s, i) => (
        <div key={i} className="palette-row" onClick={() => onPick(s)}>
          <window.Icons.spark />
          <span>{s}</span>
          <window.Kbd>{`⌘${i+1}`}</window.Kbd>
        </div>
      ))}
    </div>
  );
}

function PaletteResults({ results, onOpen }) {
  return (
    <div className="palette-section" style={{ maxHeight: 360, overflowY: "auto" }}>
      <div className="palette-section-head">Results</div>
      {results.length === 0 ? (
        <div className="palette-row" style={{ color: "var(--ink-48)" }}>
          No invoices match this query.
        </div>
      ) : (
        results.map((inv) => (
          <div key={inv.id} className="palette-row" onClick={() => onOpen?.(inv.id)}>
            <window.Icons.doc />
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, flex: 1, minWidth: 0 }}>
              <span style={{ fontWeight: 500 }}>{inv.vendor}</span>
              <span className="muted mono" style={{ fontSize: 11.5 }}>{inv.invoiceNumber ?? "—"}</span>
              <span className="muted" style={{ fontSize: 11.5 }}>{inv.date}</span>
            </div>
            <span className="num" style={{ fontSize: 12.5, color: "var(--ink-80)" }}>
              {inv.currency} {inv.total != null ? window.formatNumber(inv.total) : "—"}
            </span>
            <window.TriagePill variant={inv.triage_state} />
          </div>
        ))
      )}
    </div>
  );
}

// Apply chip filters to the invoice list — illustrative.
function filterByChips(invoices, chips) {
  return invoices.filter(inv => chips.every(c => match(inv, c)));
}
function match(inv, c) {
  const getField = (name) => {
    switch (name) {
      case "vendor_name":   return inv.vendor;
      case "invoice_date":  return inv.date;
      case "total":         return inv.total;
      case "currency":      return inv.currency;
      case "triage_state":  return inv.triage_state;
      case "is_duplicate":  return inv.triage_state === "likely_duplicate" ? "true" : "false";
      default: return null;
    }
  };
  const v = getField(c.field);
  if (v == null) return false;
  switch (c.op) {
    case "eq":       return String(v) === String(c.value);
    case "neq":      return String(v) !== String(c.value);
    case "gt":       return Number(v) >   Number(c.value);
    case "gte":      return Number(v) >=  Number(c.value);
    case "lt":       return Number(v) <   Number(c.value);
    case "lte":      return Number(v) <=  Number(c.value);
    case "contains": return String(v).toLowerCase().includes(String(c.value).toLowerCase());
    case "between": {
      const [a, b] = c.value;
      return String(v) >= String(a) && String(v) <= String(b);
    }
    default: return true;
  }
}

Object.assign(window, { SearchPalette });
