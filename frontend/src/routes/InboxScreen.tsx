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
 * Stub for Day 1 — fills in across Day 1 and Day 2.
 */
export function InboxScreen() {
  return (
    <div className="container py-8">
      <h1 className="text-2xl font-semibold">Inbox</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Upload an invoice or wait for triage. (Day 1 stub — table lands when
        the upload endpoint and first extraction wire up.)
      </p>
    </div>
  )
}
