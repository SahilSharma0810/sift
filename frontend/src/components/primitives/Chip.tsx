import { Icons } from './Icons'

const OP_DISPLAY: Record<string, string> = {
  eq: '=',
  neq: '≠',
  gt: '>',
  gte: '≥',
  lt: '<',
  lte: '≤',
  in: 'in',
  between: 'between',
  contains: 'contains',
  fts_matches: 'matches',
}

type ChipValue = string | number | boolean | Array<string | number> | null

export function Chip({
  field,
  op,
  value,
  onRemove,
}: {
  field: string
  op: string
  value: ChipValue
  onRemove?: () => void
}) {
  return (
    <span className="chip">
      <span className="chip-key">{field}</span>
      <span className="chip-op">{OP_DISPLAY[op] ?? op}</span>
      <span>{Array.isArray(value) ? value.join(' – ') : String(value)}</span>
      {onRemove && (
        <button className="chip-x" aria-label="Remove filter" onClick={onRemove}>
          <Icons.x />
        </button>
      )}
    </span>
  )
}
