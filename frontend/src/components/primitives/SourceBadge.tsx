import type { ComponentType } from 'react'

import { Icons } from './Icons'

type SourceKind = 'haiku' | 'sonnet' | 'memory' | 'manual'

const META: Record<SourceKind, { label: string; Icon: ComponentType }> = {
  haiku: { label: 'Haiku', Icon: Icons.bot },
  sonnet: { label: 'Sonnet', Icon: Icons.spark },
  memory: { label: 'Vendor memory', Icon: Icons.brain },
  manual: { label: 'Manual', Icon: Icons.pen },
}

function pickKind(rawSource: string): SourceKind {

  const s = rawSource.toLowerCase()
  if (s.includes('memory-applied') || s === 'memory') return 'memory'
  if (s.includes('manual')) return 'manual'
  if (s.includes('opus')) return 'sonnet'
  if (s.includes('sonnet') || s.includes('claude-vision') || s.includes('vision')) return 'sonnet'
  return 'haiku'
}

export function SourceBadge({ source }: { source: string }) {
  const kind = pickKind(source)
  const { Icon, label } = META[kind]
  return (
    <span className="source" data-kind={kind} title={`Value from ${label}`}>
      <Icon />
      <span>{label}</span>
    </span>
  )
}
