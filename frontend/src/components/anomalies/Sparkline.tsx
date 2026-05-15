import type { AnomalyHistoryPoint } from '@/types/generated/domain'

type SparklineProps = {
  data: AnomalyHistoryPoint[]
  avg: number
  variant: 'bars' | 'line'
}

const W = 320
const H = 80
const PAD = 6

export function Sparkline({ data, avg, variant }: SparklineProps) {
  if (data.length === 0) {
    return (
      <div className="text-[11px] text-ink-48 italic">No vendor history yet.</div>
    )
  }

  const values = data.map((d) => d.value)
  const max = Math.max(...values, avg)
  const min = 0
  const xStep = data.length === 1 ? 0 : (W - PAD * 2) / (data.length - 1)
  const yFor = (v: number) =>
    H - PAD - ((v - min) / Math.max(max - min, 1)) * (H - PAD * 2)

  return (
    <div>
      <svg
        width={W}
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        className="block w-full max-w-[320px]"
      >
        <line
          x1={PAD}
          y1={yFor(avg)}
          x2={W - PAD}
          y2={yFor(avg)}
          stroke="var(--ink-48)"
          strokeWidth="1"
          strokeDasharray="2 3"
          opacity="0.55"
        />
        <text
          x={W - PAD - 2}
          y={yFor(avg) - 4}
          textAnchor="end"
          fontFamily="var(--font-mono)"
          fontSize="9"
          fill="var(--ink-60)"
        >
          avg
        </text>

        {variant === 'bars'
          ? data.map((d, i) => {
              const x = PAD + i * xStep
              const barW = Math.max(6, xStep - 4)
              const y = yFor(d.value)
              return (
                <rect
                  key={i}
                  x={x - barW / 2}
                  y={y}
                  width={barW}
                  height={H - PAD - y}
                  fill={d.current ? 'var(--action)' : 'var(--ink-60)'}
                  opacity={d.current ? 1 : 0.35}
                />
              )
            })
          : (
              <>
                <polyline
                  fill="none"
                  stroke="var(--ink-60)"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity="0.5"
                  points={data
                    .map((d, i) => `${PAD + i * xStep},${yFor(d.value)}`)
                    .join(' ')}
                />
                {data.map((d, i) => (
                  <circle
                    key={i}
                    cx={PAD + i * xStep}
                    cy={yFor(d.value)}
                    r={d.current ? 5 : 2.5}
                    fill={d.current ? 'var(--action)' : 'var(--ink-60)'}
                    opacity={d.current ? 1 : 0.6}
                  />
                ))}
              </>
            )}
      </svg>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-ink-48">
        <span>12 invoices ago</span>
        <span>now</span>
      </div>
    </div>
  )
}
