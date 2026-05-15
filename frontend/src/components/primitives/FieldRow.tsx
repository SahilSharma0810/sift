import { useEffect, useState } from 'react'

import type { ExtractedField } from '@/types/generated/domain'
import { formatNumber } from '@/utils/format'

import { Btn } from './Btn'
import { ConfidenceBadge } from './ConfidenceBadge'
import { Icons } from './Icons'
import { SourceBadge } from './SourceBadge'

type Props = {
  name: string
  label: string
  field: ExtractedField | null
  isActive?: boolean
  onActivate?: (name: string | null) => void
  isEditing?: boolean
  onEdit?: ((name: string | null) => void) | null
  onCommit?: (name: string, value: string) => void
}

export function FieldRow({
  name,
  label,
  field,
  isActive,
  onActivate,
  isEditing,
  onEdit,
  onCommit,
}: Props) {
  const initial = field?.value ?? ''
  const [draft, setDraft] = useState(String(initial))
  useEffect(() => {
    setDraft(String(field?.value ?? ''))
  }, [field?.value])

  const empty = field?.value == null || field?.value === ''
  const isNumeric =
    typeof field?.value === 'number' || /[\d-/]/.test(String(field?.value ?? ''))

  const isoFrom = field?.iso_from
  const isoTo = field?.iso_to
  const isoHint = isoFrom
    ? isoFrom === isoTo
      ? `Interpreted as ${isoFrom}`
      : `Interpreted as ${isoFrom} → ${isoTo}`
    : null

  const body = (
    <>
      <div className="field-label">{label}</div>
      <div className="field-value">
        {isEditing ? (
          <input
            ref={(el) => el?.focus()}
            className="field-edit-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => onCommit?.(name, draft)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.currentTarget.blur()
              }
              if (e.key === 'Escape') {
                setDraft(String(field?.value ?? ''))
                onEdit?.(null)
              }
            }}
          />
        ) : empty ? (
          <span className="v-empty">empty</span>
        ) : (
          <span
            className={isNumeric ? 'v-mono' : ''}
            title={isoHint ?? undefined}
          >
            {typeof field?.value === 'number' ? formatNumber(field.value) : field?.value}
          </span>
        )}
        {isoHint && !isEditing && !empty && (
          <span className="text-[11px] text-ink-48 font-mono whitespace-nowrap">
            {isoHint}
          </span>
        )}
      </div>
      <div className="field-meta">
        {field && <ConfidenceBadge value={field.confidence} />}
        {field && <SourceBadge source={field.source} />}
        {!isEditing && onEdit && (
          <Btn
            size="sm"
            variant="ghost"
            icon={Icons.pen}
            title="Edit field"
            onClick={(e) => {
              e.stopPropagation()
              onEdit(name)
            }}
          />
        )}
      </div>
    </>
  )

  if (!onActivate) {
    return (
      <div className="field" data-active={isActive ? 'true' : 'false'}>
        {body}
      </div>
    )
  }

  const activate = () => onActivate(name)
  const deactivate = () => onActivate(null)

  return (
    <div
      className="field"
      role="button"
      tabIndex={0}
      data-active={isActive ? 'true' : 'false'}
      onMouseEnter={activate}
      onMouseLeave={deactivate}
      onClick={activate}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          activate()
        }
      }}
    >
      {body}
    </div>
  )
}
