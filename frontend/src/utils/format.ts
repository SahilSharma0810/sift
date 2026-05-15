export function formatNumber(n: number | null | undefined): string {
  if (n == null) return '—'
  if (typeof n !== 'number') return String(n)
  return n.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export function formatMoney(
  amount: number | null | undefined,
  currency?: string | null,
): string {
  if (amount == null) return '—'
  const code = (currency ?? '').trim()
  return code ? `${code} ${formatNumber(amount)}` : formatNumber(amount)
}
