import type { LineItem } from '@/types/generated/domain'
import { formatNumber } from '@/utils/format'

import { Icons } from './Icons'

export function LineItemsTable({ items }: { items: LineItem[] }) {
  if (!items || items.length === 0) {
    return (
      <div
        className="card"
        style={{
          padding: '12px 14px',
          fontSize: 12.5,
          color: 'var(--ink-60)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <Icons.layers />
        <span>No itemized line items on this invoice.</span>
      </div>
    )
  }

  const subtotalSum = items.reduce((acc, it) => acc + (it.line_total ?? 0), 0)

  return (
    <div className="card">
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 60px 90px 90px',
          alignItems: 'center',
          padding: '8px 12px',
          background: 'var(--paper-hi)',
          borderBottom: '1px solid var(--hairline)',
          fontSize: 10.5,
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          color: 'var(--ink-48)',
        }}
      >
        <div>Description</div>
        <div style={{ textAlign: 'right' }}>Qty</div>
        <div style={{ textAlign: 'right' }}>Unit</div>
        <div style={{ textAlign: 'right' }}>Total</div>
      </div>

      {items.map((item, i) => (
        <div
          key={i}
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 60px 90px 90px',
            alignItems: 'center',
            padding: '9px 12px',
            borderBottom: '1px solid var(--hairline-soft)',
            fontSize: 13,
            color: 'var(--ink-80)',
          }}
        >
          <div style={{ paddingRight: 12, overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {item.description}
          </div>
          <div className="num" style={{ textAlign: 'right' }}>
            {item.quantity == null ? <span className="subtle">—</span> : item.quantity}
          </div>
          <div className="num" style={{ textAlign: 'right' }}>
            {item.unit_price == null ? (
              <span className="subtle">—</span>
            ) : (
              `$${formatNumber(item.unit_price)}`
            )}
          </div>
          <div className="num" style={{ textAlign: 'right', fontWeight: 500 }}>
            ${formatNumber(item.line_total)}
          </div>
        </div>
      ))}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 90px',
          alignItems: 'center',
          padding: '9px 12px',
          background: 'var(--paper-hi)',
          fontSize: 12,
        }}
      >
        <div
          style={{
            color: 'var(--ink-48)',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            fontSize: 10.5,
          }}
        >
          {items.length} {items.length === 1 ? 'line' : 'lines'} · sum
        </div>
        <div
          className="num"
          style={{
            textAlign: 'right',
            fontWeight: 500,
            color: 'var(--ink)',
          }}
        >
          ${formatNumber(subtotalSum)}
        </div>
      </div>
    </div>
  )
}
