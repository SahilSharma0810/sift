/**
 * SearchPalette — opens on ⌘K. NL → typed chips → results.
 * Chips ARE the state (ADR-0004). Untranslated intent surfaces above results.
 *
 * Day-1: client-side translation map mirrors the design; client-side filter
 * against useInboxQuery data. Day-4 will replace `translate()` with a real
 * /api/nl-query call and the chip filter with a server-side StructuredQuery.
 */
import { useEffect, useMemo, useRef, useState } from 'react'

import { Chip } from '@/components/primitives/Chip'
import { Icons } from '@/components/primitives/Icons'
import { Kbd } from '@/components/primitives/Kbd'
import { TriagePill } from '@/components/primitives/TriagePill'
import { useInboxQuery } from '@/state/invoices'
import type { InvoiceOut, TriageState } from '@/types/generated/domain'
import { formatNumber } from '@/utils/format'

type ChipValue = string | number | boolean | Array<string | number>
type FilterChip = { field: string; op: string; value: ChipValue }
type Translation = { chips: FilterChip[]; untranslated: string | null }

const TRANSLATIONS: Array<{
  test: (s: string) => boolean
  chips: FilterChip[]
  untranslated: string | null
}> = [
  {
    test: (s) =>
      /vega/i.test(s) && /3\s*month/i.test(s) && /(\$|usd)?\s*5\s*k/i.test(s),
    chips: [
      { field: 'vendor_name', op: 'eq', value: 'Vega Logistics' },
      { field: 'invoice_date', op: 'between', value: ['2026-02-13', '2026-05-13'] },
      { field: 'total', op: 'gte', value: 5000 },
    ],
    untranslated: null,
  },
  {
    test: (s) => /duplicate/i.test(s) && /(this month|may)/i.test(s),
    chips: [
      { field: 'is_duplicate', op: 'eq', value: 'true' },
      { field: 'invoice_date', op: 'between', value: ['2026-05-01', '2026-05-31'] },
    ],
    untranslated: null,
  },
  {
    test: (s) => /needs review/i.test(s) && /acme/i.test(s),
    chips: [
      { field: 'triage_state', op: 'eq', value: 'needs_review' },
      { field: 'vendor_name', op: 'contains', value: 'Acme' },
    ],
    untranslated: null,
  },
  {
    test: (s) => /high(est)?\s*spend|biggest invoices?|largest/i.test(s),
    chips: [{ field: 'total', op: 'gte', value: 10000 }],
    untranslated: 'sort by total descending — top N',
  },
  {
    test: (s) => /math.*(fail|wrong|off)/i.test(s),
    chips: [{ field: 'triage_state', op: 'eq', value: 'needs_review' }],
    untranslated: 'filter to math-reconciliation reason only',
  },
]

const SUGGESTED = [
  'Vega invoices last 3 months over $5k',
  'duplicates this month',
  'needs review from Acme',
  'biggest invoices this quarter',
  'show extractions where math failed',
]

function translate(q: string): Translation {
  for (const t of TRANSLATIONS) {
    if (t.test(q)) return { chips: t.chips, untranslated: t.untranslated }
  }
  return { chips: [], untranslated: null }
}

function getFieldValue(inv: InvoiceOut, name: string): unknown {
  const fields = inv.current_extraction?.extracted_fields ?? {}
  switch (name) {
    case 'vendor_name':
      return fields.vendor_name?.value
    case 'invoice_date':
      return fields.invoice_date?.value
    case 'total':
      return fields.total?.value
    case 'currency':
      return fields.currency?.value
    case 'triage_state':
      return inv.current_extraction?.predicted_triage_state
    case 'is_duplicate':
      return inv.current_extraction?.predicted_triage_state === 'likely_duplicate'
        ? 'true'
        : 'false'
    default:
      return null
  }
}

function chipMatches(inv: InvoiceOut, c: FilterChip): boolean {
  const v = getFieldValue(inv, c.field)
  if (v == null) return false
  switch (c.op) {
    case 'eq':
      return String(v) === String(c.value)
    case 'neq':
      return String(v) !== String(c.value)
    case 'gt':
      return Number(v) > Number(c.value)
    case 'gte':
      return Number(v) >= Number(c.value)
    case 'lt':
      return Number(v) < Number(c.value)
    case 'lte':
      return Number(v) <= Number(c.value)
    case 'contains':
      return String(v).toLowerCase().includes(String(c.value).toLowerCase())
    case 'between': {
      if (!Array.isArray(c.value) || c.value.length !== 2) return true
      const [a, b] = c.value
      return String(v) >= String(a) && String(v) <= String(b)
    }
    default:
      return true
  }
}

function filterByChips(invoices: InvoiceOut[], chips: FilterChip[]): InvoiceOut[] {
  if (chips.length === 0) return invoices
  return invoices.filter((inv) => chips.every((c) => chipMatches(inv, c)))
}

export function SearchPalette({
  onClose,
  onOpen,
}: {
  onClose: () => void
  onOpen: (id: string) => void
}) {
  const { data: invoices = [] } = useInboxQuery()
  const [q, setQ] = useState('Vega invoices last 3 months over $5k')
  const [chips, setChips] = useState<FilterChip[]>([])
  const [untranslated, setUntranslated] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
    inputRef.current?.select()
  }, [])

  useEffect(() => {
    if (q.trim() === '') {
      setChips([])
      setUntranslated(null)
      return
    }
    const id = setTimeout(() => {
      const t = translate(q)
      setChips(t.chips)
      setUntranslated(t.untranslated)
    }, 220)
    return () => clearTimeout(id)
  }, [q])

  const results = useMemo(() => filterByChips(invoices, chips), [invoices, chips])
  const hasQuery = q.trim() !== ''

  return (
    <div className="scrim" onClick={onClose}>
      <div className="palette" onClick={(e) => e.stopPropagation()}>
        <div className="palette-input">
          <Icons.search />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search invoices, or ask in plain English…"
            onKeyDown={(e) => {
              if (e.key === 'Escape') onClose()
            }}
          />
          <Kbd>esc</Kbd>
        </div>

        {hasQuery && chips.length > 0 && (
          <div className="palette-chips">
            {chips.map((c, i) => (
              <Chip
                key={i}
                field={c.field}
                op={c.op}
                value={c.value}
                onRemove={() => setChips((cs) => cs.filter((_, j) => j !== i))}
              />
            ))}
            <span className="chip chip-add">
              <Icons.plus />
              <span>Add filter</span>
            </span>
          </div>
        )}

        {untranslated && (
          <div className="palette-untranslated">
            <Icons.warn />
            <div>
              <b>Partially translated.</b> Couldn't express this in structured query:{' '}
              <span
                className="mono-snip"
                style={{
                  background: 'rgba(255,255,255,0.7)',
                  padding: '0 5px',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                "{untranslated}"
              </span>{' '}
              — results below ignore that constraint.
            </div>
          </div>
        )}

        {!hasQuery ? (
          <div className="palette-section">
            <div className="palette-section-head">Try</div>
            {SUGGESTED.map((s, i) => (
              <div key={i} className="palette-row" onClick={() => setQ(s)}>
                <Icons.spark />
                <span>{s}</span>
                <Kbd>{`⌘${i + 1}`}</Kbd>
              </div>
            ))}
          </div>
        ) : chips.length === 0 ? (
          <div
            style={{
              padding: '28px 18px',
              fontSize: 13,
              color: 'var(--ink-60)',
              textAlign: 'center',
            }}
          >
            No translation yet — try one of the suggestions above, or rephrase.
          </div>
        ) : (
          <div className="palette-section" style={{ maxHeight: 360, overflowY: 'auto' }}>
            <div className="palette-section-head">Results</div>
            {results.length === 0 ? (
              <div className="palette-row" style={{ color: 'var(--ink-48)' }}>
                No invoices match this query.
              </div>
            ) : (
              results.map((inv) => {
                const fields = inv.current_extraction?.extracted_fields ?? {}
                const tState = (inv.current_extraction?.predicted_triage_state ??
                  'needs_review') as TriageState
                return (
                  <div key={inv.id} className="palette-row" onClick={() => onOpen(inv.id)}>
                    <Icons.doc />
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'baseline',
                        gap: 8,
                        flex: 1,
                        minWidth: 0,
                      }}
                    >
                      <span style={{ fontWeight: 500 }}>
                        {String(fields.vendor_name?.value ?? '—')}
                      </span>
                      <span className="muted mono" style={{ fontSize: 11.5 }}>
                        {String(fields.invoice_number?.value ?? '—')}
                      </span>
                      <span className="muted" style={{ fontSize: 11.5 }}>
                        {String(fields.invoice_date?.value ?? '—')}
                      </span>
                    </div>
                    <span className="num" style={{ fontSize: 12.5, color: 'var(--ink-80)' }}>
                      {String(fields.currency?.value ?? '')}{' '}
                      {fields.total?.value != null
                        ? formatNumber(Number(fields.total.value))
                        : '—'}
                    </span>
                    <TriagePill
                      variant={inv.review_status === 'unprocessable' ? 'unprocessable' : tState}
                    />
                  </div>
                )
              })
            )}
          </div>
        )}

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 14,
            padding: '8px 18px',
            borderTop: '1px solid var(--hairline)',
            fontSize: 11.5,
            color: 'var(--ink-48)',
            background: 'var(--surface-recess)',
          }}
        >
          <span>
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> navigate
          </span>
          <span>
            <Kbd>↵</Kbd> open
          </span>
          <span>
            <Kbd>tab</Kbd> edit chip
          </span>
          <span style={{ marginLeft: 'auto' }}>
            {results.length} match{results.length === 1 ? '' : 'es'}
          </span>
        </div>
      </div>
    </div>
  )
}
