/**
 * Reason-card registry types.
 *
 * The Triage Reason discriminated union from the backend (TriageReason in
 * generated/domain) drives the review UI. Each reason type maps to one
 * registry entry that owns:
 *   - how to render the card (icon, title, detail)
 *   - what clerk actions are allowed
 *   - what each action does (mutation, navigation, or local state change)
 *
 * Adding a new TriageReason variant is one new registry entry. No two-file
 * dance between render and dispatch.
 */
import type { ReactNode } from 'react'

import type { Icons } from '@/components/primitives/Icons'
import type { InvoiceOut, TriageReason } from '@/types/generated/domain'

/**
 * The handle each action gets. The full reason list is passed too so an
 * action can cross-reference its peers (e.g. dismiss-duplicate reads the
 * sibling DuplicateOfReason's invoice_id when wired from elsewhere).
 */
export interface ReasonActionContext {
  invoiceId: string
  reasons: TriageReason[]
  byId: Record<string, InvoiceOut>
  // mutations
  confirm: () => void
  dismissDup: (againstId: string) => void
  markUnp: () => void
  retry: (opts?: { forceTier?: string }) => void
  // local state setters
  setEditingField: (field: string | null) => void
  setManualMode: (on: boolean) => void
  navigate: (to: string) => void
}

type IconComponent = (typeof Icons)[keyof typeof Icons]

/**
 * One button on a reason card. Bound to its reason's specific type via the
 * generic `R` so the handler / label can read reason-specific fields
 * without a cast.
 */
export interface ReasonActionSpec<R extends TriageReason> {
  label: string | ((reason: R) => string)
  icon: IconComponent
  variant?: 'primary' | 'danger' | 'ghost'
  handler: (ctx: ReasonActionContext, reason: R) => void
}

/**
 * One registry entry: how to render a reason of type `R` plus the actions
 * a clerk can take on it.
 */
export interface ReasonSpec<R extends TriageReason> {
  icon: IconComponent
  renderTitle: (reason: R) => ReactNode
  renderDetail: (reason: R, ctx: ReasonActionContext) => ReactNode
  actions: ReasonActionSpec<R>[]
}

/**
 * The full registry, indexed by reason.type. TypeScript narrows each entry
 * to the exact discriminated-union variant so spec bodies are fully typed.
 */
export type ReasonRegistry = {
  [T in TriageReason['type']]: ReasonSpec<Extract<TriageReason, { type: T }>>
}
