import type { VendorMemory } from '@/types/generated/domain'
import { formatNumber } from '@/utils/format'

import { Icons } from './Icons'

export function VendorMemoryCard({
  memory,
  vendorName,
}: {
  memory: VendorMemory
  vendorName: string
}) {
  const seen = memory.stats?.total_seen ?? 0
  if (seen === 0) {
    return (
      <div className="card" style={{ padding: 14, fontSize: 12.5, color: 'var(--ink-80)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <Icons.vendor />
          <b>No history yet</b>
        </div>
        <div className="muted" style={{ fontSize: 12 }}>
          This is the first invoice from <b>{vendorName}</b>. Confirming will seed the
          vendor memory: format hints, typical totals, payment cadence.
        </div>
      </div>
    )
  }
  return (
    <div className="card">
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        borderBottom: '1px solid var(--hairline)',
      }}>
        <Cell label="Invoices seen" value={String(seen)} />
        <Cell label="Avg total" value={`$${formatNumber(memory.stats.avg_total)}`} right />
      </div>
      {memory.rules?.length > 0 && (
        <div style={{ padding: '10px 14px' }}>
          <div
            className="muted"
            style={{
              fontSize: 10.5,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              marginBottom: 6,
            }}
          >
            Patterns learned
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {memory.rules.map((r, i) => (
              <div key={i} style={{
                display: 'flex',
                gap: 8,
                alignItems: 'center',
                fontSize: 12.5,
              }}>
                <span style={{
                  width: 14,
                  height: 14,
                  background: '#f3e9f9',
                  color: '#6b3b8c',
                  display: 'grid',
                  placeItems: 'center',
                  flexShrink: 0,
                }}>
                  <Icons.brain />
                </span>
                <span style={{ color: 'var(--ink-80)' }}>
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
    <div style={{
      padding: '10px 14px',
      borderRight: !right ? '1px solid var(--hairline)' : 'none',
    }}>
      <div style={{
        fontSize: 10.5,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        color: 'var(--ink-48)',
      }}>{label}</div>
      <div style={{
        fontSize: 15,
        fontWeight: 500,
        color: 'var(--ink)',
        marginTop: 2,
        textAlign: right ? 'right' : 'left',
        fontFamily: 'var(--font-mono)',
      }}>{value}</div>
    </div>
  )
}
