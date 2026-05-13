import type { ExtractedField } from '@/types/generated/domain'

import { ConfidenceBadge } from './ConfidenceBadge'
import { SourceBadge } from './SourceBadge'

export function FieldRow({
  label,
  field,
}: {
  label: string
  field: ExtractedField | null | undefined
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b py-2 last:border-b-0">
      <div className="text-sm font-medium text-muted-foreground">{label}</div>
      <div className="flex items-center gap-3">
        <div className="text-sm tabular-nums">
          {field?.value !== null && field?.value !== undefined
            ? String(field.value)
            : '—'}
        </div>
        {field && <ConfidenceBadge value={field.confidence} />}
        {field && <SourceBadge source={field.source} />}
      </div>
    </div>
  )
}
