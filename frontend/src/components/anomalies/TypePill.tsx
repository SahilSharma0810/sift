import type { ReactNode } from 'react'

type TypeKey = 'amount' | 'frequency' | 'terms_changed' | 'new_line_item'

type PillMeta = {
  label: string
  classes: string
}

const META: Record<TypeKey, PillMeta> = {
  amount: {
    label: 'Amount',
    classes: 'text-anomaly-amount-fg bg-anomaly-amount-bg border-anomaly-amount-ring',
  },
  frequency: {
    label: 'Frequency',
    classes:
      'text-anomaly-frequency-fg bg-anomaly-frequency-bg border-anomaly-frequency-ring',
  },
  terms_changed: {
    label: 'Terms',
    classes:
      'text-aside-duplicate bg-aside-duplicate-tint border-aside-duplicate-ring',
  },
  new_line_item: {
    label: 'New line',
    classes:
      'text-aside-review bg-aside-review-tint border-aside-review-ring',
  },
}

export function TypePill({ type, icon }: { type: TypeKey; icon?: ReactNode }) {
  const meta = META[type] ?? META.amount
  return (
    <span
      className={[
        'inline-flex items-center gap-1.5 border px-2 py-0.5 text-[11.5px] font-medium tracking-[-0.005em]',
        meta.classes,
      ].join(' ')}
    >
      {icon}
      <span>{meta.label}</span>
    </span>
  )
}
