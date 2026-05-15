import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Chip } from '@/components/primitives/Chip'
import { Icons } from '@/components/primitives/Icons'
import { Kbd } from '@/components/primitives/Kbd'
import { TriagePill } from '@/components/primitives/TriagePill'
import {
  type FilterClause,
  type StructuredQuery,
  useSearchQuery,
  useTranslateMutation,
} from '@/state/invoices'
import type { TriageState } from '@/types/generated/domain'
import { formatNumber } from '@/utils/format'

const SUGGESTED = [
  'duplicates from Vega',
  'invoices over $5000',
  'anomalies this month',
  'encrypted invoices',
  'confirmed from Halcyon Software',
]

const EMPTY_TRANSLATION: StructuredQuery = {
  filters: [],
  limit: 50,
  untranslated_intent: null,
}

export function SearchPalette({
  onClose,
  onOpen,
}: {
  onClose: () => void
  onOpen: (id: string) => void
}) {
  const [q, setQ] = useState('')
  const [debounced, setDebounced] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    inputRef.current?.focus()
    inputRef.current?.select()
  }, [])

  useEffect(() => {
    const id = setTimeout(() => setDebounced(q.trim()), 240)
    return () => clearTimeout(id)
  }, [q])

  const translate = useTranslateMutation()
  const [translation, setTranslation] = useState<StructuredQuery>(EMPTY_TRANSLATION)
  const [removedChips, setRemovedChips] = useState<Set<number>>(new Set())

  useEffect(() => {
    if (debounced === '') {
      setTranslation(EMPTY_TRANSLATION)
      setRemovedChips(new Set())
      return
    }
    let cancelled = false
    translate
      .mutateAsync(debounced)
      .then((result) => {
        if (cancelled) return
        setTranslation(result)
        setRemovedChips(new Set())
      })
      .catch(() => {
        if (cancelled) return
        setTranslation({ ...EMPTY_TRANSLATION, untranslated_intent: debounced })
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced])

  const effectiveQuery = useMemo<StructuredQuery>(() => {
    const filters = translation.filters.filter((_, i) => !removedChips.has(i))
    return { ...translation, filters }
  }, [translation, removedChips])

  const shouldSearch = effectiveQuery.filters.length > 0
  const { data: results = [], isFetching } = useSearchQuery(
    shouldSearch ? effectiveQuery : { filters: [], limit: 0, untranslated_intent: null },
  )

  const handleDeepLink = () => {
    onClose()
    navigate(`/search?q=${encodeURIComponent(JSON.stringify(effectiveQuery))}`)
  }

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
              if (e.key === 'Enter' && results.length === 1) {
                onOpen(results[0].id)
              }
            }}
          />
          {translate.isPending && (
            <span style={{ fontSize: 10.5, color: 'var(--ink-48)' }}>translating…</span>
          )}
          <Kbd>esc</Kbd>
        </div>

        {effectiveQuery.filters.length > 0 && (
          <div className="palette-chips">
            {translation.filters.map((c: FilterClause, i: number) =>
              removedChips.has(i) ? null : (
                <Chip
                  key={i}
                  field={c.field}
                  op={c.op}
                  value={c.value as never}
                  onRemove={() => setRemovedChips((s) => new Set(s).add(i))}
                />
              ),
            )}
          </div>
        )}

        {translation.untranslated_intent && (
          <div className="palette-untranslated">
            <Icons.warn />
            <div>
              <b>Partially translated.</b> Couldn't express this in a structured filter:{' '}
              <span
                className="mono-snip"
                style={{
                  background: 'rgba(255,255,255,0.7)',
                  padding: '0 5px',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                "{translation.untranslated_intent}"
              </span>{' '}
              — results below ignore that constraint.
            </div>
          </div>
        )}

        {debounced === '' ? (
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
        ) : !shouldSearch ? (
          <div
            style={{
              padding: '28px 18px',
              fontSize: 13,
              color: 'var(--ink-60)',
              textAlign: 'center',
            }}
          >
            No structured translation found — try one of the suggestions above, or rephrase.
          </div>
        ) : (
          <div className="palette-section" style={{ maxHeight: 360, overflowY: 'auto' }}>
            <div className="palette-section-head">
              Results {isFetching && <span className="muted">(loading…)</span>}
            </div>
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
            <Kbd>↵</Kbd> open
          </span>
          <span>
            <Kbd>esc</Kbd> close
          </span>
          {shouldSearch && (
            <span
              onClick={handleDeepLink}
              style={{ cursor: 'pointer', textDecoration: 'underline' }}
            >
              Open in full search →
            </span>
          )}
          <span style={{ marginLeft: 'auto' }}>
            {results.length} match{results.length === 1 ? '' : 'es'}
          </span>
        </div>
      </div>
    </div>
  )
}
