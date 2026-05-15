import { Icons } from '@/components/primitives/Icons'
import type {
  AnomalyReason,
  DuplicateOfReason,
  ExtractionFailedReason,
  LowConfidenceReason,
  MathFailsReason,
  MissingFieldReason,
  UnseenVendorReason,
} from '@/types/generated/domain'
import { formatNumber } from '@/utils/format'

import type { ReasonRegistry } from './types'

const MathFailsDetail = ({ reason: r }: { reason: MathFailsReason }) => (
  <>
    <span className="mono-snip">
      subtotal {formatNumber(r.subtotal)} + tax {formatNumber(r.tax)} ={' '}
      {formatNumber(r.subtotal + r.tax)}
    </span>{' '}
    but invoice says total{' '}
    <span className="mono-snip">{formatNumber(r.total)}</span>; off by{' '}
    <span className="mono-snip">{r.delta.toFixed(2)}</span>.
  </>
)

const DuplicateOfDetail = ({
  reason: r,
  ctx,
}: {
  reason: DuplicateOfReason
  ctx: { byId: Record<string, { current_extraction?: { extracted_fields?: Record<string, { value?: unknown }> } | null }> }
}) => {
  const orig = ctx.byId[r.invoice_id]
  const origFields = orig?.current_extraction?.extracted_fields
  const origLabel = orig
    ? `${origFields?.invoice_number?.value ?? '–'} (${origFields?.vendor_name?.value ?? '–'})`
    : r.invoice_id
  return (
    <>
      {Math.round(r.similarity * 100)}% match against{' '}
      <span className="mono-snip">{String(origLabel)}</span>; matched on{' '}
      <span className="mono-snip">{r.match_method}</span>.
    </>
  )
}

const LowConfidenceDetail = ({ reason: r }: { reason: LowConfidenceReason }) => (
  <>
    Composite confidence{' '}
    <span className="mono-snip">{Math.round(r.score * 100)}%</span>: {r.reason}.
  </>
)

const AnomalyDetail = ({ reason: r }: { reason: AnomalyReason }) => (
  <>
    <span className="mono-snip">${formatNumber(r.vendor_mean)}</span> is the rolling
    average; this extraction is{' '}
    <span className="mono-snip">{r.z_score.toFixed(1)}σ</span> away (σ ={' '}
    <span className="mono-snip">${formatNumber(r.vendor_std)}</span>).
  </>
)

const ExtractionFailedDetail = ({ reason: r }: { reason: ExtractionFailedReason }) => (
  <>
    Failed at stage <span className="mono-snip">{r.stage}</span>: {r.detail}.
  </>
)

export const REASON_SPECS: ReasonRegistry = {
  math_fails: {
    icon: Icons.warn,
    Title: () => <>Math doesn't reconcile</>,
    Detail: MathFailsDetail,
    actions: [
      {
        label: 'Edit total',
        icon: Icons.pen,
        handler: (ctx) => ctx.setEditingField('total'),
      },
      {
        label: 'Re-extract',
        icon: Icons.refresh,
        variant: 'ghost',
        handler: (ctx) => ctx.retry(),
      },
    ],
  },

  duplicate_of: {
    icon: Icons.copy,
    Title: () => <>Looks like a duplicate</>,
    Detail: DuplicateOfDetail,
    actions: [
      {
        label: 'Open original',
        icon: Icons.eye,
        handler: (ctx, r) =>
          ctx.navigate(`/duplicate-review/${ctx.invoiceId}?against=${r.invoice_id}`),
      },
      {
        label: 'Mark duplicate & dismiss',
        icon: Icons.x,
        variant: 'danger',
        handler: (ctx, r) => ctx.dismissDup(r.invoice_id),
      },
      {
        label: 'Not a duplicate',
        icon: Icons.x,
        variant: 'ghost',
        handler: (ctx, r) => ctx.dismissDup(r.invoice_id),
      },
    ],
  },

  low_confidence: {
    icon: Icons.alert,
    Title: ({ reason: r }: { reason: LowConfidenceReason }) => (
      <>Low confidence on {r.field.replace('_', ' ')}</>
    ),
    Detail: LowConfidenceDetail,
    actions: [
      {
        label: (r) => `Fix ${r.field.replace('_', ' ')}`,
        icon: Icons.pen,
        handler: (ctx, r) => ctx.setEditingField(r.field),
      },
      {
        label: 'Force Opus',
        icon: Icons.cascade,
        variant: 'ghost',
        handler: (ctx) => ctx.retry({ forceTier: 'claude-opus-4-7' }),
      },
    ],
  },

  missing_field: {
    icon: Icons.alert,
    Title: ({ reason: r }: { reason: MissingFieldReason }) => (
      <>Missing {r.field.replace('_', ' ')}</>
    ),
    Detail: () => <>Required field is empty in the extraction.</>,
    actions: [
      {
        label: 'Add value',
        icon: Icons.plus,
        handler: (ctx, r) => ctx.setEditingField(r.field),
      },
    ],
  },

  anomaly: {
    icon: Icons.spark,
    Title: ({ reason: r }: { reason: AnomalyReason }) => (
      <>Unusual {r.field} for this vendor</>
    ),
    Detail: AnomalyDetail,
    actions: [
      {
        label: 'See vendor history',
        icon: Icons.history,
        handler: () => undefined,
      },
      {
        label: 'This is expected',
        icon: Icons.history,
        variant: 'ghost',
        handler: () => undefined,
      },
    ],
  },

  unseen_vendor: {
    icon: Icons.vendor,
    Title: ({ reason: r }: { reason: UnseenVendorReason }) => (
      <>First invoice from {r.vendor_name}</>
    ),
    Detail: () => (
      <>
        No vendor history yet. Confidence scores fall back to the cold-start default of
        0.85. Confirming this extraction will seed the vendor memory.
      </>
    ),
    actions: [],
  },

  extraction_failed: {
    icon: Icons.lock,
    Title: () => <>Couldn't read this PDF</>,
    Detail: ExtractionFailedDetail,
    actions: [
      {
        label: 'Manually enter fields',
        icon: Icons.pen,
        handler: (ctx) => ctx.setManualMode(true),
      },
      {
        label: 'Retry',
        icon: Icons.refresh,
        variant: 'ghost',
        handler: (ctx) => ctx.retry(),
      },
      {
        label: 'Mark unprocessable',
        icon: Icons.x,
        variant: 'ghost',
        handler: (ctx) => ctx.markUnp(),
      },
    ],
  },
}
