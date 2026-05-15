import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { Btn } from '@/components/primitives/Btn'
import { FieldRow } from '@/components/primitives/FieldRow'
import { LineItemsTable } from '@/components/primitives/LineItemsTable'
import { TaxBreakdownTable } from '@/components/primitives/TaxBreakdownTable'
import { Icons } from '@/components/primitives/Icons'
import { PdfViewer } from '@/components/primitives/PdfViewer'
import { ReasonCard } from '@/components/reason-cards/ReasonCard'
import type { ReasonActionContext } from '@/components/reason-cards/types'
import { TriagePill } from '@/components/primitives/TriagePill'
import { VendorMemoryCard } from '@/components/primitives/VendorMemoryCard'
import {
  useConfirmMutation,
  useDismissDuplicateMutation,
  useInboxQuery,
  useInvoiceQuery,
  useInvoiceVendorQuery,
  useMarkUnprocessableMutation,
  useRetryMutation,
} from '@/state/invoices'
import type { ExtractedField, InvoiceOut, TriageState } from '@/types/generated/domain'
import { formatNumber } from '@/utils/format'

const FIELDS: { key: string; label: string }[] = [
  { key: 'vendor_name', label: 'Vendor' },
  { key: 'invoice_number', label: 'Invoice #' },
  { key: 'invoice_date', label: 'Date' },
  { key: 'subtotal', label: 'Subtotal' },
  { key: 'tax', label: 'Tax' },
  { key: 'total', label: 'Total' },
  { key: 'currency', label: 'Currency' },
]

function pillVariant(inv: InvoiceOut): TriageState | 'unprocessable' {
  if (inv.review_status === 'unprocessable') return 'unprocessable'
  return (inv.current_extraction?.predicted_triage_state ?? 'needs_review') as TriageState
}

function minConfidence(inv: InvoiceOut): number | null {
  const cpf = inv.current_extraction?.confidence_per_field
  if (!cpf) return null
  const vals = Object.values(cpf)
  if (vals.length === 0) return null
  return Math.min(...vals)
}

interface CascadeStep {
  tier: string
  callIndex: number
}

function cascadeTiers(inv: InvoiceOut): CascadeStep[] {
  const trace = inv.current_extraction?.cascade_trace as
    | { tiers?: Array<{ model?: string }> }
    | undefined
  const tiers = trace?.tiers ?? []
  return tiers.flatMap((t, idx) => {
    const m = (t?.model ?? '').toLowerCase()
    let tier: string
    if (m.includes('haiku')) tier = 'haiku'
    else if (m.includes('sonnet')) tier = 'sonnet'
    else if (m.includes('opus')) tier = 'opus'
    else tier = m || 'unknown'
    return tier ? [{ tier, callIndex: idx }] : []
  })
}

function reasonKey(
  r: NonNullable<InvoiceOut['current_extraction']>['predicted_triage_reasons'][number],
): string {
  if ('field' in r) return `${r.type}:${r.field}`
  if ('invoice_id' in r) return `${r.type}:${r.invoice_id}`
  if ('vendor_name' in r) return `${r.type}:${r.vendor_name}`
  if ('stage' in r) return `${r.type}:${r.stage}`
  return r.type ?? 'reason'
}

export function ReviewScreen() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: invoice, isLoading, error } = useInvoiceQuery(id)
  const { data: allInvoices = [] } = useInboxQuery()
  const { data: vendor } = useInvoiceVendorQuery(id)

  const confirm = useConfirmMutation()
  const dismissDup = useDismissDuplicateMutation()
  const markUnp = useMarkUnprocessableMutation()
  const retry = useRetryMutation()

  const byId = useMemo(
    () => Object.fromEntries(allInvoices.map((i) => [i.id, i])),
    [allInvoices]
  )

  const [activeField, setActiveField] = useState<string | null>(null)
  const [editingField, setEditingField] = useState<string | null>(null)
  const [overrides, setOverrides] = useState<Record<string, string>>({})
  const [manualMode, setManualMode] = useState(false)

  const fields = useMemo(() => {
    const base = (invoice?.current_extraction?.extracted_fields ?? {}) as Record<
      string,
      ExtractedField
    >
    const out: Record<string, ExtractedField> = { ...base }
    for (const [k, v] of Object.entries(overrides)) {
      out[k] = {
        ...(out[k] ?? { confidence: 1, source: 'manual-correction', bbox: null, page: 0 }),
        value: v,
        confidence: 1,
        source: 'manual-correction',
      } as ExtractedField
    }
    return out
  }, [invoice, overrides])

  const bboxes = useMemo(
    () =>
      Object.entries(fields).flatMap(([name, f]) =>
        Array.isArray(f?.bbox)
          ? [{ name, bbox: f.bbox as [number, number, number, number] }]
          : [],
      ),
    [fields]
  )

  if (isLoading) {
    return <div style={{ padding: 24, color: 'var(--ink-60)' }}>Loading invoice…</div>
  }
  if (error || !invoice) {
    return (
      <div style={{ padding: 24, color: 'var(--ink-60)' }}>
        <div style={{ fontSize: 16, marginBottom: 6 }}>Invoice not found.</div>
        <div style={{ fontSize: 12.5, marginBottom: 16 }}>
          It may have been removed, or the ID is wrong.
        </div>
        <Btn icon={Icons.arrowL} onClick={() => navigate('/inbox')}>
          Back to inbox
        </Btn>
      </div>
    )
  }

  const ext = invoice.current_extraction
  const reasons = ext?.predicted_triage_reasons ?? []
  const variant = pillVariant(invoice)
  const tiers = cascadeTiers(invoice)
  const isUnprocessable = invoice.review_status === 'unprocessable'

  const reasonCtx: ReasonActionContext = {
    invoiceId: invoice.id,
    reasons,
    byId,
    confirm: () => confirm.mutate(invoice.id),
    dismissDup: (againstId) => dismissDup.mutate({ id: invoice.id, againstId }),
    markUnp: () => markUnp.mutate(invoice.id),
    retry: (opts) => retry.mutate({ id: invoice.id, ...(opts ?? {}) }),
    setEditingField,
    setManualMode,
    navigate: (to) => navigate(to),
  }

  const commitField = (name: string, value: string) => {
    setOverrides((o) => ({ ...o, [name]: value }))
    setEditingField(null)
  }

  const pdfSrc = `/api/invoices/${invoice.id}/file`

  const vendorName = String(fields.vendor_name?.value ?? 'Invoice')
  const invoiceNumber = String(fields.invoice_number?.value ?? 'no invoice #')
  const currency = String(fields.currency?.value ?? '')
  const total =
    typeof fields.total?.value === 'number' ? fields.total.value : null

  return (
    <div className="review-grid">

      <div className="pdf-stage">
        {isUnprocessable ? (
          <div className="pdf-paper pdf-paper-encrypted">
            <div
              style={{
                width: 56,
                height: 56,
                background: 'var(--surface-recess)',
                display: 'grid',
                placeItems: 'center',
                color: 'var(--ink-60)',
                marginBottom: 14,
              }}
            >
              <Icons.lock />
            </div>
            <div style={{ fontWeight: 600, color: 'var(--ink)', fontSize: 15 }}>
              Couldn't read this PDF
            </div>
            <div className="muted" style={{ marginTop: 6, fontSize: 13, maxWidth: 320 }}>
              Sift couldn't read this file. You can re-upload an unlocked copy, or enter
              the fields manually on the right.
            </div>
          </div>
        ) : (
          <PdfViewer
            src={pdfSrc}
            bboxes={bboxes}
            activeField={activeField}
            onHoverBbox={setActiveField}
          />
        )}
      </div>

      <div className="review-side">

        <div
          style={{
            padding: '14px 16px',
            borderBottom: '1px solid var(--hairline)',
            background: 'var(--canvas)',
            position: 'sticky',
            top: 0,
            zIndex: 4,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
            <Btn variant="ghost" size="sm" icon={Icons.arrowL} onClick={() => navigate('/inbox')}>
              Inbox
            </Btn>
            <TriagePill variant={variant} pct={minConfidence(invoice)} />
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
              <Btn size="sm" variant="ghost" icon={Icons.refresh} title="Retry extraction" />
            </div>
          </div>

          <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: '-0.01em' }}>
            {vendorName}
          </div>
          <div
            className="muted"
            style={{ fontSize: 12, marginTop: 2, display: 'flex', gap: 10 }}
          >
            <span className="mono">{invoiceNumber}</span>
            <span>·</span>
            <span suppressHydrationWarning>
              {new Date(invoice.uploaded_at).toLocaleString()}
            </span>
            {total != null && (
              <>
                <span>·</span>
                <span className="num" style={{ color: 'var(--ink)', fontWeight: 500 }}>
                  {currency} {formatNumber(total)}
                </span>
              </>
            )}
          </div>

          <div style={{ display: 'flex', gap: 6, marginTop: 12 }}>
            <Btn variant="primary" icon={Icons.check} onClick={() => confirm.mutate(invoice.id)}>
              Confirm
              <span className="ml-1 bg-white/[0.12] px-1 font-mono text-[12px]">
                C
              </span>
            </Btn>
            <Btn icon={Icons.x} onClick={() => markUnp.mutate(invoice.id)}>Dismiss</Btn>
            <Btn variant="ghost" icon={Icons.cascade} onClick={() => retry.mutate({ id: invoice.id, forceTier: 'claude-opus-4-7' })}>
              Force Opus
            </Btn>
          </div>
        </div>

        {}
        {reasons.length > 0 && (
          <div className="review-side-section">
            <div className="review-side-section-title">
              Why this needs attention
              <span className="mono" style={{ marginLeft: 6, color: 'var(--ink-48)' }}>
                {reasons.length} {reasons.length === 1 ? 'reason' : 'reasons'}
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {reasons.map((r) => (
                <ReasonCard key={reasonKey(r)} reason={r} ctx={reasonCtx} />
              ))}
            </div>
          </div>
        )}

        {}
        <div className="review-side-section">
          <div
            className="review-side-section-title"
            style={{ display: 'flex', alignItems: 'center' }}
          >
            <span>Extracted fields</span>
            {manualMode && (
              <span className="source" data-kind="manual" style={{ marginLeft: 8 }}>
                <Icons.pen />
                <span>Manual entry mode</span>
              </span>
            )}
            <span className="ml-auto font-mono text-[12px] text-ink-48">
              cascade: {tiers.length ? tiers.map((t) => t.tier).join(' → ') : '–'}
            </span>
          </div>

          <div className="card" style={{ marginBottom: 12 }}>
            {FIELDS.map(({ key, label }) => (
              <FieldRow
                key={key}
                name={key}
                label={label}
                field={fields[key] ?? null}
                isActive={activeField === key}
                onActivate={setActiveField}
                isEditing={editingField === key}
                onEdit={
                  manualMode || invoice.review_status === 'pending' ? setEditingField : null
                }
                onCommit={commitField}
              />
            ))}
          </div>
        </div>

        <div className="review-side-section">
          <div className="review-side-section-title">Line items</div>
          <LineItemsTable items={invoice.current_extraction?.line_items ?? []} />
        </div>

        <div className="review-side-section">
          <div className="review-side-section-title">Tax breakdown</div>
          <TaxBreakdownTable rows={invoice.current_extraction?.tax_breakdown ?? []} />
        </div>

        {}
        {tiers.length > 0 && (
          <div className="review-side-section">
            <div className="review-side-section-title">Cascade trace</div>
            <CascadeTrace tiers={tiers} />
          </div>
        )}

        {}
        {vendor?.memory && (
          <div className="review-side-section">
            <div className="review-side-section-title">Vendor memory</div>
            <VendorMemoryCard memory={vendor.memory} vendorName={vendor.name} />
          </div>
        )}

        <div style={{ height: 24 }} />
      </div>
    </div>
  )
}

const TIER_META: Record<string, { label: string; color: string; bg: string; cost: string }> = {
  haiku: { label: 'Haiku 4.5', color: 'var(--ink-60)', bg: 'var(--surface-recess)', cost: '$0.001' },
  sonnet: { label: 'Sonnet 4.6', color: '#1d6280', bg: '#e7f1f6', cost: '$0.012' },
  opus: { label: 'Opus 4.7', color: '#6b3b8c', bg: '#f3e9f9', cost: '$0.060' },
}

function CascadeTrace({ tiers }: { tiers: CascadeStep[] }) {
  return (
    <div className="card p-3">
      <div className="flex flex-wrap items-center gap-1">
        {tiers.map((step, i) => {
          const m = TIER_META[step.tier] ?? {
            label: step.tier,
            color: 'var(--ink-60)',
            bg: 'var(--surface-recess)',
            cost: '',
          }
          return (
            <span
              key={`${step.tier}-${step.callIndex}`}
              className="inline-flex items-center"
            >
              <CascadeBadge label={m.label} cost={m.cost} bg={m.bg} color={m.color} />
              {i < tiers.length - 1 && (
                <span className="mx-1 text-ink-48">→</span>
              )}
            </span>
          )
        })}
      </div>
      <div className="muted mt-2 text-xs leading-[1.5]">
        {tiers.length === 1
          ? 'First tier returned high composite confidence; no escalation needed.'
          : tiers.length === 2
            ? "Haiku's output triggered the cascade (math fails or low confidence). Sonnet's values shown above."
            : 'Sonnet disagreed with Haiku on disputed fields. Opus broke the tie; agreement scores merged into composite.'}
      </div>
    </div>
  )
}

function CascadeBadge({
  label,
  cost,
  bg,
  color,
}: {
  label: string
  cost: string
  bg: string
  color: string
}) {
  return (
    <span
      className="inline-flex items-center gap-1.5 border border-hairline px-2 py-1 font-mono text-xs"
      style={{ background: bg, color }}
    >
      <span className="size-1.5 rounded-full" style={{ background: color }} />
      <span>{label}</span>
      {cost && <span className="opacity-60">{cost}</span>}
    </span>
  )
}
