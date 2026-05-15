import { useMemo } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { Btn } from '@/components/primitives/Btn'
import { Icons } from '@/components/primitives/Icons'
import { PdfViewer } from '@/components/primitives/PdfViewer'
import { TriagePill } from '@/components/primitives/TriagePill'
import {
  useDismissDuplicateMutation,
  useInvoiceQuery,
  useMarkUnprocessableMutation,
} from '@/state/invoices'
import type { InvoiceOut, TriageState } from '@/types/generated/domain'

const FIELDS = [
  { key: 'vendor_name', label: 'Vendor' },
  { key: 'invoice_number', label: 'Invoice #' },
  { key: 'invoice_date', label: 'Date' },
  { key: 'subtotal', label: 'Subtotal' },
  { key: 'tax', label: 'Tax' },
  { key: 'total', label: 'Total' },
  { key: 'currency', label: 'Currency' },
]

function fieldValuesMatch(key: string, a: unknown, b: unknown): boolean {
  if (a == null && b == null) return true
  if (a == null || b == null) return false
  if (key === 'subtotal' || key === 'tax' || key === 'total') {
    const na = Number(a)
    const nb = Number(b)
    return Number.isFinite(na) && Number.isFinite(nb) && Math.abs(na - nb) <= 0.01
  }
  return String(a).trim() === String(b).trim()
}

function pillVariant(inv: InvoiceOut): TriageState | 'unprocessable' {
  if (inv.review_status === 'unprocessable') return 'unprocessable'
  return (inv.current_extraction?.predicted_triage_state ?? 'needs_review') as TriageState
}

export function DuplicateReviewScreen() {
  const { id } = useParams<{ id: string }>()
  const [search] = useSearchParams()
  const againstId = search.get('against') ?? undefined
  const navigate = useNavigate()

  const { data: current } = useInvoiceQuery(id)
  const { data: original } = useInvoiceQuery(againstId)
  const dismissDup = useDismissDuplicateMutation()
  const markUnp = useMarkUnprocessableMutation()

  const diff = useMemo(() => {
    if (!current || !original) return []
    const a = original.current_extraction?.extracted_fields ?? {}
    const b = current.current_extraction?.extracted_fields ?? {}
    return FIELDS.map(({ key, label }) => ({
      key,
      label,
      origValue: a[key]?.value ?? null,
      currValue: b[key]?.value ?? null,
      matches: fieldValuesMatch(key, a[key]?.value, b[key]?.value),
    }))
  }, [current, original])

  if (!current || !original) {
    return <div style={{ padding: 24, color: 'var(--ink-60)' }}>Loading…</div>
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr) minmax(320px, 380px)',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      <div className="pdf-stage">
        <div
          className="mb-2 text-center text-[12px] uppercase tracking-[0.08em] text-ink-48"
          suppressHydrationWarning
        >
          Original · uploaded {new Date(original.uploaded_at).toLocaleString()}
        </div>
        <PdfViewer src={`/api/invoices/${original.id}/file`} />
      </div>

      <div className="pdf-stage" style={{ borderLeft: '1px solid var(--hairline)' }}>
        <div
          className="mb-2 text-center text-[12px] uppercase tracking-[0.08em] text-ink-48"
          suppressHydrationWarning
        >
          New · uploaded {new Date(current.uploaded_at).toLocaleString()}
        </div>
        <PdfViewer src={`/api/invoices/${current.id}/file`} />
      </div>

      <div className="review-side">
        <div
          style={{
            padding: '14px 16px',
            borderBottom: '1px solid var(--hairline)',
          }}
        >
          <Btn variant="ghost" size="sm" icon={Icons.arrowL} onClick={() => navigate('/inbox')}>
            Inbox
          </Btn>
          <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center' }}>
            <TriagePill variant={pillVariant(current)} />
            <span style={{ fontSize: 12, color: 'var(--ink-60)' }}>vs</span>
            <TriagePill variant={pillVariant(original)} />
          </div>
        </div>

        <div className="review-side-section">
          <div className="review-side-section-title">Field diff</div>
          <div className="card">
            {diff.map(({ key, label, origValue, currValue, matches }) => (
              <div
                key={key}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '90px 1fr 1fr',
                  alignItems: 'center',
                  padding: '8px 12px',
                  borderBottom: '1px solid var(--hairline-soft)',
                  background: matches ? 'transparent' : '#fdf1ec',
                }}
              >
                <div style={{ fontSize: 12, color: 'var(--ink-60)' }}>{label}</div>
                <div className="num" style={{ fontSize: 13 }}>
                  {origValue == null ? (
                    <span className="subtle">–</span>
                  ) : (
                    String(origValue)
                  )}
                </div>
                <div
                  className="num"
                  style={{ fontSize: 13, fontWeight: matches ? 400 : 600 }}
                >
                  {currValue == null ? (
                    <span className="subtle">–</span>
                  ) : (
                    String(currValue)
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="review-side-section">
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Btn
              variant="primary"
              icon={Icons.x}
              onClick={() => markUnp.mutate(current.id)}
            >
              Confirm duplicate & dismiss
            </Btn>
            <Btn
              icon={Icons.check}
              onClick={() => {
                if (!againstId) return
                dismissDup.mutate({ id: current.id, againstId })
                navigate(`/invoice/${current.id}`)
              }}
            >
              Not a duplicate
            </Btn>
          </div>
        </div>
      </div>
    </div>
  )
}
