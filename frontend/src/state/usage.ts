import { useQuery } from '@tanstack/react-query'

import { api } from './api'

export type ApiUsage = {
  spent_usd: number
  limit_usd: number
  remaining_usd: number
  percent_used: number
  call_count: number
  exhausted: boolean
}

export function useApiUsageQuery() {
  return useQuery({
    queryKey: ['api-usage'] as const,
    queryFn: () => api<ApiUsage>('/api/usage'),
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
  })
}
