import { Bot, Brain, PenLine, Sparkles } from 'lucide-react'

import { cn } from '@/utils/cn'

const ICONS: Record<string, { Icon: typeof Bot; label: string; tone: string }> = {
  haiku: { Icon: Bot, label: 'Haiku', tone: 'text-muted-foreground' },
  sonnet: { Icon: Sparkles, label: 'Sonnet', tone: 'text-muted-foreground' },
  opus: { Icon: Sparkles, label: 'Opus', tone: 'text-muted-foreground' },
  'memory-applied': { Icon: Brain, label: 'From vendor memory', tone: 'text-primary' },
  'manual-correction': { Icon: PenLine, label: 'Clerk-corrected', tone: 'text-primary' },
  'manual-entry': { Icon: PenLine, label: 'Manually entered', tone: 'text-primary' },
  'claude-vision': { Icon: Sparkles, label: 'Vision', tone: 'text-muted-foreground' },
}

function pickConfig(source: string) {
  // Service emits "pymupdf+<model>" — split and look up by the model token.
  if (source.startsWith('pymupdf+')) {
    const model = source.slice('pymupdf+'.length).toLowerCase()
    // model is like "claude-haiku-4-5" — match by inclusion
    for (const key of ['haiku', 'sonnet', 'opus']) {
      if (model.includes(key)) return ICONS[key]
    }
    return ICONS.haiku
  }
  return ICONS[source] ?? ICONS.haiku
}

export function SourceBadge({ source }: { source: string }) {
  const { Icon, label, tone } = pickConfig(source)
  return (
    <span
      title={label}
      className={cn('inline-flex items-center gap-1 text-xs', tone)}
    >
      <Icon className="h-3 w-3" />
      <span className="sr-only">{label}</span>
    </span>
  )
}
