/* global React */
// Inbox — table of invoices, status filters, dropzone, "Why" column for reasons.

const { useState, useMemo } = window.React;

function InboxScreen({ onOpen, onTriggerSearch }) {
  const { INVOICES, COUNTS } = window.SIFT_DATA;
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState(null);
  const [dragOver, setDragOver] = useState(false);

  const filtered = useMemo(() => {
    return INVOICES.filter(inv => {
      if (filter === "all") return true;
      if (filter === "needs_review") return inv.triage_state === "needs_review";
      if (filter === "confident") return inv.triage_state === "confident" && inv.review_status === "pending";
      if (filter === "likely_duplicate") return inv.triage_state === "likely_duplicate";
      if (filter === "unprocessable") return inv.review_status === "unprocessable";
      if (filter === "confirmed") return inv.review_status === "confirmed";
      return true;
    });
  }, [filter, INVOICES]);

  return (
    <div className="inbox-content">
      {/* Dropzone */}
      <div
        className="dropzone"
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); }}
        style={dragOver ? { borderColor: "var(--primary)", background: "var(--primary-bg-soft)" } : null}
      >
        <div className="dropzone-icon"><window.Icons.upload /></div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 500, color: "var(--ink)", fontSize: 13.5 }}>
            Drop invoices to extract
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
            Digital or scanned PDF · We hash, route through Haiku → Sonnet → Opus as needed, and triage in &lt; 8s
          </div>
        </div>
        <window.Btn variant="primary" icon={window.Icons.upload}>Upload</window.Btn>
      </div>

      {/* Toolbar */}
      <div className="inbox-toolbar" style={{ marginTop: 16 }}>
        <div className="seg" role="tablist">
          <FilterTab id="all"              cur={filter} set={setFilter} label="All"            count={COUNTS.all} />
          <FilterTab id="needs_review"     cur={filter} set={setFilter} label="Needs review"   count={COUNTS.needs_review}     variant="needs_review" />
          <FilterTab id="confident"        cur={filter} set={setFilter} label="Confident"      count={COUNTS.confident}        variant="confident" />
          <FilterTab id="likely_duplicate" cur={filter} set={setFilter} label="Duplicates"     count={COUNTS.likely_duplicate} variant="likely_duplicate" />
          <FilterTab id="unprocessable"    cur={filter} set={setFilter} label="Unprocessable"  count={COUNTS.unprocessable}    variant="unprocessable" />
          <FilterTab id="confirmed"        cur={filter} set={setFilter} label="Confirmed"      count={COUNTS.confirmed} />
        </div>

        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <window.Btn variant="ghost" size="sm" icon={window.Icons.filter}>Filter</window.Btn>
          <window.Btn variant="ghost" size="sm" icon={window.Icons.download}>Export</window.Btn>
          {selected != null && (
            <>
              <span className="mono" style={{ alignSelf: "center", fontSize: 12, color: "var(--ink-60)" }}>
                1 selected
              </span>
              <window.Btn size="sm" icon={window.Icons.check} variant="primary">Confirm</window.Btn>
            </>
          )}
        </div>
      </div>

      {/* Table */}
      <div style={{ border: "1px solid var(--hairline)", overflow: "hidden", background: "var(--surface)" }}>
        <table className="table">
          <thead>
            <tr>
              <th style={{ width: 40 }}></th>
              <th style={{ width: 150 }}>Triage</th>
              <th>Vendor</th>
              <th>Invoice #</th>
              <th>Date</th>
              <th className="col-right">Amount</th>
              <th>Why</th>
              <th style={{ width: 76 }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(inv => (
              <tr key={inv.id}
                  data-selected={selected === inv.id ? "true" : "false"}
                  onClick={() => onOpen?.(inv.id)}>
                <td onClick={(e) => { e.stopPropagation(); setSelected(s => s === inv.id ? null : inv.id); }}>
                  <input type="checkbox" checked={selected === inv.id} readOnly
                         style={{ accentColor: "var(--primary)", cursor: "pointer" }} />
                </td>
                <td>
                  <window.TriagePill variant={inv.triage_state} pct={inv.minConfidence} />
                </td>
                <td style={{ fontWeight: 500 }}>{inv.vendor}</td>
                <td className="num muted">{inv.invoiceNumber ?? "—"}</td>
                <td className="num muted">{inv.date ?? "—"}</td>
                <td className="col-right num">
                  {inv.total != null
                    ? <span><span className="muted" style={{ marginRight: 4 }}>{inv.currency}</span>{window.formatNumber(inv.total)}</span>
                    : <span className="subtle">—</span>}
                </td>
                <td>
                  {inv.reasons.length === 0 ? (
                    <span className="subtle">—</span>
                  ) : (
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {inv.reasons.slice(0, 2).map((r, i) => (
                        <WhyChip key={i} reason={r} />
                      ))}
                      {inv.reasons.length > 2 && (
                        <span className="subtle mono" style={{ fontSize: 11 }}>+{inv.reasons.length - 2}</span>
                      )}
                    </div>
                  )}
                </td>
                <td>
                  <StatusBadge status={inv.review_status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Bottom hint */}
      <div style={{
        marginTop: 14, fontSize: 12, color: "var(--ink-48)",
        display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
      }}>
        <span><window.Kbd>J</window.Kbd> <window.Kbd>K</window.Kbd> navigate</span>
        <span style={{ width: 1, height: 10, background: "var(--hairline)" }} />
        <span><window.Kbd>Enter</window.Kbd> open</span>
        <span style={{ width: 1, height: 10, background: "var(--hairline)" }} />
        <span><window.Kbd>C</window.Kbd> confirm</span>
        <span style={{ width: 1, height: 10, background: "var(--hairline)" }} />
        <span><window.Kbd>X</window.Kbd> dismiss</span>
        <span style={{ width: 1, height: 10, background: "var(--hairline)" }} />
        <span><window.Kbd>⌘</window.Kbd> <window.Kbd>K</window.Kbd> natural-language search</span>
        <span style={{ marginLeft: "auto" }}>{filtered.length} of {INVOICES.length} invoices</span>
      </div>
    </div>
  );
}

function FilterTab({ id, cur, set, label, count, variant }) {
  const active = cur === id;
  return (
    <button data-active={active} onClick={() => set(id)}>
      {variant && <span className="pill-dot" style={{
        width: 6, height: 6, borderRadius: 50,
        background:
          variant === "confident" ? "var(--triage-confident)" :
          variant === "needs_review" ? "var(--triage-needs-review)" :
          variant === "likely_duplicate" ? "var(--triage-duplicate)" :
          "var(--triage-unprocessable)",
      }} />}
      <span>{label}</span>
      <span className="seg-count">{count}</span>
    </button>
  );
}

function WhyChip({ reason }) {
  const META = {
    math_fails:       { Icon: window.Icons.warn,   label: `off $${reason.delta?.toFixed(2)}`, tone: "warn" },
    duplicate_of:     { Icon: window.Icons.copy,   label: "duplicate match",                  tone: "dup" },
    low_confidence:   { Icon: window.Icons.alert,  label: `low conf · ${reason.field}`,       tone: "warn" },
    missing_field:    { Icon: window.Icons.alert,  label: `missing ${reason.field}`,          tone: "warn" },
    anomaly:          { Icon: window.Icons.spark,  label: `${reason.z_score?.toFixed(1)}σ anomaly`, tone: "anom" },
    unseen_vendor:    { Icon: window.Icons.vendor, label: "first invoice",                    tone: "neutral" },
    extraction_failed:{ Icon: window.Icons.lock,   label: reason.stage,                       tone: "fail" },
  };
  const m = META[reason.type];
  if (!m) return null;
  const colors = {
    warn:    { bg: "var(--triage-needs-review-bg)", fg: "var(--triage-needs-review)", bd: "#ebd0a8" },
    dup:     { bg: "var(--triage-duplicate-bg)",    fg: "var(--triage-duplicate)",    bd: "#c4d4ee" },
    anom:    { bg: "#f3e9f9",                       fg: "#6b3b8c",                     bd: "#e2cae8" },
    fail:    { bg: "var(--surface-recess)",         fg: "var(--ink-60)",               bd: "var(--hairline)" },
    neutral: { bg: "var(--surface-recess)",         fg: "var(--ink-80)",               bd: "var(--hairline)" },
  }[m.tone];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      padding: "2px 7px", borderRadius: 4,
      background: colors.bg, color: colors.fg, border: `1px solid ${colors.bd}`,
      fontSize: 11, fontFamily: "var(--font-mono)",
      lineHeight: 1.5, whiteSpace: "nowrap",
    }}>
      <m.Icon />
      <span>{m.label}</span>
    </span>
  );
}

function StatusBadge({ status }) {
  const META = {
    pending:        { label: "Pending",        color: "var(--ink-60)",            bg: "var(--surface-recess)" },
    confirmed:      { label: "Confirmed",      color: "var(--triage-confident)",  bg: "var(--triage-confident-bg)" },
    dismissed:      { label: "Dismissed",      color: "var(--ink-48)",            bg: "var(--surface-recess)" },
    unprocessable:  { label: "Unprocessable",  color: "var(--triage-unprocessable)", bg: "var(--surface-recess)" },
  };
  const m = META[status] ?? META.pending;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center",
      padding: "2px 7px", borderRadius: 4,
      fontSize: 11.5, color: m.color, background: m.bg,
      border: "1px solid var(--hairline)", fontFamily: "var(--font-mono)",
    }}>{m.label}</span>
  );
}

Object.assign(window, { InboxScreen });
