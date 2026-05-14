type Variant = 'confident' | 'needs_review' | 'likely_duplicate' | 'unprocessable'

const LABELS: Record<Variant, string> = {
  confident: 'Confident',
  needs_review: 'Needs review',
  likely_duplicate: 'Likely duplicate',
  unprocessable: 'Unprocessable',
}

export function TriagePill({ variant, pct }: { variant: Variant; pct?: number | null }) {
  return (
    <span className="pill" data-variant={variant}>
      <span className="pill-dot" />
      <span>{LABELS[variant]}</span>
      {pct != null && variant !== 'unprocessable' && (
        <span className="pill-pct">{Math.round(pct * 100)}%</span>
      )}
    </span>
  )
}
