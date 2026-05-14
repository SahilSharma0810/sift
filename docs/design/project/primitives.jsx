/* global React */
// Sift design-system primitives — every reusable atom and small molecule.
// Exported to window so the screen modules can pick them up regardless of file order.

const { useEffect, useRef, useState } = React;

// ── Tiny inline icons ──────────────────────────────────────────────────────────
// Keep them simple: stroke-based, 14px viewBox 24x24, currentColor.
const Icon = ({ d, size = 14, fill = "none", strokeWidth = 1.75 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke="currentColor"
       strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);
const Icons = {
  inbox:    () => <Icon d="M3 13l3-8h12l3 8M3 13v6a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-6M3 13h5l1 3h6l1-3h5" />,
  search:   () => <Icon d="M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3" />,
  bell:     () => <Icon d="M18 16v-5a6 6 0 1 0-12 0v5l-2 2h16l-2-2zM9 19a3 3 0 0 0 6 0" />,
  spark:    () => <Icon d="M12 3v3M12 18v3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M3 12h3M18 12h3M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" />,
  vendor:   () => <Icon d="M3 21h18M5 21V8l7-4 7 4v13M9 21V13h6v8" />,
  doc:      () => <Icon d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M9 13h6M9 17h4" />,
  upload:   () => <Icon d="M12 16V4M6 10l6-6 6 6M4 20h16" />,
  check:    () => <Icon d="M5 12l5 5L20 7" />,
  x:        () => <Icon d="M6 6l12 12M18 6 6 18" />,
  warn:     () => <Icon d="M12 9v4M12 17h.01M10.3 4l-8 14a2 2 0 0 0 1.7 3h16a2 2 0 0 0 1.7-3l-8-14a2 2 0 0 0-3.4 0z" />,
  alert:    () => <Icon d="M12 8v4M12 16h.01M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z" />,
  copy:     () => <Icon d="M8 4h10a2 2 0 0 1 2 2v10M16 8H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />,
  hash:     () => <Icon d="M4 9h16M4 15h16M10 3 8 21M16 3l-2 18" />,
  brain:    () => <Icon d="M9 4a3 3 0 0 0-3 3v0a3 3 0 0 0-1 5.8V15a3 3 0 0 0 4 2.8V21M15 4a3 3 0 0 1 3 3v0a3 3 0 0 1 1 5.8V15a3 3 0 0 1-4 2.8V21" />,
  bot:      () => <Icon d="M9 2v3M15 2v3M5 8h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2zM9 13h.01M15 13h.01" />,
  pen:      () => <Icon d="M12 19l7-7 3 3-7 7-3-3zM18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5zM2 2l7.6 7.6M11 11a2 2 0 1 0 4 0 2 2 0 0 0-4 0z" />,
  lock:     () => <Icon d="M5 12h14a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1zM8 12V7a4 4 0 1 1 8 0v5" />,
  refresh:  () => <Icon d="M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5" />,
  arrowL:   () => <Icon d="M19 12H5M12 19l-7-7 7-7" />,
  chevron:  () => <Icon d="M9 18l6-6-6-6" />,
  filter:   () => <Icon d="M3 5h18M6 12h12M10 19h4" />,
  layers:   () => <Icon d="M12 2 2 8l10 6 10-6-10-6zM2 16l10 6 10-6M2 12l10 6 10-6" />,
  command:  () => <Icon d="M9 6V9H6a3 3 0 1 1 3-3zM15 6V9h3a3 3 0 1 0-3-3zM9 18v-3H6a3 3 0 1 0 3 3zM15 18v-3h3a3 3 0 1 1-3 3zM9 9h6v6H9z" />,
  dollar:   () => <Icon d="M12 2v20M17 6H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />,
  plus:     () => <Icon d="M12 5v14M5 12h14" />,
  cascade:  () => <Icon d="M4 6h10l2 3 2-3h2M4 12h6l2 3 2-3h6M4 18h12l2 3 2-3" />,
  zap:      () => <Icon d="M13 2L3 14h7l-1 8 10-12h-7l1-8z" />,
  history:  () => <Icon d="M12 8v4l3 2M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5" />,
  link:     () => <Icon d="M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" />,
  eye:      () => <Icon d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12zM12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6z" />,
  download: () => <Icon d="M12 4v12M6 10l6 6 6-6M4 20h16" />,
};
const Kbd = ({ children }) => <kbd className="kbd">{children}</kbd>;

// ── TriagePill ────────────────────────────────────────────────────────────────
const TRIAGE_LABELS = {
  confident: "Confident",
  needs_review: "Needs review",
  likely_duplicate: "Likely duplicate",
  unprocessable: "Unprocessable",
};
function TriagePill({ variant, pct }) {
  return (
    <span className="pill" data-variant={variant}>
      <span className="pill-dot" />
      <span>{TRIAGE_LABELS[variant]}</span>
      {pct != null && variant !== "unprocessable" && (
        <span className="pill-pct">{Math.round(pct * 100)}%</span>
      )}
    </span>
  );
}

// ── ConfidenceBadge ──────────────────────────────────────────────────────────
function ConfidenceBadge({ value }) {
  if (value == null || value === 0) {
    return <span className="conf" data-tone="low" style={{ "--w": "0%" }}>—</span>;
  }
  const pct = Math.round(value * 100);
  const tone = pct >= 85 ? "high" : pct >= 60 ? "mid" : "low";
  return (
    <span className="conf" data-tone={tone} style={{ "--w": `${pct}%` }} title={`Composite confidence: ${pct}%`}>
      <span className="conf-bar"><span className="conf-bar-fill" /></span>
      <span>{pct}</span>
    </span>
  );
}

// ── SourceBadge ──────────────────────────────────────────────────────────────
const SOURCE_META = {
  haiku:   { kind: "haiku",   label: "Haiku",  Icon: Icons.bot },
  sonnet:  { kind: "sonnet",  label: "Sonnet", Icon: Icons.spark },
  opus:    { kind: "sonnet",  label: "Opus",   Icon: Icons.zap },
  memory:  { kind: "memory",  label: "Vendor memory", Icon: Icons.brain },
  manual:  { kind: "manual",  label: "Manual",   Icon: Icons.pen },
};
function SourceBadge({ source }) {
  const m = SOURCE_META[source] ?? SOURCE_META.haiku;
  return (
    <span className="source" data-kind={m.kind} title={`Value from ${m.label}`}>
      <m.Icon />
      <span>{m.label}</span>
    </span>
  );
}

// ── Chip (for filter/query) ───────────────────────────────────────────────────
const OP_DISPLAY = {
  eq: "=", neq: "≠", gt: ">", gte: "≥", lt: "<", lte: "≤",
  in: "in", between: "between", contains: "contains", fts_matches: "matches",
};
function Chip({ field, op, value, onRemove }) {
  return (
    <span className="chip">
      <span className="chip-key">{field}</span>
      <span className="chip-op">{OP_DISPLAY[op] ?? op}</span>
      <span>{Array.isArray(value) ? value.join(" – ") : String(value)}</span>
      {onRemove && (
        <button className="chip-x" aria-label="Remove filter" onClick={onRemove}>
          <Icons.x />
        </button>
      )}
    </span>
  );
}

// ── Button ───────────────────────────────────────────────────────────────────
function Btn({ children, variant, size, icon: IconComp, onClick, title }) {
  return (
    <button className="btn" data-variant={variant} data-size={size} onClick={onClick} title={title}>
      {IconComp && <IconComp />}
      {children && <span>{children}</span>}
    </button>
  );
}

// ── FieldRow ─────────────────────────────────────────────────────────────────
// Interactive: hover highlights bbox, click sets active. In "edit" mode, the value
// becomes an input.
function FieldRow({ name, label, field, isActive, onActivate, isEditing, onEdit, onCommit }) {
  const [draft, setDraft] = useState(field?.value ?? "");
  useEffect(() => { setDraft(field?.value ?? ""); }, [field?.value]);

  const empty = field?.value == null || field?.value === "";
  return (
    <div className="field"
         data-active={isActive ? "true" : "false"}
         onMouseEnter={() => onActivate?.(name)}
         onMouseLeave={() => onActivate?.(null)}
         onClick={() => onActivate?.(name)}>
      <div className="field-label">{label}</div>
      <div className="field-value">
        {isEditing ? (
          <input
            className="field-edit-input"
            autoFocus
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onBlur={() => onCommit?.(name, draft)}
            onKeyDown={(e) => {
              if (e.key === "Enter") { e.currentTarget.blur(); }
              if (e.key === "Escape") { setDraft(field?.value ?? ""); onEdit?.(null); }
            }}
          />
        ) : empty ? (
          <span className="v-empty">empty</span>
        ) : (
          <span className={typeof field.value === "number" || /[\d-/]/.test(String(field.value)) ? "v-mono" : ""}>
            {typeof field.value === "number" ? formatNumber(field.value) : field.value}
          </span>
        )}
      </div>
      <div className="field-meta">
        {field && <ConfidenceBadge value={field.confidence} />}
        {field && <SourceBadge source={field.source} />}
        {!isEditing && onEdit && (
          <button className="btn" data-variant="ghost" data-size="sm" title="Edit field"
                  onClick={(e) => { e.stopPropagation(); onEdit(name); }}>
            <Icons.pen />
          </button>
        )}
      </div>
    </div>
  );
}

function formatNumber(n) {
  if (typeof n !== "number") return String(n);
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ── ReasonCard — typed dispatch on r.type ────────────────────────────────────
function ReasonCard({ reason, byId, onAction }) {
  const r = reason;
  switch (r.type) {
    case "math_fails":
      return (
        <div className="reason" data-kind="math_fails">
          <div className="reason-icon"><Icons.warn /></div>
          <div className="reason-body">
            <div className="reason-title">Math doesn't reconcile</div>
            <div className="reason-detail">
              <span className="mono-snip">subtotal {formatNumber(r.subtotal)} + tax {formatNumber(r.tax)} = {formatNumber(r.subtotal + r.tax)}</span>
              {" "}but invoice says total <span className="mono-snip">{formatNumber(r.total)}</span>
              {" "}— off by <span className="mono-snip">{r.delta.toFixed(2)}</span>.
            </div>
            <div className="reason-actions">
              <Btn size="sm" icon={Icons.pen} onClick={() => onAction?.("edit_total")}>Edit total</Btn>
              <Btn size="sm" variant="ghost" icon={Icons.refresh} onClick={() => onAction?.("retry")}>Re-extract</Btn>
            </div>
          </div>
        </div>
      );

    case "duplicate_of": {
      const orig = byId?.[r.invoice_id];
      return (
        <div className="reason" data-kind="duplicate_of">
          <div className="reason-icon"><Icons.copy /></div>
          <div className="reason-body">
            <div className="reason-title">Looks like a duplicate</div>
            <div className="reason-detail">
              {Math.round(r.similarity * 100)}% match against{" "}
              <span className="mono-snip">{orig ? `${orig.invoiceNumber} (${orig.vendor})` : r.invoice_id}</span>
              {" "}— matched on <span className="mono-snip">{r.match_method}</span>.
              {orig && (
                <>
                  {" "}Confirmed on <span className="mono-snip">{orig.uploaded}</span>.
                </>
              )}
            </div>
            <div className="reason-actions">
              <Btn size="sm" icon={Icons.eye} onClick={() => onAction?.("view_dup", r.invoice_id)}>Open original</Btn>
              <Btn size="sm" variant="danger" icon={Icons.x} onClick={() => onAction?.("dismiss_dup")}>Mark duplicate &amp; dismiss</Btn>
              <Btn size="sm" variant="ghost" onClick={() => onAction?.("not_dup")}>Not a duplicate</Btn>
            </div>
          </div>
        </div>
      );
    }

    case "low_confidence":
      return (
        <div className="reason" data-kind="low_confidence">
          <div className="reason-icon"><Icons.alert /></div>
          <div className="reason-body">
            <div className="reason-title">Low confidence on {r.field.replace("_", " ")}</div>
            <div className="reason-detail">
              Composite confidence <span className="mono-snip">{Math.round(r.score * 100)}%</span> — {r.reason}.
            </div>
            <div className="reason-actions">
              <Btn size="sm" icon={Icons.pen} onClick={() => onAction?.("edit_field", r.field)}>Fix {r.field.replace("_", " ")}</Btn>
              <Btn size="sm" variant="ghost" icon={Icons.cascade} onClick={() => onAction?.("force_opus")}>Force Opus</Btn>
            </div>
          </div>
        </div>
      );

    case "missing_field":
      return (
        <div className="reason" data-kind="missing_field">
          <div className="reason-icon"><Icons.alert /></div>
          <div className="reason-body">
            <div className="reason-title">Missing {r.field.replace("_", " ")}</div>
            <div className="reason-detail">
              Required field is empty in the extraction.
            </div>
            <div className="reason-actions">
              <Btn size="sm" icon={Icons.plus} onClick={() => onAction?.("add_field", r.field)}>Add value</Btn>
            </div>
          </div>
        </div>
      );

    case "anomaly":
      return (
        <div className="reason" data-kind="anomaly">
          <div className="reason-icon"><Icons.spark /></div>
          <div className="reason-body">
            <div className="reason-title">Unusual {r.field} for this vendor</div>
            <div className="reason-detail">
              <span className="mono-snip">${formatNumber(r.value)}</span> is{" "}
              <span className="mono-snip">{r.z_score.toFixed(1)}σ</span> above the rolling average of{" "}
              <span className="mono-snip">${formatNumber(r.vendor_avg)}</span> over the last 18 invoices.
            </div>
            <div className="reason-actions">
              <Btn size="sm" icon={Icons.history} onClick={() => onAction?.("see_history")}>See vendor history</Btn>
              <Btn size="sm" variant="ghost" onClick={() => onAction?.("expected")}>This is expected</Btn>
            </div>
          </div>
        </div>
      );

    case "unseen_vendor":
      return (
        <div className="reason" data-kind="unseen_vendor">
          <div className="reason-icon"><Icons.vendor /></div>
          <div className="reason-body">
            <div className="reason-title">First invoice from {r.vendor_name}</div>
            <div className="reason-detail">
              No vendor history yet — confidence scores fall back to the cold-start default of 0.85.
              Confirming this extraction will seed the vendor memory.
            </div>
          </div>
        </div>
      );

    case "extraction_failed":
      return (
        <div className="reason" data-kind="extraction_failed">
          <div className="reason-icon"><Icons.lock /></div>
          <div className="reason-body">
            <div className="reason-title">Couldn't read this PDF</div>
            <div className="reason-detail">
              Failed at stage <span className="mono-snip">{r.stage}</span>: {r.detail}.
            </div>
            <div className="reason-actions">
              <Btn size="sm" icon={Icons.pen} onClick={() => onAction?.("manual_entry")}>Manually enter fields</Btn>
              <Btn size="sm" variant="ghost" icon={Icons.refresh} onClick={() => onAction?.("retry")}>Retry</Btn>
              <Btn size="sm" variant="ghost" onClick={() => onAction?.("mark_unprocessable")}>Mark unprocessable</Btn>
            </div>
          </div>
        </div>
      );

    default:
      return null;
  }
}

Object.assign(window, {
  Icons, Kbd, TriagePill, ConfidenceBadge, SourceBadge,
  Chip, Btn, FieldRow, ReasonCard, formatNumber,
});
