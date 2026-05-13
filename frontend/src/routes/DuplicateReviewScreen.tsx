/**
 * DuplicateReviewScreen — locked design per PLAN.md "UX surface
 * > DuplicateReviewScreen":
 *
 * - 3-column: original PDF · new PDF · field diff panel
 * - Field diff: same-row pairs, matching fields rendered subtly,
 *   differing fields highlighted; similarity score + match method at top
 * - Two actions: Confirm duplicate / Not a duplicate
 *   - Confirm → `invoices.review_status = dismissed_duplicate` on the new
 *     one, original untouched, link logged
 *   - Not a duplicate → persist a `not_a_duplicate` marker so the same pair
 *     never re-fires
 * - 1280px minimum width; below that the layout stacks vertically
 *
 * Stub for Day 1 — fills in on Day 2.
 */
import { useParams } from 'react-router-dom'

export function DuplicateReviewScreen() {
  const { id } = useParams<{ id: string }>()
  return (
    <div className="container py-8">
      <h1 className="text-2xl font-semibold">Duplicate review — {id}</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Side-by-side comparison with the suspected original. (Day 1 stub.)
      </p>
    </div>
  )
}
