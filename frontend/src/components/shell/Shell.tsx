import { useEffect, useMemo, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'

import { Icons } from '@/components/primitives/Icons'
import { Kbd } from '@/components/primitives/Kbd'
import { SearchPalette } from '@/components/search-palette/SearchPalette'
import { useAppMetaQuery, useInboxQuery } from '@/state/invoices'

export function Shell() {
  const location = useLocation()
  const params = useParams()
  const [paletteOpen, setPaletteOpen] = useState(false)
  const { data: invoices = [] } = useInboxQuery()
  const { data: meta } = useAppMetaQuery()
  const navigate = useNavigate()

  // ⌘K opens palette · Esc closes
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen(true)
      } else if (e.key === 'Escape') {
        setPaletteOpen(false)
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

  const onInbox = location.pathname === '/inbox' || location.pathname === '/'
  const reviewVendor =
    !onInbox && params.id
      ? invoices.find((i) => i.id === params.id)?.current_extraction?.extracted_fields
          ?.vendor_name?.value
      : null

  return (
    <div className="app" data-screen-label={onInbox ? '01 Inbox' : '02 Review'}>
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="brand-mark">S</div>
          <div className="brand-name">Sift</div>
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
          <div className="nav-item" onClick={() => setPaletteOpen(true)}>
            <Icons.search />
            <span>Search</span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 2 }}>
              <Kbd>⌘</Kbd>
              <Kbd>K</Kbd>
            </span>
          </div>
          <div className="nav-item">
            <Icons.bell />
            <span>Anomalies</span>
            <span className="nav-count">{counts.likely_duplicate}</span>
          </div>

          <div className="nav-section">Library</div>
          <div className="nav-item">
            <Icons.vendor />
            <span>Vendors</span>
          </div>
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
          <span className="sidebar-footer-dot" />
          <span>All systems normal · Haiku 4.5 / Sonnet 4.6</span>
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          {onInbox ? (
            <>
              <div className="topbar-title">Inbox</div>
              <div className="topbar-crumbs">
                <span style={{ color: 'var(--ink-48)' }}>·</span>
                <span className="mono">{counts.needs_review} need review</span>
                <span style={{ color: 'var(--ink-48)' }}>·</span>
                <span className="mono">{counts.confident} ready to confirm</span>
              </div>
            </>
          ) : (
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
    </div>
  )
}
