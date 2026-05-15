import { useEffect, useMemo, useState } from 'react'
import { Link, Navigate, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'

import { Icons } from '@/components/primitives/Icons'
import { Kbd } from '@/components/primitives/Kbd'
import { SiftMark } from '@/components/primitives/SiftMark'
import { SearchPalette } from '@/components/search-palette/SearchPalette'
import { useLogoutMutation, useMeQuery } from '@/state/auth'
import { useAnomalyCountQuery } from '@/state/anomalies'
import { useAppMetaQuery, useInboxQuery } from '@/state/invoices'

export function Shell() {
  const navigate = useNavigate()
  const { data: me, isLoading: meLoading } = useMeQuery()
  const logout = useLogoutMutation()
  const location = useLocation()
  const params = useParams()
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const { data: invoices = [] } = useInboxQuery()
  const { data: meta } = useAppMetaQuery()
  const { data: anomalyCount = 0 } = useAnomalyCountQuery()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {

      const target = e.target as HTMLElement | null
      const isEditable =
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable)
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen(true)
      } else if (!isEditable && e.key === '?') {
        e.preventDefault()
        setHelpOpen((v) => !v)
      } else if (e.key === 'Escape') {
        setPaletteOpen(false)
        setHelpOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const counts = useMemo(() => {
    const c = { needs_review: 0, confident: 0, likely_duplicate: 0, unprocessable: 0 }
    for (const inv of invoices) {
      if (inv.review_status === 'unprocessable') {
        c.unprocessable += 1
        continue
      }
      const t = inv.current_extraction?.predicted_triage_state
      if (t === 'needs_review') c.needs_review += 1
      else if (t === 'confident' && inv.review_status === 'pending') c.confident += 1
      else if (t === 'likely_duplicate') c.likely_duplicate += 1
    }
    return c
  }, [invoices])

  const vendorCount = useMemo(() => {
    const names = new Set<string>()
    for (const inv of invoices) {
      const v = inv.current_extraction?.extracted_fields?.vendor_name?.value
      if (v != null) {
        const name = String(v).trim()
        if (name) names.add(name)
      }
    }
    return names.size
  }, [invoices])

  if (meLoading) {
    return (
      <div className="grid h-screen place-items-center bg-canvas text-ink-60 text-sm">
        Loading…
      </div>
    )
  }
  if (!me) {
    return <Navigate to="/login" replace />
  }

  const onInbox = location.pathname === '/inbox' || location.pathname === '/'
  const onVendors = location.pathname === '/vendors'
  const onSearch = location.pathname === '/search'
  const onReview = !onInbox && !onVendors && !onSearch
  const reviewVendor =
    onReview && params.id
      ? invoices.find((i) => i.id === params.id)?.current_extraction?.extracted_fields
          ?.vendor_name?.value
      : null

  const screenLabel = onInbox
    ? '01 Inbox'
    : onVendors
      ? '03 Vendors'
      : onSearch
        ? '04 Search'
        : '02 Review'

  return (
    <div className="app" data-screen-label={screenLabel}>
      <aside className="sidebar">
        <div className="sidebar-header">
          <SiftMark size={22} dark />
          <div className="brand-name">
            Sift<span style={{ color: 'var(--primary-on-dark)' }}>.</span>
          </div>
          <div className="brand-tag">v0.4</div>
        </div>
        <nav className="nav">
          <div className="nav-section">Workflow</div>
          <Link to="/inbox" className="nav-item" data-active={onInbox} style={{ textDecoration: 'none' }}>
            <Icons.inbox />
            <span>Inbox</span>
            <span className="nav-count">
              {counts.needs_review + counts.confident + counts.likely_duplicate}
            </span>
          </Link>
          <Link
            to="/search"
            className="nav-item"
            data-active={location.pathname === '/search'}
            style={{ textDecoration: 'none' }}
          >
            <Icons.search />
            <span>Search</span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 2 }}>
              <Kbd>⌘</Kbd>
              <Kbd>K</Kbd>
            </span>
          </Link>
          <Link
            to="/anomalies"
            className="nav-item"
            data-active={location.pathname === '/anomalies'}
            style={{ textDecoration: 'none' }}
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
            style={{ textDecoration: 'none' }}
          >
            <Icons.vendor />
            <span>Vendors</span>
            <span className="nav-count">{vendorCount}</span>
          </Link>
          <div className="nav-item">
            <Icons.layers />
            <span>Tax breakdowns</span>
          </div>
          <div className="nav-item">
            <Icons.history />
            <span>History</span>
          </div>

          <div className="nav-section">System</div>
          <div className="nav-item">
            <Icons.brain />
            <span>Vendor memory</span>
          </div>
          <div className="nav-item">
            <Icons.cascade />
            <span>Cascade runs</span>
          </div>
        </nav>

        <div className="sidebar-footer">
          <button
            type="button"
            onClick={() => {
              logout.mutate(undefined, {
                onSettled: () => navigate('/login', { replace: true }),
              })
            }}
            className="text-left text-[12px] tracking-[-0.005em] text-light-subtle hover:text-light underline-offset-2 hover:underline disabled:cursor-not-allowed"
            disabled={logout.isPending}
          >
            {logout.isPending ? 'Signing out…' : 'Sign out'}
          </button>
          <span className="sidebar-footer-dot" />
          <span>All systems normal · Haiku 4.5 / Sonnet 4.6</span>
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          {onInbox && (
            <>
              <div className="topbar-title">Inbox</div>
              <div className="topbar-crumbs">
                <span style={{ color: 'var(--ink-48)' }}>·</span>
                <span className="mono">{counts.needs_review} need review</span>
                <span style={{ color: 'var(--ink-48)' }}>·</span>
                <span className="mono">{counts.confident} ready to confirm</span>
              </div>
            </>
          )}
          {onVendors && (
            <>
              <div className="topbar-title">Vendors</div>
              <div className="topbar-crumbs">
                <span style={{ color: 'var(--ink-48)' }}>·</span>
                <span className="mono">
                  {vendorCount} {vendorCount === 1 ? 'vendor' : 'vendors'} tracked
                </span>
              </div>
            </>
          )}
          {onSearch && (
            <>
              <div className="topbar-title">Search</div>
              <div className="topbar-crumbs">
                <span style={{ color: 'var(--ink-48)' }}>·</span>
                <span className="mono">Natural-language query</span>
              </div>
            </>
          )}
          {onReview && (
            <>
              <div className="topbar-title">Review</div>
              <div className="topbar-crumbs">
                <span style={{ color: 'var(--ink-48)' }}>/</span>
                <span>{reviewVendor ?? 'Invoice'}</span>
              </div>
            </>
          )}

          <div
            className="topbar-search"
            onClick={() => setPaletteOpen(true)}
            role="button"
            tabIndex={0}
          >
            <Icons.search />
            <span style={{ flex: 1 }}>Search invoices or ask anything…</span>
            <Kbd>⌘</Kbd>
            <Kbd>K</Kbd>
          </div>

          {meta?.llm_provider === 'stub' && (
            <div
              title="Running with the offline StubLLMClient — no Anthropic API calls. Set SIFT_LLM_PROVIDER=anthropic to use the real cascade."
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '4px 10px',
                fontSize: 11,
                fontFamily: 'var(--font-mono)',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: 'var(--ink-80)',
                background: '#fff6db',
                border: '1px solid #e6c75a',
                cursor: 'help',
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: '#c89400',
                  display: 'inline-block',
                }}
              />
              Stub mode
            </div>
          )}
        </div>

        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <Outlet />
        </div>
      </main>

      {paletteOpen && (
        <SearchPalette
          onClose={() => setPaletteOpen(false)}
          onOpen={(id) => {
            setPaletteOpen(false)
            navigate(`/invoice/${id}`)
          }}
        />
      )}

      {helpOpen && <KeyboardHelp onClose={() => setHelpOpen(false)} />}
    </div>
  )
}

const SHORTCUTS: { keys: string[]; description: string }[] = [
  { keys: ['⌘', 'K'], description: 'Open search palette' },
  { keys: ['?'], description: 'Toggle this help' },
  { keys: ['Esc'], description: 'Close any open overlay' },
  { keys: ['↵'], description: 'Open a row / submit chip' },
  { keys: ['C'], description: 'Confirm (on review)' },
  { keys: ['D'], description: 'Dismiss (on review)' },
  { keys: ['U'], description: 'Mark unprocessable (on review)' },
]

function KeyboardHelp({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="scrim"
      onClick={onClose}
      style={{ display: 'grid', placeItems: 'center' }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--paper)',
          border: '1px solid var(--hairline)',
          minWidth: 380,
          maxWidth: 460,
          padding: 0,
        }}
      >
        <div
          style={{
            padding: '14px 18px',
            borderBottom: '1px solid var(--hairline)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: 13,
            fontWeight: 500,
          }}
        >
          <span>Keyboard shortcuts</span>
          <Kbd>esc</Kbd>
        </div>
        <div style={{ padding: '4px 0' }}>
          {SHORTCUTS.map((s, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '7px 18px',
                fontSize: 12.5,
              }}
            >
              <div style={{ display: 'flex', gap: 4, width: 90 }}>
                {s.keys.map((k, j) => (
                  <Kbd key={j}>{k}</Kbd>
                ))}
              </div>
              <span style={{ color: 'var(--ink-80)' }}>{s.description}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
