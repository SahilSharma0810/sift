import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, api } from '@/state/api'
import type {
  AnomaliesResponse,
  AnomalyOut,
  BulkAcknowledgeOut,
} from '@/types/generated/domain'

const ANOMALIES_KEY = ['anomalies'] as const

export function useAnomaliesQuery() {
  return useQuery<AnomaliesResponse, ApiError>({
    queryKey: ANOMALIES_KEY,
    queryFn: () => api<AnomaliesResponse>('/api/anomalies'),
    staleTime: 15_000,
  })
}

export function useAnomalyCountQuery() {
  return useQuery<AnomaliesResponse, ApiError, number>({
    queryKey: ANOMALIES_KEY,
    queryFn: () => api<AnomaliesResponse>('/api/anomalies'),
    staleTime: 15_000,
    select: (data) => data.counts.unreviewed,
  })
}

export function useAcknowledgeAnomaly() {
  const qc = useQueryClient()
  return useMutation<AnomalyOut, ApiError, string>({
    mutationFn: (anomalyId) =>
      api<AnomalyOut>(`/api/anomalies/${encodeURIComponent(anomalyId)}/acknowledge`, {
        method: 'POST',
      }),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ANOMALIES_KEY })
    },
  })
}

export function useBulkAcknowledgeAnomalies() {
  const qc = useQueryClient()
  return useMutation<BulkAcknowledgeOut, ApiError, string[]>({
    mutationFn: (anomalyIds) =>
      api<BulkAcknowledgeOut>('/api/anomalies/acknowledge-bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ anomaly_ids: anomalyIds }),
      }),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ANOMALIES_KEY })
    },
  })
}
