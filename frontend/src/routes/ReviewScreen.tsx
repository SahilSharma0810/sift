/**
 * ReviewScreen — locked design per PLAN.md "UX surface > ReviewScreen":
 *
 * - 2-column: PDF viewer (PDF.js) on left, fields panel on right
 * - Active field highlights in panel AND on PDF (bbox overlay, zoom-to-fit
 *   for small bboxes)
 * - Tab/Shift-Tab walks fields; E/Enter enters edit mode; Esc cancels; Enter
 *   commits
 * - FieldRow: label · editable value · ConfidenceBadge · SourceBadge
 * - Provenance hover on a field reveals: extracted by [model], corrected
 *   by clerk [date], auto-applied from vendor memory
 * - ReasonCardStack at top of fields panel — dispatch on reason.type
 * - Action bar: C Confirm · D Dismiss · U Mark unprocessable
 * - Failure-mode UX (ADR-0006): when reasons include `extraction_failed`,
 *   fields panel renders ExtractionFailedCard with Retry / Mark unprocessable
 *   / Manually enter fields buttons
 *
 * Day-1 implementation lands the 2-col PDF + read-only field rows. Editing,
 * keyboard nav, bbox-follow, and action bar come online in Day 2.
 */
import { useParams } from 'react-router-dom'

import { FieldRow } from '@/components/primitives/FieldRow'
import { PdfViewer } from '@/components/primitives/PdfViewer'
import { TriagePill } from '@/components/primitives/TriagePill'
import { useInvoiceQuery } from '@/state/invoices'

type TriagePillVariant =
  | 'confident'
  | 'needs_review'
  | 'likely_duplicate'
  | 'unprocessable'

const FIELD_LABELS: { key: string; label: string }[] = [
  { key: 'vendor_name', label: 'Vendor' },
  { key: 'invoice_number', label: 'Invoice #' },
  { key: 'invoice_date', label: 'Date' },
  { key: 'subtotal', label: 'Subtotal' },
  { key: 'tax', label: 'Tax' },
  { key: 'total', label: 'Total' },
  { key: 'currency', label: 'Currency' },
]

export function ReviewScreen() {
  const { id } = useParams<{ id: string }>()
  const { data: invoice, isLoading } = useInvoiceQuery(id)

  if (isLoading || !invoice) {
    return <div className="container py-8 text-muted-foreground">Loading…</div>
  }

  const ext = invoice.current_extraction
  const fields = ext?.extracted_fields ?? {}
  const pdfSrc = `/api/invoices/${invoice.id}/file`

  const variant: TriagePillVariant =
    invoice.review_status === 'unprocessable'
      ? 'unprocessable'
      : ((ext?.predicted_triage_state ?? 'needs_review') as TriagePillVariant)

  return (
    <div className="grid h-full grid-cols-1 gap-4 overflow-hidden p-4 lg:grid-cols-2">
      <div className="overflow-y-auto">
        <PdfViewer src={pdfSrc} />
      </div>
      <div className="overflow-y-auto">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">
            {String(fields.vendor_name?.value ?? 'Invoice')}
          </h2>
          {ext && <TriagePill variant={variant} />}
        </div>
        <div className="mt-4 rounded-lg border bg-card p-4">
          {FIELD_LABELS.map(({ key, label }) => (
            <FieldRow key={key} label={label} field={fields[key] ?? null} />
          ))}
        </div>
        {ext?.predicted_triage_reasons.length ? (
          <div className="mt-4 rounded-lg border bg-card p-4">
            <h3 className="text-sm font-medium">Why</h3>
            <ul className="mt-2 list-disc pl-5 text-sm text-muted-foreground">
              {ext.predicted_triage_reasons.map((r, i) => (
                <li key={i}>{r.type}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  )
}
