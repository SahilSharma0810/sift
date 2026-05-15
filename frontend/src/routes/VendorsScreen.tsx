import { Children, useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { Btn } from '@/components/primitives/Btn'
import { Icons } from '@/components/primitives/Icons'
import { useInboxQuery } from '@/state/invoices'
import type { InvoiceOut } from '@/types/generated/domain'
import { formatNumber } from '@/utils/format'

type SortKey = 'name' | 'invoices' | 'totalSpent' | 'avgInvoice' | 'lastSeen' | 'confidence'
type Trend = 'rising' | 'declining' | 'stable' | 'new'

interface VendorAggregate {
  name: string
  invoices: number
  totalSpent: number
  avgInvoice: number
  lastSeen: string | null
  anomalies: number
  confidence: number
  trend: Trend
  invoiceIds: string[]
}

function getVendorName(inv: InvoiceOut): string | null {
  const v = inv.current_extraction?.extracted_fields?.vendor_name?.value
  return v == null ? null : String(v).trim() || null
}

function getTotal(inv: InvoiceOut): number | null {
  const t = inv.current_extraction?.extracted_fields?.total?.value
  if (t == null) return null
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}

function getDate(inv: InvoiceOut): string | null {
  const d = inv.current_extraction?.extracted_fields?.invoice_date?.value
  return d == null ? null : String(d)
}

function minConfidence(inv: InvoiceOut): number | null {
  const cpf = inv.current_extraction?.confidence_per_field
  if (!cpf) return null
  const vals = Object.values(cpf)
  return vals.length === 0 ? null : Math.min(...vals)
}

function isAnomaly(inv: InvoiceOut): boolean {
  if (inv.review_status !== 'pending') return false
  const triage = inv.current_extraction?.predicted_triage_state
  return triage === 'needs_review' || triage === 'likely_duplicate'
}

function deriveTrend(totals: number[]): Trend {
  if (totals.length <= 1) return 'new'
  const half = Math.max(1, Math.floor(totals.length / 2))
  const olderAvg = totals.slice(0, half).reduce((s, n) => s + n, 0) / half
  const recent = totals.slice(half)
  const recentAvg = recent.reduce((s, n) => s + n, 0) / recent.length
  if (olderAvg === 0) return 'stable'
  const delta = (recentAvg - olderAvg) / olderAvg
  if (delta > 0.15) return 'rising'
  if (delta < -0.15) return 'declining'
  return 'stable'
}

function aggregateVendors(invoices: InvoiceOut[]): VendorAggregate[] {
  const groups = new Map<string, InvoiceOut[]>()
  for (const inv of invoices) {
    const name = getVendorName(inv)
    if (!name) continue
    const arr = groups.get(name) ?? []
    arr.push(inv)
    groups.set(name, arr)
  }

  const out: VendorAggregate[] = []
  for (const [name, group] of groups) {
    const sorted = [...group].sort((a, b) =>
      (getDate(a) ?? '').localeCompare(getDate(b) ?? '')
    )
    const totals = sorted
      .map(getTotal)
      .filter((n): n is number => n != null && n > 0)
    const totalSpent = totals.reduce((s, n) => s + n, 0)
    const confidences = group
      .map(minConfidence)
      .filter((n): n is number => n != null)
    out.push({
      name,
      invoices: group.length,
      totalSpent,
      avgInvoice: totals.length === 0 ? 0 : totalSpent / totals.length,
      lastSeen: getDate(sorted[sorted.length - 1]),
      anomalies: group.filter(isAnomaly).length,
      confidence:
        confidences.length === 0
          ? 0
          : confidences.reduce((s, n) => s + n, 0) / confidences.length,
      trend: deriveTrend(totals),
      invoiceIds: group.map((g) => g.id),
    })
  }
  return out
}

function formatMoney(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n === 0) return '—'
  if (n >= 1000) return `$${(n / 1000).toFixed(1)}K`
  return `$${n.toFixed(2)}`
}

function formatMoneyFull(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—'
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

export function VendorsScreen() {
  const { data: invoices = [], isLoading } = useInboxQuery()
  const [sort, setSort] = useState<SortKey>('totalSpent')
  const [active, setActive] = useState<string | null>(null)

  const vendors = useMemo(() => aggregateVendors(invoices), [invoices])

  const sorted = useMemo(() => {
    const copy = [...vendors]
    copy.sort((a, b) => {
      if (sort === 'name') return a.name.localeCompare(b.name)
      if (sort === 'lastSeen') return (b.lastSeen ?? '').localeCompare(a.lastSeen ?? '')
      return (b[sort] ?? 0) - (a[sort] ?? 0)
    })
    return copy
  }, [sort, vendors])

  const totals = useMemo(() => {
    if (vendors.length === 0) {
      return { spent: 0, invoices: 0, anomalies: 0, avgConfidence: 0 }
    }
    return {
      spent: vendors.reduce((s, v) => s + v.totalSpent, 0),
      invoices: vendors.reduce((s, v) => s + v.invoices, 0),
      anomalies: vendors.reduce((s, v) => s + v.anomalies, 0),
      avgConfidence:
        vendors.reduce((s, v) => s + v.confidence, 0) / vendors.length,
    }
  }, [vendors])

  const selected = active ? vendors.find((v) => v.name === active) ?? null : null
  const selectedInvoices = useMemo(() => {
    if (!selected) return []
    const ids = new Set(selected.invoiceIds)
    return invoices
      .filter((i) => ids.has(i.id))
      .sort((a, b) => (getDate(b) ?? '').localeCompare(getDate(a) ?? ''))
  }, [invoices, selected])

  return (
    <div className="inbox-content">
      <ScreenHeader
        eyebrow="Vendor directory"
        title={`${vendors.length} ${vendors.length === 1 ? 'vendor' : 'vendors'} in your portfolio`}
        sub="Per-vendor aggregate stats drive composite confidence, anomaly Z-scores, and the cold-start hedge applied to brand-new vendors. Click any row to see invoices and confidence."
      />

      <StatStrip>
        <StatTile label="Total spent" value={formatMoney(totals.spent)} suffix="all-time" />
        <StatTile label="Invoices" value={String(totals.invoices)} suffix="across vendors" />
        <StatTile
          label="Anomalies"
          value={String(totals.anomalies)}
          suffix={totals.anomalies === 1 ? 'pending review' : 'pending review'}
        />
        <StatTile
          label="Avg confidence"
          value={totals.avgConfidence > 0 ? `${Math.round(totals.avgConfidence * 100)}%` : '—'}
          suffix="composite"
          last
        />
      </StatStrip>

      <div className="inbox-toolbar">
        <div style={{ fontSize: 12, color: 'var(--ink-60)' }}>
          {isLoading
            ? 'Loading vendors…'
            : `${vendors.length} vendor${vendors.length === 1 ? '' : 's'} · grouped from ${invoices.length} invoice${invoices.length === 1 ? '' : 's'}`}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <Btn size="sm" variant="ghost" icon={Icons.filter}>
            Filter
          </Btn>
          <Btn size="sm" variant="ghost" icon={Icons.download}>
            Export
          </Btn>
        </div>
      </div>

      <div style={{ border: '1px solid var(--hairline)', background: 'var(--surface)' }}>
        <table className="table">
          <thead>
            <tr>
              <SortHead k="name" sort={sort} set={setSort}>Vendor</SortHead>
              <SortHead k="invoices" sort={sort} set={setSort} right>Invoices</SortHead>
              <SortHead k="totalSpent" sort={sort} set={setSort} right>Total spent</SortHead>
              <SortHead k="avgInvoice" sort={sort} set={setSort} right>Avg</SortHead>
              <SortHead k="lastSeen" sort={sort} set={setSort}>Last seen</SortHead>
              <th>Trend</th>
              <SortHead k="confidence" sort={sort} set={setSort} right>Confidence</SortHead>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={7} style={{ padding: 24, textAlign: 'center', color: 'var(--ink-60)' }}>
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && sorted.length === 0 && (
              <tr>
                <td colSpan={7} style={{ padding: 24, textAlign: 'center', color: 'var(--ink-60)' }}>
                  No vendors yet — upload an invoice in the Inbox to start building the directory.
                </td>
              </tr>
            )}
            {sorted.map((v) => (
              <tr
                key={v.name}
                onClick={() => setActive(active === v.name ? null : v.name)}
                data-selected={active === v.name ? 'true' : 'false'}
              >
                <td style={{ fontWeight: 500 }}>
                  {v.name}
                  {v.anomalies > 0 && (
                    <span
                      className="mono"
                      style={{
                        marginLeft: 8,
                        fontSize: 10.5,
                        color: 'var(--triage-needs-review)',
                        padding: '1px 6px',
                        border: '1px solid #ebd0a8',
                        background: 'var(--triage-needs-review-bg)',
                      }}
                    >
                      {v.anomalies} {v.anomalies === 1 ? 'anomaly' : 'anomalies'}
                    </span>
                  )}
                </td>
                <td className="col-right num">{v.invoices}</td>
                <td className="col-right num">
                  {v.totalSpent > 0 ? formatMoneyFull(v.totalSpent) : '—'}
                </td>
                <td className="col-right num muted">
                  {v.avgInvoice > 0 ? formatMoneyFull(v.avgInvoice) : '—'}
                </td>
                <td className="num muted">{v.lastSeen ?? '—'}</td>
                <td><TrendBadge trend={v.trend} /></td>
                <td className="col-right num muted">
                  {v.confidence > 0 ? `${Math.round(v.confidence * 100)}%` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && (
        <VendorDetailDrawer
          vendor={selected}
          invoices={selectedInvoices}
          onClose={() => setActive(null)}
        />
      )}
    </div>
  )
}

function ScreenHeader({
  eyebrow,
  title,
  sub,
}: {
  eyebrow: string
  title: string
  sub: string
}) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div
        style={{
          fontSize: 11,
          letterSpacing: '0.10em',
          textTransform: 'uppercase',
          color: 'var(--ink-48)',
          fontWeight: 500,
          marginBottom: 8,
        }}
      >
        {eyebrow}
      </div>
      <div
        style={{
          fontSize: 21,
          fontWeight: 600,
          letterSpacing: '-0.012em',
          color: 'var(--ink)',
          marginBottom: 4,
        }}
      >
        {title}
      </div>
      <div style={{ fontSize: 14, color: 'var(--ink-60)', lineHeight: 1.5, maxWidth: '70ch' }}>
        {sub}
      </div>
    </div>
  )
}

function StatStrip({ children }: { children: ReactNode }) {
  const count = Children.count(children)
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${count}, 1fr)`,
        background: 'var(--surface)',
        border: '1px solid var(--hairline)',
        marginBottom: 18,
      }}
    >
      {children}
    </div>
  )
}

function StatTile({
  label,
  value,
  suffix,
  last,
}: {
  label: string
  value: string
  suffix?: string
  last?: boolean
}) {
  return (
    <div
      style={{
        padding: '16px 20px',
        borderRight: last ? 0 : '1px solid var(--hairline)',
      }}
    >
      <div
        style={{
          fontSize: 10.5,
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          color: 'var(--ink-48)',
          fontWeight: 500,
        }}
      >
        {label}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 6 }}>
        <span
          className="num"
          style={{
            fontSize: 22,
            fontWeight: 600,
            color: 'var(--ink)',
            letterSpacing: '-0.012em',
          }}
        >
          {value}
        </span>
        {suffix && (
          <span style={{ fontSize: 11.5, color: 'var(--ink-60)', fontFamily: 'var(--font-mono)' }}>
            {suffix}
          </span>
        )}
      </div>
    </div>
  )
}

function SortHead({
  k,
  sort,
  set,
  right,
  children,
}: {
  k: SortKey
  sort: SortKey
  set: (k: SortKey) => void
  right?: boolean
  children: ReactNode
}) {
  const isActive = sort === k
  return (
    <th
      onClick={() => set(k)}
      className={right ? 'col-right' : ''}
      style={{ cursor: 'pointer', userSelect: 'none' }}
    >
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
          color: isActive ? 'var(--ink)' : undefined,
        }}
      >
        {children}
        {isActive && <span style={{ fontFamily: 'var(--font-mono)' }}>↓</span>}
      </span>
    </th>
  )
}

function TrendBadge({ trend }: { trend: Trend }) {
  const META: Record<Trend, { label: string; color: string; glyph: string }> = {
    rising: { label: 'Rising', color: 'var(--triage-needs-review)', glyph: '↗' },
    declining: { label: 'Declining', color: 'var(--ink-60)', glyph: '↘' },
    stable: { label: 'Stable', color: 'var(--ink-60)', glyph: '→' },
    new: { label: 'New', color: 'var(--primary)', glyph: '★' },
  }
  const m = META[trend]
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        fontSize: 11.5,
        color: m.color,
        fontFamily: 'var(--font-mono)',
      }}
    >
      <span>{m.glyph}</span>
      <span>{m.label}</span>
    </span>
  )
}

function VendorDetailDrawer({
  vendor,
  invoices,
  onClose,
}: {
  vendor: VendorAggregate
  invoices: InvoiceOut[]
  onClose: () => void
}) {
  return (
    <div
      style={{
        position: 'fixed',
        right: 0,
        top: 60,
        bottom: 0,
        width: 440,
        background: 'var(--surface)',
        borderLeft: '1px solid var(--hairline)',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.12)',
        overflowY: 'auto',
        zIndex: 30,
      }}
    >
      <div
        style={{
          padding: '16px 18px',
          borderBottom: '1px solid var(--hairline)',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          position: 'sticky',
          top: 0,
          background: 'var(--surface)',
          zIndex: 1,
        }}
      >
        <div>
          <div
            style={{
              fontSize: 10.5,
              color: 'var(--ink-48)',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              fontWeight: 500,
            }}
          >
            Vendor
          </div>
          <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: '-0.005em' }}>
            {vendor.name}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          style={{
            marginLeft: 'auto',
            padding: 6,
            color: 'var(--ink-60)',
            background: 'transparent',
            border: 0,
            cursor: 'pointer',
          }}
          title="Close"
          aria-label="Close vendor details"
        >
          <Icons.x />
        </button>
      </div>

      <div
        style={{
          padding: '16px 18px',
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 10,
        }}
      >
        <KV label="Invoices" value={String(vendor.invoices)} />
        <KV
          label="Total spent"
          value={vendor.totalSpent > 0 ? formatMoneyFull(vendor.totalSpent) : '—'}
        />
        <KV
          label="Avg invoice"
          value={vendor.avgInvoice > 0 ? formatMoneyFull(vendor.avgInvoice) : '—'}
        />
        <KV label="Last seen" value={vendor.lastSeen ?? '—'} />
        <KV
          label="Confidence"
          value={vendor.confidence > 0 ? `${Math.round(vendor.confidence * 100)}%` : '—'}
        />
        <KV
          label="Active anomalies"
          value={String(vendor.anomalies)}
          tone={vendor.anomalies > 0 ? 'warn' : null}
        />
      </div>

      <div style={{ padding: '0 18px 6px', marginTop: 4 }}>
        <div
          style={{
            fontSize: 10.5,
            color: 'var(--ink-48)',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            fontWeight: 500,
            marginBottom: 8,
          }}
        >
          Invoices · {invoices.length}
        </div>
      </div>

      <div style={{ padding: '0 18px 18px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {invoices.length === 0 && (
          <div className="muted" style={{ fontSize: 13, fontStyle: 'italic' }}>
            No invoices for this vendor yet.
          </div>
        )}
        {invoices.map((inv) => {
          const fields = inv.current_extraction?.extracted_fields ?? {}
          const total = fields.total?.value
          return (
            <Link
              key={inv.id}
              to={`/invoice/${inv.id}`}
              style={{
                textDecoration: 'none',
                color: 'inherit',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '10px 12px',
                background: 'var(--surface-recess)',
                border: '1px solid var(--hairline)',
              }}
            >
              <div style={{ minWidth: 0, flex: 1 }}>
                <div className="mono" style={{ fontSize: 12, color: 'var(--ink)' }}>
                  {String(fields.invoice_number?.value ?? '—')}
                </div>
                <div style={{ fontSize: 11, color: 'var(--ink-60)', marginTop: 2 }}>
                  {String(fields.invoice_date?.value ?? '—')}
                </div>
              </div>
              <div className="num" style={{ fontSize: 13 }}>
                {total != null ? formatNumber(Number(total)) : '—'}
              </div>
            </Link>
          )
        })}
      </div>
    </div>
  )
}

function KV({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'warn' | null
}) {
  const color = tone === 'warn' ? 'var(--triage-needs-review)' : 'var(--ink)'
  return (
    <div
      style={{
        padding: '10px 12px',
        background: 'var(--surface-recess)',
        border: '1px solid var(--hairline)',
      }}
    >
      <div
        style={{
          fontSize: 10.5,
          color: 'var(--ink-48)',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          fontWeight: 500,
        }}
      >
        {label}
      </div>
      <div className="num" style={{ fontSize: 15, fontWeight: 500, color, marginTop: 2 }}>
        {value}
      </div>
    </div>
  )
}
