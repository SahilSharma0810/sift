/**
 * ReasonCard — generic dispatch component that renders any TriageReason
 * through the REASON_SPECS registry.
 *
 * The card body (icon + title + detail) and the clerk action buttons all
 * come from one registry entry per reason type. Adding a new reason type
 * is one entry in registry.tsx — no edits here.
 */
import { Btn } from '@/components/primitives/Btn'
import type { TriageReason } from '@/types/generated/domain'

import { REASON_SPECS } from './registry'
import type { ReasonActionContext, ReasonSpec } from './types'

export function ReasonCard({
  reason,
  ctx,
}: {
  reason: TriageReason
  ctx: ReasonActionContext
}) {
  // The registry is keyed by reason.type; the cast is the dispatch step
  // that swaps the union for the narrowed variant. Inside the spec body
  // everything is fully typed.
  const spec = REASON_SPECS[reason.type] as unknown as ReasonSpec<TriageReason>
  if (!spec) return null

  const Icon = spec.icon

  return (
    <div className="reason" data-kind={reason.type}>
      <div className="reason-icon">
        <Icon />
      </div>
      <div className="reason-body">
        <div className="reason-title">{spec.renderTitle(reason)}</div>
        <div className="reason-detail">{spec.renderDetail(reason, ctx)}</div>
        {spec.actions.length > 0 && (
          <div className="reason-actions">
            {spec.actions.map((action, i) => {
              const label =
                typeof action.label === 'function' ? action.label(reason) : action.label
              return (
                <Btn
                  key={i}
                  size="sm"
                  variant={action.variant}
                  icon={action.icon}
                  onClick={() => action.handler(ctx, reason)}
                >
                  {label}
                </Btn>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
