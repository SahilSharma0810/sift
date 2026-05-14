import type { CSSProperties, ComponentType } from 'react'

import type { TriageReason } from '@/types/generated/domain'

import { Icons } from './Icons'

type ChipMeta = { Icon: ComponentType; label: string; tone: Tone }
type Tone = 'warn' | 'dup' | 'anom' | 'fail' | 'neutral'

function metaForReason(reason: TriageReason): ChipMeta | null {
  switch (reason.type) {
    case 'math_fails':
      return {
        Icon: Icons.warn,
        label: `off $${reason.delta?.toFixed(2) ?? ''}`,
        tone: 'warn',
      }
    case 'duplicate_of':
      return { Icon: Icons.copy, label: 'duplicate match', tone: 'dup' }
    case 'low_confidence':
      return { Icon: Icons.alert, label: `low conf · ${reason.field}`, tone: 'warn' }
    case 'missing_field':
      return { Icon: Icons.alert, label: `missing ${reason.field}`, tone: 'warn' }
    case 'anomaly':
      return {
        Icon: Icons.spark,
        label: `${reason.z_score?.toFixed(1)}σ anomaly`,
        tone: 'anom',
      }
    case 'unseen_vendor':
      return { Icon: Icons.vendor, label: 'first invoice', tone: 'neutral' }
    case 'extraction_failed':
      return { Icon: Icons.lock, label: reason.stage, tone: 'fail' }
    default:
      return null
  }
}

const COLORS: Record<Tone, { bg: string; fg: string; bd: string }> = {
  warn: { bg: 'var(--triage-needs-review-bg)', fg: 'var(--triage-needs-review)', bd: '#ebd0a8' },
  dup: { bg: 'var(--triage-duplicate-bg)', fg: 'var(--triage-duplicate)', bd: '#c4d4ee' },
  anom: { bg: '#f3e9f9', fg: '#6b3b8c', bd: '#e2cae8' },
  fail: { bg: 'var(--surface-recess)', fg: 'var(--ink-60)', bd: 'var(--hairline)' },
  neutral: { bg: 'var(--surface-recess)', fg: 'var(--ink-80)', bd: 'var(--hairline)' },
}

export function WhyChip({ reason }: { reason: TriageReason }) {
  const m = metaForReason(reason)
  if (!m) return null
  const c = COLORS[m.tone]
  const style: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 5,
    padding: '2px 7px',
    background: c.bg,
    color: c.fg,
    border: `1px solid ${c.bd}`,
    fontSize: 11,
    fontFamily: 'var(--font-mono)',
    lineHeight: 1.5,
    whiteSpace: 'nowrap',
  }
  return (
    <span style={style}>
      <m.Icon />
      <span>{m.label}</span>
    </span>
  )
}
