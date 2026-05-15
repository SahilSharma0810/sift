import { useCallback, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { Btn } from '@/components/primitives/Btn'
import { Icons } from '@/components/primitives/Icons'
import { Kbd } from '@/components/primitives/Kbd'
import { StatusBadge } from '@/components/primitives/StatusBadge'
import { TriagePill } from '@/components/primitives/TriagePill'
import { WhyChip } from '@/components/primitives/WhyChip'
import { useConfirmMutation, useInboxQuery, useUploadMutation } from '@/state/invoices'
import type { InvoiceOut, TriageState } from '@/types/generated/domain'
import { formatNumber } from '@/utils/format'

type FilterId = 'all' | 'needs_review' | 'confident' | 'likely_duplicate' | 'unprocessable' | 'confirmed'

function pillVariant(inv: InvoiceOut): TriageState | 'unprocessable' {
  if (inv.review_status === 'unprocessable') return 'unprocessable'
  return (inv.current_extraction?.predicted_triage_state ?? 'needs_review') as TriageState
}

function minConfidence(inv: InvoiceOut): number | null {
  const cpf = inv.current_extraction?.confidence_per_field
  if (!cpf) return null
  const values = Object.values(cpf)
  if (values.length === 0) return null
  return Math.min(...values)
}

export function InboxScreen() {
  const { data: invoices = [], isLoading, error } = useInboxQuery()
  const upload = useUploadMutation()
  const [filter, setFilter] = useState<FilterId>('all')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const confirm = useConfirmMutation()

  const toggleSelect = (id: string) => {
    setSelected((s) => {
      const n = new Set(s)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }

  const handleBulkConfirm = () => {
    const ids = Array.from(selected)
    if (ids.length === 0) return
    const toastId = toast(
      `Confirming ${ids.length} ${ids.length === 1 ? 'invoice' : 'invoices'}…`,
      {
        duration: 10_000,
        action: {
          label: 'Undo',
          onClick: () => {

            toast.dismiss(toastId)
            toast.info('Undo applied — pending confirmations cancelled.')
          },
        },
      }
    )
    for (const id of ids) {
      confirm.mutate(id)
    }
    setSelected(new Set())
  }

  const [dragOver, setDragOver] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const counts = useMemo(() => {
    const c = {
      all: invoices.length,
      needs_review: 0,
      confident: 0,
      likely_duplicate: 0,
      unprocessable: 0,
      confirmed: 0,
    }
    for (const inv of invoices) {
      if (inv.review_status === 'unprocessable') c.unprocessable += 1
      if (inv.review_status === 'confirmed') c.confirmed += 1
      const t = inv.current_extraction?.predicted_triage_state
      if (t === 'needs_review' && inv.review_status === 'pending') c.needs_review += 1
      if (t === 'confident' && inv.review_status === 'pending') c.confident += 1
      if (t === 'likely_duplicate' && inv.review_status === 'pending')
        c.likely_duplicate += 1
    }
    return c
  }, [invoices])

  const filtered = useMemo(() => {
    return invoices.filter((inv) => {
      if (filter === 'all') return true
      if (filter === 'unprocessable') return inv.review_status === 'unprocessable'
      if (filter === 'confirmed') return inv.review_status === 'confirmed'
      const t = inv.current_extraction?.predicted_triage_state
      if (filter === 'needs_review')
        return t === 'needs_review' && inv.review_status === 'pending'
      if (filter === 'confident') return t === 'confident' && inv.review_status === 'pending'
      if (filter === 'likely_duplicate')
        return t === 'likely_duplicate' && inv.review_status === 'pending'
      return true
    })
  }, [invoices, filter])

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files?.length) return
      const file = files[0]
      if (file.type !== 'application/pdf') {
        toast.error('Only PDFs are accepted right now.')
        return
      }
      const id = toast.loading(`Extracting ${file.name}…`)
      try {
        const inv = await upload.mutateAsync(file)
        const vendor =
          inv.current_extraction?.extracted_fields?.vendor_name?.value ?? 'invoice'
        toast.success(`Extracted ${String(vendor)}`, { id })
      } catch (e) {
        toast.error(`Upload failed: ${(e as Error).message}`, { id })
      }
    },
    [upload]
  )

  return (
    <div className="inbox-content">
      <div
        className="dropzone"
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          void handleFiles(e.dataTransfer.files)
        }}
        onClick={() => fileInput.current?.click()}
        style={
          dragOver
            ? { borderColor: 'var(--primary)', background: 'var(--primary-bg-soft)' }
            : undefined
        }
      >
        <div className="dropzone-icon">
          <Icons.upload />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 500, color: 'var(--ink)', fontSize: 13.5 }}>
            Drop invoices to extract
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
            Digital or scanned PDF · We hash, route through Haiku → Sonnet → Opus as needed,
            and triage in &lt; 8s
          </div>
        </div>
        <Btn variant="primary" icon={Icons.upload}>
          Upload
        </Btn>
        <input
          ref={fileInput}
          type="file"
          accept="application/pdf"
          className="hidden"
          style={{ display: 'none' }}
          onChange={(e) => void handleFiles(e.target.files)}
        />
      </div>

      <div className="inbox-toolbar" style={{ marginTop: 16 }}>
        <div className="seg" role="tablist">
          <FilterTab id="all" cur={filter} set={setFilter} label="All" count={counts.all} />
          <FilterTab
            id="needs_review"
            cur={filter}
            set={setFilter}
            label="Needs review"
            count={counts.needs_review}
            variant="needs_review"
          />
          <FilterTab
            id="confident"
            cur={filter}
            set={setFilter}
            label="Confident"
            count={counts.confident}
            variant="confident"
          />
          <FilterTab
            id="likely_duplicate"
            cur={filter}
            set={setFilter}
            label="Duplicates"
            count={counts.likely_duplicate}
            variant="likely_duplicate"
          />
          <FilterTab
            id="unprocessable"
            cur={filter}
            set={setFilter}
            label="Unprocessable"
            count={counts.unprocessable}
            variant="unprocessable"
          />
          <FilterTab
            id="confirmed"
            cur={filter}
            set={setFilter}
            label="Confirmed"
            count={counts.confirmed}
          />
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <Btn variant="ghost" size="sm" icon={Icons.filter}>
            Filter
          </Btn>
          <Btn variant="ghost" size="sm" icon={Icons.download}>
            Export
          </Btn>
          {selected.size > 0 && (
            <>
              <span className="mono" style={{ alignSelf: 'center', fontSize: 12, color: 'var(--ink-60)' }}>
                {selected.size} selected
              </span>
              <Btn size="sm" icon={Icons.check} variant="primary" onClick={handleBulkConfirm}>
                Confirm
              </Btn>
            </>
          )}
        </div>
      </div>

      <div
        style={{
          border: '1px solid var(--hairline)',
          overflow: 'hidden',
          background: 'var(--surface)',
        }}
      >
        <table className="table">
          <thead>
            <tr>
              <th style={{ width: 40 }}></th>
              <th style={{ width: 150 }}>Triage</th>
              <th>Vendor</th>
              <th>Invoice #</th>
              <th>Date</th>
              <th className="col-right">Amount</th>
              <th>Why</th>
              <th style={{ width: 76 }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={8} style={{ padding: 24, textAlign: 'center', color: 'var(--ink-60)' }}>
                  Loading…
                </td>
              </tr>
            )}
            {error && (
              <tr>
                <td colSpan={8} style={{ padding: 24, textAlign: 'center', color: '#b22020' }}>
                  Failed to load invoices.
                </td>
              </tr>
            )}
            {!isLoading && filtered.length === 0 && (
              <tr>
                <td colSpan={8} style={{ padding: 24, textAlign: 'center', color: 'var(--ink-60)' }}>
                  {invoices.length === 0
                    ? 'No invoices yet — drop one above to get started.'
                    : `No invoices match the "${filter}" filter.`}
                </td>
              </tr>
            )}
            {filtered.map((inv) => {
              const fields = inv.current_extraction?.extracted_fields ?? {}
              const reasons = inv.current_extraction?.predicted_triage_reasons ?? []
              return (
                <tr key={inv.id} data-selected={selected.has(inv.id) ? 'true' : 'false'}>
                  <td onClick={(e) => { e.stopPropagation(); toggleSelect(inv.id); }}>
                    <input
                      type="checkbox"
                      checked={selected.has(inv.id)}
                      readOnly
                      style={{ accentColor: 'var(--primary)', cursor: 'pointer' }}
                    />
                  </td>
                  <td>
                    <TriagePill variant={pillVariant(inv)} pct={minConfidence(inv)} />
                  </td>
                  <td style={{ fontWeight: 500 }}>
                    <Link
                      to={`/invoice/${inv.id}`}
                      style={{
                        color: 'inherit',
                        textDecoration: 'none',
                        display: 'block',
                      }}
                    >
                      {String(fields.vendor_name?.value ?? '—')}
                    </Link>
                  </td>
                  <td className="num muted">{String(fields.invoice_number?.value ?? '—')}</td>
                  <td className="num muted">{String(fields.invoice_date?.value ?? '—')}</td>
                  <td className="col-right num">
                    {fields.total?.value != null ? (
                      <span>
                        <span className="muted" style={{ marginRight: 4 }}>
                          {String(fields.currency?.value ?? '')}
                        </span>
                        {formatNumber(Number(fields.total.value))}
                      </span>
                    ) : (
                      <span className="subtle">—</span>
                    )}
                  </td>
                  <td>
                    {reasons.length === 0 ? (
                      <span className="subtle">—</span>
                    ) : (
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {reasons.slice(0, 2).map((r, i) => (
                          <WhyChip key={i} reason={r} />
                        ))}
                        {reasons.length > 2 && (
                          <span className="subtle mono" style={{ fontSize: 11 }}>
                            +{reasons.length - 2}
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                  <td>
                    <StatusBadge status={inv.review_status} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div
        style={{
          marginTop: 14,
          fontSize: 12,
          color: 'var(--ink-48)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          flexWrap: 'wrap',
        }}
      >
        <span>
          <Kbd>J</Kbd> <Kbd>K</Kbd> navigate
        </span>
        <span style={{ width: 1, height: 10, background: 'var(--hairline)' }} />
        <span>
          <Kbd>Enter</Kbd> open
        </span>
        <span style={{ width: 1, height: 10, background: 'var(--hairline)' }} />
        <span>
          <Kbd>C</Kbd> confirm
        </span>
        <span style={{ width: 1, height: 10, background: 'var(--hairline)' }} />
        <span>
          <Kbd>X</Kbd> dismiss
        </span>
        <span style={{ width: 1, height: 10, background: 'var(--hairline)' }} />
        <span>
          <Kbd>⌘</Kbd> <Kbd>K</Kbd> natural-language search
        </span>
        <span style={{ marginLeft: 'auto' }}>
          {filtered.length} of {invoices.length} invoices
        </span>
      </div>
    </div>
  )
}

function FilterTab({
  id,
  cur,
  set,
  label,
  count,
  variant,
}: {
  id: FilterId
  cur: FilterId
  set: (v: FilterId) => void
  label: string
  count: number
  variant?: 'confident' | 'needs_review' | 'likely_duplicate' | 'unprocessable'
}) {
  const active = cur === id
  return (
    <button data-active={active} onClick={() => set(id)}>
      {variant && (
        <span
          className="pill-dot"
          style={{
            width: 6,
            height: 6,
            borderRadius: 50,
            background:
              variant === 'confident'
                ? 'var(--triage-confident)'
                : variant === 'needs_review'
                  ? 'var(--triage-needs-review)'
                  : variant === 'likely_duplicate'
                    ? 'var(--triage-duplicate)'
                    : 'var(--triage-unprocessable)',
          }}
        />
      )}
      <span>{label}</span>
      <span className="seg-count">{count}</span>
    </button>
  )
}
