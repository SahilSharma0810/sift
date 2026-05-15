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
  const spec = REASON_SPECS[reason.type] as unknown as ReasonSpec<TriageReason>
  if (!spec) return null

  const Icon = spec.icon
  const { Title, Detail } = spec

  return (
    <div className="reason" data-kind={reason.type}>
      <div className="reason-icon">
        <Icon />
      </div>
      <div className="reason-body">
        <div className="reason-title">
          <Title reason={reason} />
        </div>
        <div className="reason-detail">
          <Detail reason={reason} ctx={ctx} />
        </div>
        {spec.actions.length > 0 && (
          <div className="reason-actions">
            {spec.actions.map((action) => {
              const label =
                typeof action.label === 'function' ? action.label(reason) : action.label
              return (
                <Btn
                  key={label}
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
