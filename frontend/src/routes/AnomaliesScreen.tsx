import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { AnomalyCard } from '@/components/anomalies/AnomalyCard'
import {
  useAcknowledgeAnomaly,
  useAnomaliesQuery,
  useBulkAcknowledgeAnomalies,
} from '@/state/anomalies'
import type { AnomalyOut } from '@/types/generated/domain'

type FilterKey = 'unreviewed' | 'all' | 'amount' | 'frequency' | 'pattern' | 'acknowledged'

const EMPTY: Record<FilterKey, string> = {
  unreviewed: 'Nothing to flag. New anomalies surface here as invoices arrive.',
  all: 'No anomalies in the corpus yet.',
  amount: 'Nothing to flag. New anomalies surface here as invoices arrive.',
  frequency: "Sift doesn't yet flag frequency anomalies — coming next.",
  pattern: 'Pattern anomalies (terms changed, new line items) ship in a later iteration.',
  acknowledged: 'Nothing acknowledged yet.',
}

function filterAnomalies(anomalies: AnomalyOut[], key: FilterKey): AnomalyOut[] {
  if (key === 'all') return anomalies
  if (key === 'unreviewed') return anomalies.filter((a) => a.status === 'unreviewed')
  if (key === 'acknowledged') return anomalies.filter((a) => a.status === 'acknowledged')
  if (key === 'amount') {
    return anomalies.filter((a) => a.status === 'unreviewed' && a.type === 'amount')
  }
  return []
}

function formatCurrency(amount: number, currency: string): string {
  if (currency === 'USD') {
    if (amount >= 1_000) return `$${(amount / 1_000).toFixed(1)}K`
    return `$${amount.toFixed(0)}`
  }
  if (amount >= 1_000) return `${currency} ${(amount / 1_000).toFixed(1)}K`
  return `${currency} ${amount.toFixed(0)}`
}

export function AnomaliesScreen() {
  const navigate = useNavigate()
  const { data, isLoading, isError } = useAnomaliesQuery()
  const acknowledge = useAcknowledgeAnomaly()
  const bulkAcknowledge = useBulkAcknowledgeAnomalies()
  const [filter, setFilter] = useState<FilterKey>('unreviewed')
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const visible = useMemo(
    () => filterAnomalies(data?.anomalies ?? [], filter),
    [data?.anomalies, filter],
  )

  if (isLoading) {
    return (
      <div className="p-6 text-sm text-ink-60">Loading anomalies…</div>
    )
  }
  if (isError || !data) {
    return (
      <div className="p-6 text-sm text-aside-review">
        Couldn't load anomalies. Refresh to try again.
      </div>
    )
  }

  const onCardToggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const onAcknowledgeAll = () => {
    if (selected.size === 0) return
    bulkAcknowledge.mutate(Array.from(selected), {
      onSettled: () => setSelected(new Set()),
    })
  }

  return (
    <div className="px-6 py-5">
      <div className="mb-5">
        <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.10em] text-ink-48">
          What changed this period
        </div>
        <div className="mb-1 text-[21px] font-semibold tracking-[-0.012em] text-ink">
          {data.counts.unreviewed} {data.counts.unreviewed === 1 ? 'anomaly needs' : 'anomalies need'} a second look
        </div>
        <div className="max-w-[70ch] text-[14px] leading-[1.5] text-ink-60">
          The extractions are confident — the <i>values</i> are unusual.
          Per-vendor Z-scores flag invoices that need a second pair of eyes
          before payment.
        </div>
      </div>

      <div className="mb-4 grid grid-cols-4 border border-hairline bg-surface">
        <StatTile label="Unreviewed" value={String(data.counts.unreviewed)} />
        <StatTile
          label="Total $ flagged"
          value={formatCurrency(data.aggregates.total_flagged_amount, data.aggregates.total_flagged_currency)}
          suffix={data.aggregates.total_flagged_currency}
        />
        <StatTile label="Vendors affected" value={String(data.aggregates.vendors_affected)} />
        <StatTile
          label="Highest severity"
          value={data.aggregates.highest_severity_z != null ? `${data.aggregates.highest_severity_z.toFixed(1)}σ` : '—'}
          suffix={data.aggregates.highest_severity_vendor ?? undefined}
        />
      </div>

      <div className="mb-3.5 flex items-center gap-2">
        <FilterTab id="unreviewed" cur={filter} set={setFilter} label="Unreviewed" count={data.counts.unreviewed} />
        <FilterTab id="all" cur={filter} set={setFilter} label="All" count={data.counts.all} />
        <FilterTab id="amount" cur={filter} set={setFilter} label="Amount" count={data.counts.amount} />
        <FilterTab id="frequency" cur={filter} set={setFilter} label="Frequency" count={data.counts.frequency} />
        <FilterTab id="pattern" cur={filter} set={setFilter} label="Pattern" count={data.counts.pattern} />
        <FilterTab id="acknowledged" cur={filter} set={setFilter} label="Acknowledged" count={data.counts.acknowledged} />
        <div className="ml-auto flex items-center gap-2">
          {selected.size > 0 && (
            <>
              <span className="font-mono text-[12px] text-ink-60">
                {selected.size} selected
              </span>
              <button
                type="button"
                onClick={onAcknowledgeAll}
                disabled={bulkAcknowledge.isPending}
                className="border border-action bg-action px-2.5 py-1 text-[12px] font-medium text-white transition-colors disabled:cursor-not-allowed disabled:opacity-60"
              >
                {bulkAcknowledge.isPending ? 'Acknowledging…' : 'Acknowledge all'}
              </button>
            </>
          )}
        </div>
      </div>

      {visible.length === 0 ? (
        <EmptyState message={EMPTY[filter]} />
      ) : (
        <div className="grid gap-3.5" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))' }}>
          {visible.map((a) => (
            <AnomalyCard
              key={a.id}
              anomaly={a}
              selected={selected.has(a.id)}
              onToggle={() => onCardToggle(a.id)}
              onAcknowledge={() => acknowledge.mutate(a.id)}
              onInvestigate={() => navigate(`/invoice/${a.invoice_id}`)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function StatTile({ label, value, suffix }: { label: string; value: string; suffix?: string }) {
  return (
    <div className="border-r border-hairline px-5 py-4 last:border-r-0">
      <div className="text-[10.5px] font-medium uppercase tracking-[0.06em] text-ink-48">
        {label}
      </div>
      <div className="mt-1.5 flex items-baseline gap-2">
        <span className="font-mono text-[22px] font-semibold tracking-[-0.012em] text-ink">
          {value}
        </span>
        {suffix && (
          <span className="font-mono text-[11.5px] text-ink-60">{suffix}</span>
        )}
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
}: {
  id: FilterKey
  cur: FilterKey
  set: (k: FilterKey) => void
  label: string
  count: number
}) {
  const active = cur === id
  return (
    <button
      type="button"
      data-active={active}
      onClick={() => set(id)}
      className={[
        'inline-flex items-center gap-1.5 border px-2.5 py-1 text-[12px] font-medium transition-colors',
        active
          ? 'border-action bg-action text-white'
          : 'border-hairline bg-surface text-ink-60 hover:border-ink-48 hover:text-ink',
      ].join(' ')}
    >
      <span>{label}</span>
      <span className="font-mono text-[11px] opacity-80">{count}</span>
    </button>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="border border-hairline bg-surface px-10 py-12 text-center text-ink-60">
      <div className="mb-1.5 text-[16px] font-semibold text-ink">Nothing to flag</div>
      <div className="mx-auto max-w-[40ch] text-[13.5px]">{message}</div>
    </div>
  )
}
