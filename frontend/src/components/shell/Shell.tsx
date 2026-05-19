import { useEffect, useMemo, useReducer } from "react";
import {
  Link,
  Navigate,
  Outlet,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";

import { Icons } from "@/components/primitives/Icons";
import { Kbd } from "@/components/primitives/Kbd";
import { LoadingSplash } from "@/components/primitives/LoadingSplash";
import { SiftMark } from "@/components/primitives/SiftMark";
import { SearchPalette } from "@/components/search-palette/SearchPalette";
import { ApiUsageIndicator } from "@/components/shell/ApiUsageIndicator";
import { TourProvider, useTour } from "@/components/tour/TourProvider";
import { useLogoutMutation, useMeQuery } from "@/state/auth";
import { useAnomalyCountQuery } from "@/state/anomalies";
import { useAppMetaQuery, useInboxQuery } from "@/state/invoices";

interface OverlayState {
  paletteOpen: boolean;
  helpOpen: boolean;
}

type OverlayAction =
  | { type: "openPalette" }
  | { type: "closePalette" }
  | { type: "toggleHelp" }
  | { type: "closeAll" };

function overlayReducer(
  state: OverlayState,
  action: OverlayAction,
): OverlayState {
  switch (action.type) {
    case "openPalette":
      return { ...state, paletteOpen: true };
    case "closePalette":
      return { ...state, paletteOpen: false };
    case "toggleHelp":
      return { ...state, helpOpen: !state.helpOpen };
    case "closeAll":
      return { paletteOpen: false, helpOpen: false };
  }
}

export function Shell() {
  return (
    <TourProvider>
      <ShellInner />
    </TourProvider>
  );
}

function ShellInner() {
  const navigate = useNavigate();
  const { data: me, isLoading: meLoading } = useMeQuery();
  const logout = useLogoutMutation();
  const location = useLocation();
  const params = useParams();
  const tour = useTour();
  const [overlay, dispatch] = useReducer(overlayReducer, {
    paletteOpen: false,
    helpOpen: false,
  });
  const { paletteOpen, helpOpen } = overlay;
  const { data: invoices = [] } = useInboxQuery();
  const { data: meta } = useAppMetaQuery();
  const { data: anomalyCount = 0 } = useAnomalyCountQuery();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const isEditable =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        if (tour.isActive) return;
        e.preventDefault();
        dispatch({ type: "openPalette" });
      } else if (!isEditable && e.key === "?") {
        if (tour.isActive) return;
        e.preventDefault();
        dispatch({ type: "toggleHelp" });
      } else if (e.key === "Escape") {
        if (tour.isActive) return;
        dispatch({ type: "closeAll" });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tour.isActive]);

  const counts = useMemo(() => {
    const c = {
      needs_review: 0,
      confident: 0,
      likely_duplicate: 0,
      unprocessable: 0,
    };
    for (const inv of invoices) {
      if (inv.review_status === "unprocessable") {
        c.unprocessable += 1;
        continue;
      }
      const t = inv.current_extraction?.predicted_triage_state;
      if (t === "needs_review") c.needs_review += 1;
      else if (t === "confident" && inv.review_status === "pending")
        c.confident += 1;
      else if (t === "likely_duplicate") c.likely_duplicate += 1;
    }
    return c;
  }, [invoices]);

  const vendorCount = useMemo(() => {
    const names = new Set<string>();
    for (const inv of invoices) {
      const v = inv.current_extraction?.extracted_fields?.vendor_name?.value;
      if (v != null) {
        const name = String(v).trim();
        if (name) names.add(name);
      }
    }
    return names.size;
  }, [invoices]);

  if (meLoading) {
    return <LoadingSplash />;
  }
  if (!me) {
    return <Navigate to="/login" replace />;
  }

  const onInbox = location.pathname === "/inbox" || location.pathname === "/";
  const onVendors = location.pathname === "/vendors";
  const onSearch = location.pathname === "/search";
  const onReview = !onInbox && !onVendors && !onSearch;
  const reviewVendor =
    onReview && params.id
      ? invoices.find((i) => i.id === params.id)?.current_extraction
          ?.extracted_fields?.vendor_name?.value
      : null;

  const screenLabel = onInbox
    ? "01 Inbox"
    : onVendors
      ? "03 Vendors"
      : onSearch
        ? "04 Search"
        : "02 Review";

  return (
    <div className="app" data-screen-label={screenLabel}>
      <aside className="sidebar">
        <div className="sidebar-header">
          <SiftMark size={22} dark />
          <div className="brand-name">
            Sift<span style={{ color: "var(--primary-on-dark)" }}>.</span>
          </div>
          <div className="brand-tag">v0.4</div>
        </div>
        <nav className="nav">
          <div className="nav-section">Workflow</div>
          <Link
            to="/inbox"
            className="nav-item"
            data-active={onInbox}
            style={{ textDecoration: "none" }}
          >
            <Icons.inbox />
            <span>Inbox</span>
            <span className="nav-count">
              {counts.needs_review + counts.confident + counts.likely_duplicate}
            </span>
          </Link>
          <Link
            to="/search"
            className="nav-item"
            data-active={location.pathname === "/search"}
            style={{ textDecoration: "none" }}
          >
            <Icons.search />
            <span>Search</span>
            <span style={{ marginLeft: "auto", display: "flex", gap: 2 }}>
              <Kbd>⌘</Kbd>
              <Kbd>K</Kbd>
            </span>
          </Link>
          <Link
            to="/anomalies"
            className="nav-item"
            data-active={location.pathname === "/anomalies"}
            data-tour="nav-anomalies"
            style={{ textDecoration: "none" }}
          >
            <Icons.bell />
            <span>Anomalies</span>
            <span className="nav-count">{anomalyCount}</span>
          </Link>

          <div className="nav-section">Library</div>
          <Link
            to="/vendors"
            className="nav-item"
            data-active={onVendors}
            style={{ textDecoration: "none" }}
          >
            <Icons.vendor />
            <span>Vendors</span>
            <span className="nav-count">{vendorCount}</span>
          </Link>
        </nav>

        <div className="mt-auto flex flex-col">
          <ApiUsageIndicator />
          <div className="sidebar-footer" style={{ marginTop: 0 }}>
            <button
              type="button"
              onClick={() => {
                logout.mutate(undefined, {
                  onSettled: () => navigate("/login", { replace: true }),
                });
              }}
              className="text-left text-[12px] tracking-[-0.005em] text-light-subtle hover:text-light underline-offset-2 hover:underline disabled:cursor-not-allowed"
              disabled={logout.isPending}
            >
              {logout.isPending ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          {onInbox && (
            <>
              <div className="topbar-title">Inbox</div>
              <div className="topbar-crumbs">
                <span style={{ color: "var(--ink-48)" }}>·</span>
                <span className="mono">{counts.needs_review} need review</span>
                <span style={{ color: "var(--ink-48)" }}>·</span>
                <span className="mono">
                  {counts.confident} ready to confirm
                </span>
              </div>
            </>
          )}
          {onVendors && (
            <>
              <div className="topbar-title">Vendors</div>
              <div className="topbar-crumbs">
                <span style={{ color: "var(--ink-48)" }}>·</span>
                <span className="mono">
                  {vendorCount} {vendorCount === 1 ? "vendor" : "vendors"}{" "}
                  tracked
                </span>
              </div>
            </>
          )}
          {onSearch && (
            <>
              <div className="topbar-title">Search</div>
              <div className="topbar-crumbs">
                <span style={{ color: "var(--ink-48)" }}>·</span>
                <span className="mono">Natural-language query</span>
              </div>
            </>
          )}
          {onReview && (
            <>
              <div className="topbar-title">Review</div>
              <div className="topbar-crumbs">
                <span style={{ color: "var(--ink-48)" }}>/</span>
                <span>{reviewVendor ?? "Invoice"}</span>
              </div>
            </>
          )}

          <div
            className="topbar-search"
            data-tour="topbar-search"
            onClick={() => dispatch({ type: "openPalette" })}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                dispatch({ type: "openPalette" });
              }
            }}
            role="button"
            tabIndex={0}
          >
            <Icons.search />
            <span className="flex-1">Search invoices or ask anything…</span>
            <Kbd>⌘</Kbd>
            <Kbd>K</Kbd>
          </div>

          {meta?.llm_provider === "stub" && <StubModeBadge />}
        </div>

        <div className="flex flex-1 flex-col overflow-hidden">
          <Outlet />
        </div>
      </main>

      {paletteOpen && (
        <SearchPalette
          onClose={() => dispatch({ type: "closePalette" })}
          onOpen={(id) => {
            dispatch({ type: "closePalette" });
            navigate(`/invoice/${id}`);
          }}
        />
      )}

      {helpOpen && (
        <KeyboardHelp
          onClose={() => dispatch({ type: "closeAll" })}
          onStartTour={() => {
            dispatch({ type: "closeAll" });
            tour.start();
          }}
        />
      )}
    </div>
  );
}

function StubModeBadge() {
  return (
    <div
      title="Running with the offline StubLLMClient; no Anthropic API calls. Set SIFT_LLM_PROVIDER=anthropic to use the real cascade."
      className="inline-flex cursor-help items-center gap-1.5 border border-[#e6c75a] bg-[#fff6db] px-2.5 py-1 font-mono text-xs uppercase tracking-[0.06em] text-ink-80"
    >
      <span className="inline-block size-1.5 rounded-full bg-[#c89400]" />
      Stub mode
    </div>
  );
}

const SHORTCUTS: { keys: string[]; description: string }[] = [
  { keys: ["⌘", "K"], description: "Open search palette" },
  { keys: ["?"], description: "Toggle this help" },
  { keys: ["Esc"], description: "Close any open overlay" },
  { keys: ["↵"], description: "Open a row / submit chip" },
  { keys: ["C"], description: "Confirm (on review)" },
  { keys: ["D"], description: "Dismiss (on review)" },
  { keys: ["U"], description: "Mark unprocessable (on review)" },
];

function KeyboardHelp({
  onClose,
  onStartTour,
}: {
  onClose: () => void;
  onStartTour: () => void;
}) {
  const closeOnBackdrop = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose();
  };
  const closeOnEscape = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  };
  return (
    <div
      className="scrim grid place-items-center"
      role="presentation"
      onClick={closeOnBackdrop}
      onKeyDown={closeOnEscape}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
        className="min-w-[380px] max-w-[460px] border border-hairline bg-surface"
      >
        <div className="flex items-center justify-between border-b border-hairline px-[18px] py-3.5 text-[13px] font-medium">
          <span>Keyboard shortcuts</span>
          <Kbd>esc</Kbd>
        </div>
        <div className="py-1">
          {SHORTCUTS.map((s) => (
            <div
              key={s.description}
              className="flex items-center gap-2.5 px-[18px] py-1.5 text-[12.5px]"
            >
              <div className="flex w-[90px] gap-1">
                {s.keys.map((k) => (
                  <Kbd key={`${s.description}-${k}`}>{k}</Kbd>
                ))}
              </div>
              <span className="text-ink-80">{s.description}</span>
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between border-t border-hairline px-[18px] py-3">
          <span className="text-[12px] text-ink-60">New to Sift?</span>
          <button
            type="button"
            onClick={onStartTour}
            className="text-[12px] font-medium text-action transition-colors hover:text-action-focus"
          >
            Take the product tour →
          </button>
        </div>
      </div>
    </div>
  );
}
