import { cn } from '@/utils/cn'

type Variant = 'confident' | 'needs_review' | 'likely_duplicate' | 'unprocessable'

const LABELS: Record<Variant, string> = {
  confident: 'Confident',
  needs_review: 'Needs review',
  likely_duplicate: 'Likely duplicate',
  unprocessable: 'Unprocessable',
}

const COLORS: Record<Variant, string> = {
  confident: 'bg-triage-confident/15 text-triage-confident',
  needs_review: 'bg-triage-needs-review/15 text-triage-needs-review',
  likely_duplicate: 'bg-triage-duplicate/15 text-triage-duplicate',
  unprocessable: 'bg-triage-unprocessable/15 text-triage-unprocessable',
}

export function TriagePill({ variant }: { variant: Variant }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        COLORS[variant]
      )}
    >
      {LABELS[variant]}
    </span>
  )
}
