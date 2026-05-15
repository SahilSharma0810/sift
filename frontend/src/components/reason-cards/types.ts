import type { ReactNode } from 'react'

import type { Icons } from '@/components/primitives/Icons'
import type { InvoiceOut, TriageReason } from '@/types/generated/domain'

export interface ReasonActionContext {
  invoiceId: string
  reasons: TriageReason[]
  byId: Record<string, InvoiceOut>

  confirm: () => void
  dismissDup: (againstId: string) => void
  markUnp: () => void
  retry: (opts?: { forceTier?: string }) => void

  setEditingField: (field: string | null) => void
  setManualMode: (on: boolean) => void
  navigate: (to: string) => void
}

type IconComponent = (typeof Icons)[keyof typeof Icons]

interface ReasonActionSpec<R extends TriageReason> {
  label: string | ((reason: R) => string)
  icon: IconComponent
  variant?: 'primary' | 'danger' | 'ghost'
  handler: (ctx: ReasonActionContext, reason: R) => void
}

export interface ReasonSpec<R extends TriageReason> {
  icon: IconComponent
  Title: (props: { reason: R }) => ReactNode
  Detail: (props: { reason: R; ctx: ReasonActionContext }) => ReactNode
  actions: ReasonActionSpec<R>[]
}

export type ReasonRegistry = {
  [T in TriageReason['type']]: ReasonSpec<Extract<TriageReason, { type: T }>>
}
