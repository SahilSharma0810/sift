/** 2-decimal-place locale formatter used for amounts in the design. */
export function formatNumber(n: number | null | undefined): string {
  if (n == null) return '—'
  if (typeof n !== 'number') return String(n)
  return n.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}
