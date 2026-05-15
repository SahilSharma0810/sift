import type { VendorMemory } from '@/types/generated/domain'
import { formatMoney } from '@/utils/format'

import { Icons } from './Icons'

export function VendorMemoryCard({
  memory,
  vendorName,
  currency,
}: {
  memory: VendorMemory
  vendorName: string
  currency?: string
}) {
  const seen = memory.stats?.total_seen ?? 0
  if (seen === 0) {
    return (
      <div className="card p-3.5 text-xs text-ink-80">
        <div className="mb-1.5 flex items-center gap-2">
          <Icons.vendor />
          <b>No history yet</b>
        </div>
        <div className="muted text-xs">
          This is the first invoice from <b>{vendorName}</b>. Confirming will seed the
          vendor memory: format hints, typical totals, payment cadence.
        </div>
      </div>
    )
  }
  return (
    <div className="card">
      <div className="grid grid-cols-2 border-b border-hairline">
        <Cell label="Invoices seen" value={String(seen)} />
        <Cell label="Avg total" value={formatMoney(memory.stats?.avg_total, currency)} right />
      </div>
      {memory.rules && memory.rules.length > 0 && (
        <div className="px-3.5 py-2.5">
          <div className="muted mb-1.5 text-[12px] uppercase tracking-[0.06em]">
            Patterns learned
          </div>
          <div className="flex flex-col gap-1">
            {memory.rules.map((r) => (
              <div
                key={r.source_correction_id}
                className="flex items-center gap-2 text-xs"
              >
                <span className="grid size-3.5 flex-shrink-0 place-items-center bg-[#f3e9f9] text-[#6b3b8c]">
                  <Icons.brain />
                </span>
                <span className="text-ink-80">
                  {r.field}: {r.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Cell({
  label,
  value,
  right,
}: {
  label: string
  value: string
  right?: boolean
}) {
  return (
    <div className={`px-3.5 py-2.5 ${right ? '' : 'border-r border-hairline'}`}>
      <div className="text-[12px] uppercase tracking-[0.06em] text-ink-48">{label}</div>
      <div
        className={`mt-0.5 font-mono text-[15px] font-medium text-ink ${
          right ? 'text-right' : 'text-left'
        }`}
      >
        {value}
      </div>
    </div>
  )
}
