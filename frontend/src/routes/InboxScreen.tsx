/**
 * InboxScreen — locked design per PLAN.md "UX surface > InboxScreen":
 *
 * - shadcn Table, sticky header, virtualized rows when >100
 * - Columns: triage pill, vendor, invoice #, date, total, confidence pill,
 *   Why (typed reason cards on hover), review_status
 * - 4th pill style for `unprocessable` (ADR-0006)
 * - J/K row navigation, Space multi-select, Enter to open review
 * - Bulk actions toolbar with 10s client-side undo on each bulk action
 * - Filters (triage, vendor, date range) live in URL state for deep-links
 *
 * Day-1 implementation lands the dropzone + table. Bulk actions, keyboard
 * nav, and URL-state filters come online in Day 2.
 */
import { Link } from 'react-router-dom'

import { TriagePill } from '@/components/primitives/TriagePill'
import { UploadDropzone } from '@/components/primitives/UploadDropzone'
import { useInboxQuery } from '@/state/invoices'

type TriagePillVariant =
  | 'confident'
  | 'needs_review'
  | 'likely_duplicate'
  | 'unprocessable'

export function InboxScreen() {
  const { data, isLoading, error } = useInboxQuery()
  return (
    <div className="container py-8">
      <h1 className="text-2xl font-semibold">Inbox</h1>

      <div className="mt-4">
        <UploadDropzone />
      </div>

      <div className="mt-8 overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Triage</th>
              <th className="px-4 py-2">Vendor</th>
              <th className="px-4 py-2">Invoice #</th>
              <th className="px-4 py-2">Date</th>
              <th className="px-4 py-2 text-right">Total</th>
              <th className="px-4 py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td
                  colSpan={6}
                  className="px-4 py-6 text-center text-muted-foreground"
                >
                  Loading…
                </td>
              </tr>
            )}
            {error && (
              <tr>
                <td
                  colSpan={6}
                  className="px-4 py-6 text-center text-destructive"
                >
                  Failed to load invoices.
                </td>
              </tr>
            )}
            {data?.length === 0 && !isLoading && (
              <tr>
                <td
                  colSpan={6}
                  className="px-4 py-6 text-center text-muted-foreground"
                >
                  No invoices yet — drop one above to get started.
                </td>
              </tr>
            )}
            {data?.map((inv) => {
              const fields = inv.current_extraction?.extracted_fields ?? {}
              const isUnprocessable = inv.review_status === 'unprocessable'
              const variant: TriagePillVariant = isUnprocessable
                ? 'unprocessable'
                : ((inv.current_extraction?.predicted_triage_state ??
                    'needs_review') as TriagePillVariant)
              return (
                <tr key={inv.id} className="border-t hover:bg-accent/30">
                  <td className="px-4 py-2">
                    <TriagePill variant={variant} />
                  </td>
                  <td className="px-4 py-2">
                    <Link
                      to={`/invoice/${inv.id}`}
                      className="font-medium hover:underline"
                    >
                      {fields.vendor_name?.value ?? '—'}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {fields.invoice_number?.value ?? '—'}
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {fields.invoice_date?.value ?? '—'}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {fields.total?.value !== undefined &&
                    fields.total?.value !== null
                      ? `${fields.currency?.value ?? ''} ${fields.total.value}`
                      : '—'}
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {inv.review_status}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
