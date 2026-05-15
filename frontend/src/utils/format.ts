export function formatNumber(n: number | null | undefined): string {
  if (n == null) return '—'
  if (typeof n !== 'number') return String(n)
  return n.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}
