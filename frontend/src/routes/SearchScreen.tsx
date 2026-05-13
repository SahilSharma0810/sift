/**
 * SearchScreen — locked design per ADR-0004 + PLAN.md Day 4:
 *
 * - Chips ARE the state. NL box is a chip-editor fast-path.
 * - StructuredQuery filters render as removable chips; editing/removing
 *   re-queries.
 * - Best-effort partial translation — untranslated_intent surfaces in an
 *   amber notice above results.
 * - URL-state persistence so deep-links share the exact query.
 * - FTS on raw_text exposed as `raw_text fts_matches "..."` clause.
 *
 * Stub for Day 1 — fills in on Day 4.
 */
export function SearchScreen() {
  return (
    <div className="container py-8">
      <h1 className="text-2xl font-semibold">Search</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Natural-language and chip filters. (Day 1 stub — wires up on Day 4.)
      </p>
    </div>
  )
}
