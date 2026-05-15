import { useEffect, useMemo, useReducer, useRef, useState } from 'react'
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

interface PaletteState {
  translation: StructuredQuery
  removedChips: Set<number>
}

type PaletteAction =
  | { type: 'reset' }
  | { type: 'translated'; result: StructuredQuery }
  | { type: 'failed'; intent: string }
  | { type: 'removeChip'; index: number }

function paletteReducer(state: PaletteState, action: PaletteAction): PaletteState {
  switch (action.type) {
    case 'reset':
      return { translation: EMPTY_TRANSLATION, removedChips: new Set() }
    case 'translated':
      return { translation: action.result, removedChips: new Set() }
    case 'failed':
      return {
        translation: { ...EMPTY_TRANSLATION, untranslated_intent: action.intent },
        removedChips: state.removedChips,
      }
    case 'removeChip': {
      const next = new Set(state.removedChips)
      next.add(action.index)
      return { ...state, removedChips: next }
    }
  }
}

function chipKey(c: FilterClause): string {
  return `${c.field}|${c.op}|${JSON.stringify(c.value)}`
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
  const [state, dispatch] = useReducer(paletteReducer, {
    translation: EMPTY_TRANSLATION,
    removedChips: new Set<number>(),
  })

  useEffect(() => {
    if (debounced === '') {
      dispatch({ type: 'reset' })
      return
    }
    let cancelled = false
    translate
      .mutateAsync(debounced)
      .then((result) => {
        if (cancelled) return
        dispatch({ type: 'translated', result })
      })
      .catch(() => {
        if (cancelled) return
        dispatch({ type: 'failed', intent: debounced })
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced])

  const { translation, removedChips } = state

  const effectiveQuery = useMemo<StructuredQuery>(() => {
    const filters = translation.filters.filter((_, i) => !removedChips.has(i))
    return { ...translation, filters }
  }, [translation, removedChips])

  const shouldSearch = effectiveQuery.filters.length > 0
  const { data: results = [], isFetching } = useSearchQuery(
    effectiveQuery,
    { enabled: shouldSearch },
  )

  const handleDeepLink = () => {
    onClose()
    navigate(`/search?q=${encodeURIComponent(JSON.stringify(effectiveQuery))}`)
  }

  const handleScrimClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose()
  }
  const handleScrimKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
    }
  }

  return (
    <div
      className="scrim"
      role="presentation"
      onClick={handleScrimClick}
      onKeyDown={handleScrimKey}
    >
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Search invoices"
      >
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
            <span className="text-xs text-ink-48">translating…</span>
          )}
          <Kbd>esc</Kbd>
        </div>

        {effectiveQuery.filters.length > 0 && (
          <div className="palette-chips">
            {translation.filters.map((c: FilterClause, i: number) =>
              removedChips.has(i) ? null : (
                <Chip
                  key={chipKey(c)}
                  field={c.field}
                  op={c.op}
                  value={c.value as never}
                  onRemove={() => dispatch({ type: 'removeChip', index: i })}
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
              <span className="mono-snip bg-white/70 px-1.5 font-mono">
                "{translation.untranslated_intent}"
              </span>
              . Results below ignore that constraint.
            </div>
          </div>
        )}

        {debounced === '' ? (
          <div className="palette-section">
            <div className="palette-section-head">Try</div>
            {SUGGESTED.map((s, i) => (
              <PaletteRow key={s} onSelect={() => setQ(s)}>
                <Icons.spark />
                <span>{s}</span>
                <Kbd>{`⌘${i + 1}`}</Kbd>
              </PaletteRow>
            ))}
          </div>
        ) : !shouldSearch ? (
          <div className="px-[18px] py-7 text-center text-sm text-ink-60">
            No structured translation found; try one of the suggestions above, or rephrase.
          </div>
        ) : (
          <div className="palette-section max-h-[360px] overflow-y-auto">
            <div className="palette-section-head">
              Results {isFetching && <span className="muted">(loading…)</span>}
            </div>
            {results.length === 0 ? (
              <div className="palette-row text-ink-48">No invoices match this query.</div>
            ) : (
              results.map((inv) => {
                const fields = inv.current_extraction?.extracted_fields ?? {}
                const tState = (inv.current_extraction?.predicted_triage_state ??
                  'needs_review') as TriageState
                return (
                  <PaletteRow key={inv.id} onSelect={() => onOpen(inv.id)}>
                    <Icons.doc />
                    <div className="flex min-w-0 flex-1 items-baseline gap-2">
                      <span className="font-medium">
                        {String(fields.vendor_name?.value ?? '–')}
                      </span>
                      <span className="muted mono text-xs">
                        {String(fields.invoice_number?.value ?? '–')}
                      </span>
                      <span className="muted text-xs">
                        {String(fields.invoice_date?.value ?? '–')}
                      </span>
                    </div>
                    <span className="num text-xs text-ink-80">
                      {String(fields.currency?.value ?? '')}{' '}
                      {fields.total?.value != null
                        ? formatNumber(Number(fields.total.value))
                        : '–'}
                    </span>
                    <TriagePill
                      variant={inv.review_status === 'unprocessable' ? 'unprocessable' : tState}
                    />
                  </PaletteRow>
                )
              })
            )}
          </div>
        )}

        <PaletteFooter
          shouldSearch={shouldSearch}
          onDeepLink={handleDeepLink}
          resultCount={results.length}
        />
      </div>
    </div>
  )
}

function PaletteRow({
  onSelect,
  children,
}: {
  onSelect: () => void
  children: React.ReactNode
}) {
  return (
    <div
      className="palette-row"
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect()
        }
      }}
    >
      {children}
    </div>
  )
}

function PaletteFooter({
  shouldSearch,
  onDeepLink,
  resultCount,
}: {
  shouldSearch: boolean
  onDeepLink: () => void
  resultCount: number
}) {
  return (
    <div className="flex items-center gap-3.5 border-t border-hairline bg-surface-recess px-[18px] py-2 text-xs text-ink-48">
      <span>
        <Kbd>↵</Kbd> open
      </span>
      <span>
        <Kbd>esc</Kbd> close
      </span>
      {shouldSearch && (
        <button
          type="button"
          onClick={onDeepLink}
          className="cursor-pointer underline"
        >
          Open in full search →
        </button>
      )}
      <span className="ml-auto">
        {resultCount} match{resultCount === 1 ? '' : 'es'}
      </span>
    </div>
  )
}
