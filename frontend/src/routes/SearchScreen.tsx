import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { Btn } from '@/components/primitives/Btn'
import { Icons } from '@/components/primitives/Icons'
import { TriagePill } from '@/components/primitives/TriagePill'
import {
  EMPTY_QUERY,
  type FilterClause,
  type StructuredQuery,
  useSearchQuery,
  useTranslateMutation,
} from '@/state/invoices'
import type { InvoiceOut, TriageState } from '@/types/generated/domain'
import { formatNumber } from '@/utils/format'

function parseQueryParam(raw: string | null): StructuredQuery {
  if (!raw) return { ...EMPTY_QUERY }
  try {
    const parsed = JSON.parse(raw) as StructuredQuery
    return {
      filters: Array.isArray(parsed.filters) ? parsed.filters : [],
      limit: parsed.limit ?? 50,
      sort: parsed.sort ?? null,
      untranslated_intent: parsed.untranslated_intent ?? null,
    }
  } catch {
    return { ...EMPTY_QUERY }
  }
}

async function downloadExport(query: StructuredQuery, format: 'csv' | 'json'): Promise<void> {
  const res = await fetch(`/api/search/export?format=${format}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(query),
  })
  if (!res.ok) return
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const today = new Date().toISOString().slice(0, 10)
  a.download = `sift-export-${today}.${format}`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function chipLabel(c: FilterClause): string {
  const valueText = Array.isArray(c.value)
    ? c.value.join(' to ')
    : typeof c.value === 'boolean'
      ? c.value
        ? 'true'
        : 'false'
      : String(c.value)
  const opLabel: Record<string, string> = {
    eq: '=',
    neq: '≠',
    gt: '>',
    gte: '≥',
    lt: '<',
    lte: '≤',
    in: 'in',
    between: 'between',
    contains: 'contains',
    fts_matches: 'matches',
  }
  return `${c.field} ${opLabel[c.op] ?? c.op} ${valueText}`
}

function pillVariant(inv: InvoiceOut): TriageState | 'unprocessable' {
  if (inv.review_status === 'unprocessable') return 'unprocessable'
  return (inv.current_extraction?.predicted_triage_state ?? 'needs_review') as TriageState
}

export function SearchScreen() {
  const [params, setParams] = useSearchParams()
  const query = parseQueryParam(params.get('q'))
  const [nlInput, setNlInput] = useState('')
  const navigate = useNavigate()

  const translate = useTranslateMutation()
  const { data: results = [], isFetching, error } = useSearchQuery(query)

  useEffect(() => {
    setNlInput('')
  }, [params])

  const setQuery = (next: StructuredQuery) => {
    setParams({ q: JSON.stringify(next) }, { replace: true })
  }

  const clearAll = () => setParams({}, { replace: true })

  const removeChip = (idx: number) => {
    const next: StructuredQuery = {
      ...query,
      filters: query.filters.filter((_, i) => i !== idx),
    }
    setQuery(next)
  }

  const onNlSubmit = async (raw: string) => {
    const trimmed = raw.trim()
    if (!trimmed) {
      clearAll()
      return
    }
    try {
      const translated = await translate.mutateAsync(trimmed)
      setQuery({
        filters: translated.filters,
        limit: translated.limit ?? 50,
        sort: translated.sort ?? null,
        untranslated_intent: translated.untranslated_intent ?? null,
      })
    } catch (e) {

      setQuery({
        ...EMPTY_QUERY,
        untranslated_intent: trimmed,
      })
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div
        style={{
          padding: '14px 20px',
          borderBottom: '1px solid var(--hairline)',
          background: 'var(--paper)',
        }}
      >

        <form
          onSubmit={(e) => {
            e.preventDefault()
            void onNlSubmit(nlInput)
          }}
          style={{ display: 'flex', gap: 8, alignItems: 'center' }}
        >
          <div
            style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '8px 12px',
              border: '1px solid var(--hairline)',
              background: '#fff',
            }}
          >
            <Icons.search />
            <input
              type="text"
              value={nlInput}
              onChange={(e) => setNlInput(e.target.value)}
              placeholder="Ask in plain English — e.g. 'duplicates from Vega over $5,000 this month'"
              style={{
                flex: 1,
                border: 'none',
                outline: 'none',
                background: 'transparent',
                fontSize: 14,
              }}
            />
            {translate.isPending && (
              <span style={{ fontSize: 11, color: 'var(--ink-48)' }}>translating…</span>
            )}
          </div>
          <Btn variant="primary" type="submit">
            Search
          </Btn>
          {query.filters.length > 0 && (
            <>
              <Btn variant="ghost" onClick={() => downloadExport(query, 'csv')}>
                Export CSV
              </Btn>
              <Btn variant="ghost" onClick={() => downloadExport(query, 'json')}>
                Export JSON
              </Btn>
              <Btn variant="ghost" onClick={clearAll}>
                Clear
              </Btn>
            </>
          )}
        </form>

        {}
        {query.filters.length > 0 && (
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 6,
              marginTop: 12,
              alignItems: 'center',
            }}
          >
            <span
              style={{
                fontSize: 10.5,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: 'var(--ink-48)',
                marginRight: 4,
              }}
            >
              Filters
            </span>
            {query.filters.map((c, i) => (
              <ChipWithRemove
                key={`${c.field}-${c.op}-${i}`}
                label={chipLabel(c)}
                onRemove={() => removeChip(i)}
              />
            ))}
          </div>
        )}

        {}
        {query.untranslated_intent && (
          <div
            style={{
              marginTop: 10,
              padding: '8px 12px',
              fontSize: 12.5,
              color: '#7a4a00',
              background: '#fdf3da',
              border: '1px solid #e6c75a',
              display: 'flex',
              gap: 8,
              alignItems: 'flex-start',
            }}
          >
            <span style={{ marginTop: 1 }}>⚠</span>
            <div>
              <b>Partial translation.</b> The system couldn't translate "
              <em>{query.untranslated_intent}</em>" into a structured filter — surfaced here so it's
              not silently dropped.
            </div>
          </div>
        )}
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: '12px 20px' }}>
        {error ? (
          <div style={{ color: 'var(--ink-60)', padding: 16 }}>
            Search failed: {String(error)}
          </div>
        ) : isFetching && results.length === 0 ? (
          <div style={{ color: 'var(--ink-60)', padding: 16 }}>Loading…</div>
        ) : results.length === 0 ? (
          <div
            style={{
              padding: 32,
              textAlign: 'center',
              color: 'var(--ink-60)',
              fontSize: 13.5,
            }}
          >
            {query.filters.length === 0 ? (
              <>Type a query above to search the corpus.</>
            ) : (
              <>No invoices match this query.</>
            )}
          </div>
        ) : (
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: 13.5,
            }}
          >
            <thead>
              <tr>
                {[
                  ['triage', 110],
                  ['vendor', 220],
                  ['invoice #', 160],
                  ['date', 110],
                  ['total', 110],
                  ['status', 110],
                ].map(([label, w]) => (
                  <th
                    key={String(label)}
                    style={{
                      textAlign: 'left',
                      padding: '8px 12px',
                      fontSize: 10.5,
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                      color: 'var(--ink-48)',
                      borderBottom: '1px solid var(--hairline)',
                      width: w as number,
                    }}
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {results.map((inv) => {
                const fields = inv.current_extraction?.extracted_fields ?? {}
                const vendor = fields.vendor_name?.value ?? '—'
                const invoiceNum = fields.invoice_number?.value ?? '—'
                const total = fields.total?.value
                const date = fields.invoice_date?.value ?? '—'
                return (
                  <tr
                    key={inv.id}
                    onClick={() => navigate(`/invoice/${inv.id}`)}
                    style={{
                      cursor: 'pointer',
                      borderBottom: '1px solid var(--hairline-soft)',
                    }}
                  >
                    <td style={{ padding: '10px 12px' }}>
                      <TriagePill variant={pillVariant(inv)} />
                    </td>
                    <td style={{ padding: '10px 12px' }}>{String(vendor)}</td>
                    <td className="num" style={{ padding: '10px 12px' }}>{String(invoiceNum)}</td>
                    <td className="num" style={{ padding: '10px 12px' }}>{String(date)}</td>
                    <td className="num" style={{ padding: '10px 12px', textAlign: 'right' }}>
                      {total == null ? '—' : `$${formatNumber(Number(total))}`}
                    </td>
                    <td style={{ padding: '10px 12px', color: 'var(--ink-60)' }}>
                      {inv.review_status}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function ChipWithRemove({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '4px 4px 4px 10px',
        fontSize: 11.5,
        fontFamily: 'var(--font-mono)',
        color: 'var(--ink-80)',
        background: '#eef3fb',
        border: '1px solid #c2d4ee',
      }}
    >
      {label}
      <button
        onClick={onRemove}
        type="button"
        aria-label={`Remove ${label}`}
        style={{
          width: 18,
          height: 18,
          display: 'inline-grid',
          placeItems: 'center',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          color: 'var(--ink-60)',
          padding: 0,
        }}
      >
        ✕
      </button>
    </span>
  )
}
