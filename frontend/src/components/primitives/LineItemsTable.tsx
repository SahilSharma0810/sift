import type { LineItem } from '@/types/generated/domain'
import { formatNumber } from '@/utils/format'

import { Icons } from './Icons'

const ROW_GRID = '[grid-template-columns:1fr_60px_90px_90px]'

function lineItemKey(item: LineItem): string {
  return `${item.description}|${item.quantity ?? ''}|${item.unit_price ?? ''}|${item.line_total}`
}

export function LineItemsTable({ items }: { items: LineItem[] }) {
  if (!items || items.length === 0) {
    return (
      <div className="card flex items-center gap-2 px-3.5 py-3 text-xs text-ink-60">
        <Icons.layers />
        <span>No itemized line items on this invoice.</span>
      </div>
    )
  }

  const subtotalSum = items.reduce((acc, it) => acc + (it.line_total ?? 0), 0)

  return (
    <div className="card">
      <div
        className={`grid ${ROW_GRID} items-center border-b border-hairline bg-surface-pearl px-3 py-2 text-[12px] uppercase tracking-[0.06em] text-ink-48`}
      >
        <div>Description</div>
        <div className="text-right">Qty</div>
        <div className="text-right">Unit</div>
        <div className="text-right">Total</div>
      </div>

      {items.map((item) => (
        <div
          key={lineItemKey(item)}
          className={`grid ${ROW_GRID} items-center border-b border-hairline-soft px-3 py-[9px] text-[13px] text-ink-80`}
        >
          <div className="overflow-hidden pr-3 text-ellipsis">{item.description}</div>
          <div className="num text-right">
            {item.quantity == null ? <span className="subtle">–</span> : item.quantity}
          </div>
          <div className="num text-right">
            {item.unit_price == null ? (
              <span className="subtle">–</span>
            ) : (
              `$${formatNumber(item.unit_price)}`
            )}
          </div>
          <div className="num text-right font-medium">${formatNumber(item.line_total)}</div>
        </div>
      ))}

      <div className="grid grid-cols-[1fr_90px] items-center bg-surface-pearl px-3 py-[9px] text-xs">
        <div className="text-[12px] uppercase tracking-[0.06em] text-ink-48">
          {items.length} {items.length === 1 ? 'line' : 'lines'} · sum
        </div>
        <div className="num text-right font-medium text-ink">${formatNumber(subtotalSum)}</div>
      </div>
    </div>
  )
}
