import type { TaxBreakdownLine } from '@/types/generated/domain'
import { formatNumber } from '@/utils/format'

import { Icons } from './Icons'

const ROW_GRID = '[grid-template-columns:1fr_70px_90px]'

function taxRowKey(row: TaxBreakdownLine): string {
  return `${row.jurisdiction}|${row.rate ?? ''}|${row.amount}`
}

export function TaxBreakdownTable({ rows }: { rows: TaxBreakdownLine[] }) {
  if (!rows || rows.length === 0) {
    return (
      <div className="card flex items-center gap-2 px-3.5 py-3 text-xs text-ink-60">
        <Icons.layers />
        <span>Single tax line on this invoice; no per-jurisdiction breakdown.</span>
      </div>
    )
  }

  const sum = rows.reduce((acc, r) => acc + (r.amount ?? 0), 0)

  return (
    <div className="card">
      <div
        className={`grid ${ROW_GRID} items-center border-b border-hairline bg-surface-pearl px-3 py-2 text-[12px] uppercase tracking-[0.06em] text-ink-48`}
      >
        <div>Jurisdiction</div>
        <div className="text-right">Rate</div>
        <div className="text-right">Amount</div>
      </div>

      {rows.map((row) => (
        <div
          key={taxRowKey(row)}
          className={`grid ${ROW_GRID} items-center border-b border-hairline-soft px-3 py-[9px] text-[13px] text-ink-80`}
        >
          <div className="overflow-hidden pr-3 text-ellipsis">{row.jurisdiction}</div>
          <div className="num text-right">
            {row.rate == null ? <span className="subtle">–</span> : `${row.rate}%`}
          </div>
          <div className="num text-right font-medium">${formatNumber(row.amount)}</div>
        </div>
      ))}

      <div className="grid grid-cols-[1fr_90px] items-center bg-surface-pearl px-3 py-[9px] text-xs">
        <div className="text-[12px] uppercase tracking-[0.06em] text-ink-48">
          {rows.length} {rows.length === 1 ? 'jurisdiction' : 'jurisdictions'} · sum
        </div>
        <div className="num text-right font-medium text-ink">${formatNumber(sum)}</div>
      </div>
    </div>
  )
}
