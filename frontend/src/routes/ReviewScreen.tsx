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
 * Stub for Day 1.
 */
import { useParams } from 'react-router-dom'

export function ReviewScreen() {
  const { id } = useParams<{ id: string }>()
  return (
    <div className="container py-8">
      <h1 className="text-2xl font-semibold">Invoice {id}</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Review screen — PDF on the left, fields on the right. (Day 1 stub.)
      </p>
    </div>
  )
}
