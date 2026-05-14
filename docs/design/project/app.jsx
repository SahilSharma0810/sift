/* global React, ReactDOM */
// Sift — root app: sidebar nav, top bar, screen routing, ⌘K palette, tweaks panel.

const { useState, useEffect, useMemo } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "density": "comfortable",
  "accent": "indigo",
  "pillStyle": "soft"
}/*EDITMODE-END*/;

const ACCENTS = {
  indigo: "#0066cc",
  emerald: "#0a7c46",
  amber: "#b25b00",
  rose: "#b22020",
};

function App() {
  const [route, setRoute] = useState({ name: "inbox" });
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [tweaks, setTweak] = window.useTweaks(TWEAK_DEFAULTS);

  // Apply accent — single quiet blue replaced by user's pick
  useEffect(() => {
    const v = ACCENTS[tweaks.accent] ?? ACCENTS.indigo;
    document.documentElement.style.setProperty("--primary", v);
    document.documentElement.style.setProperty("--primary-focus", v);
  }, [tweaks.accent]);

  // Apply density
  useEffect(() => {
    const r = document.documentElement;
    if (tweaks.density === "compact") {
      r.style.setProperty("font-size", "14px");
    } else if (tweaks.density === "spacious") {
      r.style.setProperty("font-size", "16px");
    } else {
      r.style.setProperty("font-size", "15px");
    }
  }, [tweaks.density]);

  // ⌘K handler
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      } else if (e.key === "Escape") {
        setPaletteOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const goInbox  = () => setRoute({ name: "inbox" });
  const openInv  = (id) => setRoute({ name: "review", id });

  const { COUNTS } = window.SIFT_DATA;

  return (
    <div className="app" data-screen-label={route.name === "inbox" ? "01 Inbox" : "02 Review"}>
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="brand-mark">S</div>
          <div className="brand-name">Sift</div>
          <div className="brand-tag">v0.4</div>
        </div>
        <nav className="nav">
          <div className="nav-section">Workflow</div>
          <div className="nav-item" data-active={route.name === "inbox"} onClick={goInbox}>
            <window.Icons.inbox /> <span>Inbox</span>
            <span className="nav-count">{COUNTS.needs_review + COUNTS.confident + COUNTS.likely_duplicate}</span>
          </div>
          <div className="nav-item" onClick={() => setPaletteOpen(true)}>
            <window.Icons.search /> <span>Search</span>
            <span style={{ marginLeft: "auto", display: "flex", gap: 2 }}>
              <window.Kbd>⌘</window.Kbd><window.Kbd>K</window.Kbd>
            </span>
          </div>
          <div className="nav-item">
            <window.Icons.bell /> <span>Anomalies</span>
            <span className="nav-count">3</span>
          </div>

          <div className="nav-section">Library</div>
          <div className="nav-item"><window.Icons.vendor /> <span>Vendors</span><span className="nav-count">128</span></div>
          <div className="nav-item"><window.Icons.layers /> <span>Tax breakdowns</span></div>
          <div className="nav-item"><window.Icons.history /> <span>History</span></div>

          <div className="nav-section">System</div>
          <div className="nav-item"><window.Icons.brain /> <span>Vendor memory</span></div>
          <div className="nav-item"><window.Icons.cascade /> <span>Cascade runs</span></div>
        </nav>

        <div className="sidebar-footer">
          <span className="sidebar-footer-dot" />
          <span>All systems normal · Haiku 4.5 / Sonnet 4.6</span>
        </div>
      </aside>

      {/* Main */}
      <main className="main">
        {/* Top bar */}
        <div className="topbar">
          {route.name === "inbox" ? (
            <>
              <div className="topbar-title">Inbox</div>
              <div className="topbar-crumbs">
                <span style={{ color: "var(--ink-48)" }}>·</span>
                <span className="mono">{COUNTS.needs_review} need review</span>
                <span style={{ color: "var(--ink-48)" }}>·</span>
                <span className="mono">{COUNTS.confident} ready to confirm</span>
              </div>
            </>
          ) : (
            <>
              <div className="topbar-title">Review</div>
              <div className="topbar-crumbs">
                <span style={{ color: "var(--ink-48)" }}>/</span>
                <span>{window.SIFT_DATA.INVOICES.find(i => i.id === route.id)?.vendor}</span>
              </div>
            </>
          )}

          <div className="topbar-search" onClick={() => setPaletteOpen(true)}>
            <window.Icons.search />
            <span style={{ flex: 1 }}>Search invoices or ask anything…</span>
            <window.Kbd>⌘</window.Kbd><window.Kbd>K</window.Kbd>
          </div>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          {route.name === "inbox"
            ? <window.InboxScreen onOpen={openInv} onTriggerSearch={() => setPaletteOpen(true)} />
            : <window.ReviewScreen invoiceId={route.id} onBack={goInbox} onOpen={openInv} />
          }
        </div>
      </main>

      {/* Palette */}
      {paletteOpen && (
        <window.SearchPalette
          onClose={() => setPaletteOpen(false)}
          onOpen={openInv}
        />
      )}

      {/* Tweaks panel */}
      <window.TweaksPanel title="Tweaks">
        <window.TweakSection label="Display">
          <window.TweakRadio
            label="Density"
            value={tweaks.density}
            onChange={(v) => setTweak("density", v)}
            options={[
              { value: "compact",     label: "Tight" },
              { value: "comfortable", label: "Comfy" },
              { value: "spacious",    label: "Roomy" },
            ]}
          />
          <window.TweakSelect
            label="Accent"
            value={tweaks.accent}
            onChange={(v) => setTweak("accent", v)}
            options={[
              { value: "indigo",  label: "Indigo" },
              { value: "emerald", label: "Emerald" },
              { value: "amber",   label: "Amber" },
              { value: "rose",    label: "Rose" },
            ]}
          />
        </window.TweakSection>
        <window.TweakSection label="Triage pills">
          <window.TweakRadio
            label="Style"
            value={tweaks.pillStyle}
            onChange={(v) => setTweak("pillStyle", v)}
            options={[
              { value: "soft",    label: "Soft" },
              { value: "solid",   label: "Solid" },
              { value: "outline", label: "Outline" },
            ]}
          />
        </window.TweakSection>
        <window.TweakSection label="Jump to invoice">
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {window.SIFT_DATA.INVOICES.filter(i => i.review_status !== "confirmed").map(i => (
              <button key={i.id}
                      onClick={() => openInv(i.id)}
                      style={{
                        textAlign: "left", padding: "6px 8px",
                        border: "1px solid var(--hairline)", borderRadius: 6,
                        background: "var(--surface)", fontSize: 12.5,
                        display: "flex", alignItems: "center", gap: 8, cursor: "pointer",
                      }}>
                <window.TriagePill variant={i.triage_state} />
                <span>{i.vendor}</span>
              </button>
            ))}
          </div>
        </window.TweakSection>
      </window.TweaksPanel>

      {/* Pill style override */}
      <PillStyleOverride mode={tweaks.pillStyle} />
    </div>
  );
}

// Tweakable pill style — emit a <style> override based on the mode.
function PillStyleOverride({ mode }) {
  if (mode === "soft") return null;
  if (mode === "solid") {
    return (
      <style>{`
        .pill[data-variant="confident"] { background: var(--triage-confident); color: white; border-color: var(--triage-confident); }
        .pill[data-variant="confident"] .pill-dot { background: white; }
        .pill[data-variant="needs_review"] { background: var(--triage-needs-review); color: white; border-color: var(--triage-needs-review); }
        .pill[data-variant="needs_review"] .pill-dot { background: white; }
        .pill[data-variant="likely_duplicate"] { background: var(--triage-duplicate); color: white; border-color: var(--triage-duplicate); }
        .pill[data-variant="likely_duplicate"] .pill-dot { background: white; }
        .pill[data-variant="unprocessable"] { background: var(--triage-unprocessable); color: white; border-color: var(--triage-unprocessable); }
        .pill[data-variant="unprocessable"] .pill-dot { background: white; }
        .pill .pill-pct { opacity: 0.9; }
      `}</style>
    );
  }
  if (mode === "outline") {
    return (
      <style>{`
        .pill { background: transparent !important; }
        .pill[data-variant="confident"] { color: var(--triage-confident); border-color: var(--triage-confident); }
        .pill[data-variant="needs_review"] { color: oklch(0.42 0.13 70); border-color: var(--triage-needs-review); }
        .pill[data-variant="likely_duplicate"] { color: var(--triage-duplicate); border-color: var(--triage-duplicate); }
        .pill[data-variant="unprocessable"] { color: var(--triage-unprocessable); border-color: var(--triage-unprocessable); }
      `}</style>
    );
  }
  return null;
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
