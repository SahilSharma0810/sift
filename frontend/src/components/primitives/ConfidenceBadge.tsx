import { cn } from '@/utils/cn'

export function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const tone =
    pct >= 85
      ? 'text-triage-confident'
      : pct >= 60
        ? 'text-triage-needs-review'
        : 'text-destructive'
  return (
    <span className={cn('inline-flex items-center text-xs tabular-nums', tone)}>
      {pct}%
    </span>
  )
}
