import type { TaxBreakdownLine } from '@/types/generated/domain'
import { formatNumber } from '@/utils/format'

import { Icons } from './Icons'

export function TaxBreakdownTable({ rows }: { rows: TaxBreakdownLine[] }) {
  if (!rows || rows.length === 0) {
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
        <span>Single tax line on this invoice — no per-jurisdiction breakdown.</span>
      </div>
    )
  }

  const sum = rows.reduce((acc, r) => acc + (r.amount ?? 0), 0)

  return (
    <div className="card">
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 70px 90px',
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
        <div>Jurisdiction</div>
        <div style={{ textAlign: 'right' }}>Rate</div>
        <div style={{ textAlign: 'right' }}>Amount</div>
      </div>

      {rows.map((row, i) => (
        <div
          key={i}
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 70px 90px',
            alignItems: 'center',
            padding: '9px 12px',
            borderBottom: '1px solid var(--hairline-soft)',
            fontSize: 13,
            color: 'var(--ink-80)',
          }}
        >
          <div style={{ paddingRight: 12, overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {row.jurisdiction}
          </div>
          <div className="num" style={{ textAlign: 'right' }}>
            {row.rate == null ? <span className="subtle">—</span> : `${row.rate}%`}
          </div>
          <div className="num" style={{ textAlign: 'right', fontWeight: 500 }}>
            ${formatNumber(row.amount)}
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
          {rows.length} {rows.length === 1 ? 'jurisdiction' : 'jurisdictions'} · sum
        </div>
        <div
          className="num"
          style={{
            textAlign: 'right',
            fontWeight: 500,
            color: 'var(--ink)',
          }}
        >
          ${formatNumber(sum)}
        </div>
      </div>
    </div>
  )
}
