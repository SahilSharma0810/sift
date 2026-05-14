import type { CSSProperties } from 'react'

import type { ReviewStatus } from '@/types/generated/domain'

const META: Record<ReviewStatus, { label: string; color: string; bg: string }> = {
  pending: {
    label: 'Pending',
    color: 'var(--ink-60)',
    bg: 'var(--surface-recess)',
  },
  confirmed: {
    label: 'Confirmed',
    color: 'var(--triage-confident)',
    bg: 'var(--triage-confident-bg)',
  },
  dismissed_duplicate: {
    label: 'Dismissed',
    color: 'var(--ink-48)',
    bg: 'var(--surface-recess)',
  },
  unprocessable: {
    label: 'Unprocessable',
    color: 'var(--triage-unprocessable)',
    bg: 'var(--surface-recess)',
  },
}

export function StatusBadge({ status }: { status: ReviewStatus }) {
  const m = META[status] ?? META.pending
  const style: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    padding: '2px 7px',
    fontSize: 11.5,
    color: m.color,
    background: m.bg,
    border: '1px solid var(--hairline)',
    fontFamily: 'var(--font-mono)',
  }
  return <span style={style}>{m.label}</span>
}
