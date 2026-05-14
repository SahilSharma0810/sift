import type { InvoiceOut, TriageReason } from '@/types/generated/domain'
import { formatNumber } from '@/utils/format'

import { Btn } from './Btn'
import { Icons } from './Icons'

export type ReasonAction =
  | 'edit_total'
  | 'edit_field'
  | 'add_field'
  | 'retry'
  | 'view_dup'
  | 'dismiss_dup'
  | 'not_dup'
  | 'force_opus'
  | 'see_history'
  | 'expected'
  | 'manual_entry'
  | 'mark_unprocessable'

export function ReasonCard({
  reason,
  byId,
  onAction,
}: {
  reason: TriageReason
  byId?: Record<string, InvoiceOut>
  onAction?: (action: ReasonAction, payload?: string) => void
}) {
  switch (reason.type) {
    case 'math_fails': {
      const r = reason
      return (
        <div className="reason" data-kind="math_fails">
          <div className="reason-icon">
            <Icons.warn />
          </div>
          <div className="reason-body">
            <div className="reason-title">Math doesn't reconcile</div>
            <div className="reason-detail">
              <span className="mono-snip">
                subtotal {formatNumber(r.subtotal)} + tax {formatNumber(r.tax)} ={' '}
                {formatNumber(r.subtotal + r.tax)}
              </span>{' '}
              but invoice says total <span className="mono-snip">{formatNumber(r.total)}</span>{' '}
              — off by <span className="mono-snip">{r.delta.toFixed(2)}</span>.
            </div>
            <div className="reason-actions">
              <Btn size="sm" icon={Icons.pen} onClick={() => onAction?.('edit_total')}>
                Edit total
              </Btn>
              <Btn
                size="sm"
                variant="ghost"
                icon={Icons.refresh}
                onClick={() => onAction?.('retry')}
              >
                Re-extract
              </Btn>
            </div>
          </div>
        </div>
      )
    }

    case 'duplicate_of': {
      const r = reason
      const orig = byId?.[r.invoice_id]
      const origFields = orig?.current_extraction?.extracted_fields
      const origLabel = orig
        ? `${origFields?.invoice_number?.value ?? '—'} (${origFields?.vendor_name?.value ?? '—'})`
        : r.invoice_id
      return (
        <div className="reason" data-kind="duplicate_of">
          <div className="reason-icon">
            <Icons.copy />
          </div>
          <div className="reason-body">
            <div className="reason-title">Looks like a duplicate</div>
            <div className="reason-detail">
              {Math.round(r.similarity * 100)}% match against{' '}
              <span className="mono-snip">{origLabel}</span> — matched on{' '}
              <span className="mono-snip">{r.match_method}</span>.
            </div>
            <div className="reason-actions">
              <Btn
                size="sm"
                icon={Icons.eye}
                onClick={() => onAction?.('view_dup', r.invoice_id)}
              >
                Open original
              </Btn>
              <Btn
                size="sm"
                variant="danger"
                icon={Icons.x}
                onClick={() => onAction?.('dismiss_dup')}
              >
                Mark duplicate & dismiss
              </Btn>
              <Btn size="sm" variant="ghost" onClick={() => onAction?.('not_dup')}>
                Not a duplicate
              </Btn>
            </div>
          </div>
        </div>
      )
    }

    case 'low_confidence': {
      const r = reason
      return (
        <div className="reason" data-kind="low_confidence">
          <div className="reason-icon">
            <Icons.alert />
          </div>
          <div className="reason-body">
            <div className="reason-title">
              Low confidence on {r.field.replace('_', ' ')}
            </div>
            <div className="reason-detail">
              Composite confidence{' '}
              <span className="mono-snip">{Math.round(r.score * 100)}%</span> — {r.reason}.
            </div>
            <div className="reason-actions">
              <Btn
                size="sm"
                icon={Icons.pen}
                onClick={() => onAction?.('edit_field', r.field)}
              >
                Fix {r.field.replace('_', ' ')}
              </Btn>
              <Btn
                size="sm"
                variant="ghost"
                icon={Icons.cascade}
                onClick={() => onAction?.('force_opus')}
              >
                Force Opus
              </Btn>
            </div>
          </div>
        </div>
      )
    }

    case 'missing_field': {
      const r = reason
      return (
        <div className="reason" data-kind="missing_field">
          <div className="reason-icon">
            <Icons.alert />
          </div>
          <div className="reason-body">
            <div className="reason-title">Missing {r.field.replace('_', ' ')}</div>
            <div className="reason-detail">Required field is empty in the extraction.</div>
            <div className="reason-actions">
              <Btn
                size="sm"
                icon={Icons.plus}
                onClick={() => onAction?.('add_field', r.field)}
              >
                Add value
              </Btn>
            </div>
          </div>
        </div>
      )
    }

    case 'anomaly': {
      const r = reason
      return (
        <div className="reason" data-kind="anomaly">
          <div className="reason-icon">
            <Icons.spark />
          </div>
          <div className="reason-body">
            <div className="reason-title">Unusual {r.field} for this vendor</div>
            <div className="reason-detail">
              <span className="mono-snip">${formatNumber(r.vendor_mean)}</span> is the rolling
              average; this extraction is{' '}
              <span className="mono-snip">{r.z_score.toFixed(1)}σ</span> away (σ ={' '}
              <span className="mono-snip">${formatNumber(r.vendor_std)}</span>).
            </div>
            <div className="reason-actions">
              <Btn
                size="sm"
                icon={Icons.history}
                onClick={() => onAction?.('see_history')}
              >
                See vendor history
              </Btn>
              <Btn size="sm" variant="ghost" onClick={() => onAction?.('expected')}>
                This is expected
              </Btn>
            </div>
          </div>
        </div>
      )
    }

    case 'unseen_vendor': {
      const r = reason
      return (
        <div className="reason" data-kind="unseen_vendor">
          <div className="reason-icon">
            <Icons.vendor />
          </div>
          <div className="reason-body">
            <div className="reason-title">First invoice from {r.vendor_name}</div>
            <div className="reason-detail">
              No vendor history yet — confidence scores fall back to the cold-start default
              of 0.85. Confirming this extraction will seed the vendor memory.
            </div>
          </div>
        </div>
      )
    }

    case 'extraction_failed': {
      const r = reason
      return (
        <div className="reason" data-kind="extraction_failed">
          <div className="reason-icon">
            <Icons.lock />
          </div>
          <div className="reason-body">
            <div className="reason-title">Couldn't read this PDF</div>
            <div className="reason-detail">
              Failed at stage <span className="mono-snip">{r.stage}</span>: {r.detail}.
            </div>
            <div className="reason-actions">
              <Btn
                size="sm"
                icon={Icons.pen}
                onClick={() => onAction?.('manual_entry')}
              >
                Manually enter fields
              </Btn>
              <Btn
                size="sm"
                variant="ghost"
                icon={Icons.refresh}
                onClick={() => onAction?.('retry')}
              >
                Retry
              </Btn>
              <Btn
                size="sm"
                variant="ghost"
                onClick={() => onAction?.('mark_unprocessable')}
              >
                Mark unprocessable
              </Btn>
            </div>
          </div>
        </div>
      )
    }

    default:
      return null
  }
}
