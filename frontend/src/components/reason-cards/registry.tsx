/**
 * Reason-card registry — single source of truth for "what does each
 * TriageReason render and what can a clerk do with it?"
 *
 * Each entry is fully typed against its specific reason variant via the
 * discriminated union. The renderTitle / renderDetail / action handler
 * bodies have access to the reason's narrowed fields without casts.
 */
import { Icons } from '@/components/primitives/Icons'
import { formatNumber } from '@/utils/format'

import type { ReasonRegistry } from './types'

export const REASON_SPECS: ReasonRegistry = {
  math_fails: {
    icon: Icons.warn,
    renderTitle: () => "Math doesn't reconcile",
    renderDetail: (r) => (
      <>
        <span className="mono-snip">
          subtotal {formatNumber(r.subtotal)} + tax {formatNumber(r.tax)} ={' '}
          {formatNumber(r.subtotal + r.tax)}
        </span>{' '}
        but invoice says total{' '}
        <span className="mono-snip">{formatNumber(r.total)}</span> — off by{' '}
        <span className="mono-snip">{r.delta.toFixed(2)}</span>.
      </>
    ),
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
    renderTitle: () => 'Looks like a duplicate',
    renderDetail: (r, ctx) => {
      const orig = ctx.byId[r.invoice_id]
      const origFields = orig?.current_extraction?.extracted_fields
      const origLabel = orig
        ? `${origFields?.invoice_number?.value ?? '—'} (${origFields?.vendor_name?.value ?? '—'})`
        : r.invoice_id
      return (
        <>
          {Math.round(r.similarity * 100)}% match against{' '}
          <span className="mono-snip">{origLabel}</span> — matched on{' '}
          <span className="mono-snip">{r.match_method}</span>.
        </>
      )
    },
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
    renderTitle: (r) => `Low confidence on ${r.field.replace('_', ' ')}`,
    renderDetail: (r) => (
      <>
        Composite confidence{' '}
        <span className="mono-snip">{Math.round(r.score * 100)}%</span> — {r.reason}.
      </>
    ),
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
    renderTitle: (r) => `Missing ${r.field.replace('_', ' ')}`,
    renderDetail: () => 'Required field is empty in the extraction.',
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
    renderTitle: (r) => `Unusual ${r.field} for this vendor`,
    renderDetail: (r) => (
      <>
        <span className="mono-snip">${formatNumber(r.vendor_mean)}</span> is the rolling
        average; this extraction is{' '}
        <span className="mono-snip">{r.z_score.toFixed(1)}σ</span> away (σ ={' '}
        <span className="mono-snip">${formatNumber(r.vendor_std)}</span>).
      </>
    ),
    actions: [
      {
        label: 'See vendor history',
        icon: Icons.history,
        // Vendor-history side panel is a planned route; today the action
        // is a no-op placeholder kept to preserve the demo button surface.
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
    renderTitle: (r) => `First invoice from ${r.vendor_name}`,
    renderDetail: () =>
      'No vendor history yet — confidence scores fall back to the cold-start default of 0.85. Confirming this extraction will seed the vendor memory.',
    actions: [],
  },

  extraction_failed: {
    icon: Icons.lock,
    renderTitle: () => "Couldn't read this PDF",
    renderDetail: (r) => (
      <>
        Failed at stage <span className="mono-snip">{r.stage}</span>: {r.detail}.
      </>
    ),
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
