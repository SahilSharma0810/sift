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
    const sorted = group.toSorted((a, b) =>
      (getDate(a) ?? '').localeCompare(getDate(b) ?? '')
    )
    const totals = sorted.flatMap((inv) => {
      const t = getTotal(inv)
      return t != null && t > 0 ? [t] : []
    })
    const totalSpent = totals.reduce((s, n) => s + n, 0)
    const confidences = group.flatMap((inv) => {
      const c = minConfidence(inv)
      return c != null ? [c] : []
    })
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
          value={totals.avgConfidence > 0 ? `${Math.round(totals.avgConfidence * 100)}%` : '–'}
          suffix="composite"
          last
        />
      </StatStrip>

      <div className="inbox-toolbar">
        <div className="text-xs text-ink-60">
          {isLoading
            ? 'Loading vendors…'
            : `${vendors.length} vendor${vendors.length === 1 ? '' : 's'} · grouped from ${invoices.length} invoice${invoices.length === 1 ? '' : 's'}`}
        </div>
        <div className="ml-auto flex gap-2">
          <Btn size="sm" variant="ghost" icon={Icons.filter}>
            Filter
          </Btn>
          <Btn size="sm" variant="ghost" icon={Icons.download}>
            Export
          </Btn>
        </div>
      </div>

      <div className="border border-hairline bg-surface">
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
                  No vendors yet. Upload an invoice in the Inbox to start building the directory.
                </td>
              </tr>
            )}
            {sorted.map((v) => (
              <tr
                key={v.name}
                onClick={() => setActive(active === v.name ? null : v.name)}
                data-selected={active === v.name ? 'true' : 'false'}
              >
                <td className="font-medium">
                  {v.name}
                  {v.anomalies > 0 && (
                    <span className="mono ml-2 border border-[#ebd0a8] bg-triage-needs-review-tint px-1.5 py-px text-[12px] text-triage-needs-review">
                      {v.anomalies} {v.anomalies === 1 ? 'anomaly' : 'anomalies'}
                    </span>
                  )}
                </td>
                <td className="col-right num">{v.invoices}</td>
                <td className="col-right num">
                  {v.totalSpent > 0 ? formatMoneyFull(v.totalSpent) : '–'}
                </td>
                <td className="col-right num muted">
                  {v.avgInvoice > 0 ? formatMoneyFull(v.avgInvoice) : '–'}
                </td>
                <td className="num muted">{v.lastSeen ?? '–'}</td>
                <td>
                  <TrendBadge trend={v.trend} />
                </td>
                <td className="col-right num muted">
                  {v.confidence > 0 ? `${Math.round(v.confidence * 100)}%` : '–'}
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
    <div className="mb-5">
      <div className="mb-2 text-[12px] font-medium uppercase tracking-[0.10em] text-ink-48">
        {eyebrow}
      </div>
      <div className="mb-1 text-[21px] font-semibold tracking-[-0.012em] text-ink">
        {title}
      </div>
      <div className="max-w-[70ch] text-sm leading-[1.5] text-ink-60">{sub}</div>
    </div>
  )
}

function StatStrip({ children }: { children: ReactNode }) {
  const count = Children.count(children)
  return (
    <div
      className="mb-[18px] grid border border-hairline bg-surface"
      style={{ gridTemplateColumns: `repeat(${count}, 1fr)` }}
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
    <div className={`px-5 py-4 ${last ? '' : 'border-r border-hairline'}`}>
      <div className="text-[12px] font-medium uppercase tracking-[0.06em] text-ink-48">
        {label}
      </div>
      <div className="mt-1.5 flex items-baseline gap-2">
        <span className="num text-[22px] font-semibold tracking-[-0.012em] text-ink">
          {value}
        </span>
        {suffix && <span className="font-mono text-xs text-ink-60">{suffix}</span>}
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
      className={`cursor-pointer select-none ${right ? 'col-right' : ''}`}
    >
      <span
        className={`inline-flex items-center gap-1 ${isActive ? 'text-ink' : ''}`}
      >
        {children}
        {isActive && <span className="font-mono">↓</span>}
      </span>
    </th>
  )
}

const TREND_META: Record<Trend, { label: string; color: string; glyph: string }> = {
  rising: { label: 'Rising', color: 'var(--triage-needs-review)', glyph: '↗' },
  declining: { label: 'Declining', color: 'var(--ink-60)', glyph: '↘' },
  stable: { label: 'Stable', color: 'var(--ink-60)', glyph: '→' },
  new: { label: 'New', color: 'var(--primary)', glyph: '★' },
}

function TrendBadge({ trend }: { trend: Trend }) {
  const m = TREND_META[trend]
  return (
    <span
      className="inline-flex items-center gap-1 font-mono text-xs"
      style={{ color: m.color }}
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
    <div className="fixed bottom-0 right-0 top-[60px] z-30 w-[440px] overflow-y-auto border-l border-hairline bg-surface shadow-[0_8px_32px_rgba(0,0,0,0.12)]">
      <div className="sticky top-0 z-[1] flex items-center gap-2.5 border-b border-hairline bg-surface px-[18px] py-4">
        <div>
          <div className="text-[12px] font-medium uppercase tracking-[0.06em] text-ink-48">
            Vendor
          </div>
          <div className="text-[17px] font-semibold tracking-[-0.005em]">
            {vendor.name}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="ml-auto cursor-pointer border-0 bg-transparent p-1.5 text-ink-60"
          title="Close"
          aria-label="Close vendor details"
        >
          <Icons.x />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2.5 px-[18px] py-4">
        <KV label="Invoices" value={String(vendor.invoices)} />
        <KV
          label="Total spent"
          value={vendor.totalSpent > 0 ? formatMoneyFull(vendor.totalSpent) : '–'}
        />
        <KV
          label="Avg invoice"
          value={vendor.avgInvoice > 0 ? formatMoneyFull(vendor.avgInvoice) : '–'}
        />
        <KV label="Last seen" value={vendor.lastSeen ?? '–'} />
        <KV
          label="Confidence"
          value={vendor.confidence > 0 ? `${Math.round(vendor.confidence * 100)}%` : '–'}
        />
        <KV
          label="Active anomalies"
          value={String(vendor.anomalies)}
          tone={vendor.anomalies > 0 ? 'warn' : null}
        />
      </div>

      <div className="mt-1 px-[18px] pb-1.5">
        <div className="mb-2 text-[12px] font-medium uppercase tracking-[0.06em] text-ink-48">
          Invoices · {invoices.length}
        </div>
      </div>

      <div className="flex flex-col gap-1.5 px-[18px] pb-[18px]">
        {invoices.length === 0 && (
          <div className="muted text-sm italic">
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
              className="flex items-center gap-2.5 border border-hairline bg-surface-recess px-3 py-2.5 text-inherit no-underline"
            >
              <div className="min-w-0 flex-1">
                <div className="mono text-xs text-ink">
                  {String(fields.invoice_number?.value ?? '–')}
                </div>
                <div className="mt-0.5 text-xs text-ink-60">
                  {String(fields.invoice_date?.value ?? '–')}
                </div>
              </div>
              <div className="num text-[13px]">
                {total != null ? formatNumber(Number(total)) : '–'}
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
  return (
    <div className="border border-hairline bg-surface-recess px-3 py-2.5">
      <div className="text-[12px] font-medium uppercase tracking-[0.06em] text-ink-48">
        {label}
      </div>
      <div
        className={`num mt-0.5 text-[15px] font-medium ${
          tone === 'warn' ? 'text-triage-needs-review' : 'text-ink'
        }`}
      >
        {value}
      </div>
    </div>
  )
}
