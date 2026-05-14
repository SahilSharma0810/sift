import type { CSSProperties } from 'react'

export function ConfidenceBadge({ value }: { value: number | null | undefined }) {
  if (value == null || value === 0) {
    return (
      <span
        className="conf"
        data-tone="low"
        style={{ '--w': '0%' } as CSSProperties}
      >
        —
      </span>
    )
  }
  const pct = Math.round(value * 100)
  const tone = pct >= 85 ? 'high' : pct >= 60 ? 'mid' : 'low'
  return (
    <span
      className="conf"
      data-tone={tone}
      style={{ '--w': `${pct}%` } as CSSProperties}
      title={`Composite confidence: ${pct}%`}
    >
      <span className="conf-bar">
        <span className="conf-bar-fill" />
      </span>
      <span>{pct}</span>
    </span>
  )
}
