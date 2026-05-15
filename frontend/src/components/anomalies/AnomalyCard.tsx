import type { AnomalyOut } from '@/types/generated/domain'
import { Sparkline } from '@/components/anomalies/Sparkline'
import { TypePill } from '@/components/anomalies/TypePill'

type AnomalyCardProps = {
  anomaly: AnomalyOut
  selected: boolean
  onToggle: () => void
  onAcknowledge: () => void
  onInvestigate: () => void
}

const SEVERITY_CLASS: Record<string, string> = {
  high: 'text-anomaly-severity-high border-anomaly-severity-high',
  medium: 'text-aside-review border-aside-review',
  low: 'text-ink-48 border-ink-48',
}

export function AnomalyCard({
  anomaly,
  selected,
  onToggle,
  onAcknowledge,
  onInvestigate,
}: AnomalyCardProps) {
  const isAck = anomaly.status === 'acknowledged'

  return (
    <div
      className={[
        'flex flex-col border bg-surface transition-colors duration-100',
        selected ? 'border-action' : 'border-hairline',
        isAck ? 'opacity-70' : 'opacity-100',
      ].join(' ')}
    >
      <header className="flex items-center gap-2.5 border-b border-hairline-soft px-3.5 py-3">
        <TypePill type={anomaly.type} />
        <span
          className={[
            'font-mono text-[11.5px] font-medium px-1.5 py-px border',
            SEVERITY_CLASS[anomaly.severity] ?? '',
          ].join(' ')}
        >
          {anomaly.z_score > 20 ? '≥20σ' : `${anomaly.z_score.toFixed(1)}σ`}
        </span>
        <span className="ml-auto flex items-center gap-1.5">
          {isAck && (
            <span className="font-mono text-[11px] text-aside-confident">
              acknowledged
            </span>
          )}
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            aria-label="Select anomaly"
            className="m-0 cursor-pointer accent-action"
          />
        </span>
      </header>

      <div className="flex-1 p-3.5">
        <div className="flex items-center gap-1.5">
          <span className="text-[13.5px] font-medium text-ink">{anomaly.vendor}</span>
          <span className="ml-auto font-mono text-[11.5px] text-ink-48">
            {new Date(anomaly.detected_at).toLocaleString(undefined, {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </div>
        <div className="mt-1.5 font-mono text-[18px] font-semibold tracking-[-0.005em] text-ink">
          {anomaly.headline}
        </div>
        <div className="mt-1 text-[12.5px] leading-[1.5] text-ink-60">
          {anomaly.sub}
        </div>

        <div className="mt-3.5">
          <Sparkline data={anomaly.history} avg={anomaly.avg} variant="bars" />
        </div>
      </div>

      <footer className="flex gap-1.5 border-t border-hairline-soft bg-surface-recess px-3.5 py-2.5">
        {!isAck && (
          <button
            type="button"
            onClick={onAcknowledge}
            className="border border-hairline bg-surface px-2.5 py-1 text-[12px] font-medium text-ink-80 transition-colors hover:border-action hover:text-action"
          >
            Acknowledge
          </button>
        )}
        <button
          type="button"
          onClick={onInvestigate}
          className="border border-transparent px-2.5 py-1 text-[12px] font-medium text-ink-60 transition-colors hover:text-ink"
        >
          Investigate
        </button>
      </footer>
    </div>
  )
}
