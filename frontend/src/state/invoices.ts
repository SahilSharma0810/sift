import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type { InvoiceOut, VendorOut } from '@/types/generated/domain'

import { api } from './api'

export interface FilterClause {
  field: string
  op: string
  value: string | number | boolean | (string | number)[] | null
}

export interface StructuredQuery {
  filters: FilterClause[]
  sort?: [string, 'asc' | 'desc'] | null
  limit?: number
  untranslated_intent?: string | null
}

export const EMPTY_QUERY: StructuredQuery = {
  filters: [],
  limit: 50,
  untranslated_intent: null,
}

export function useTranslateMutation() {
  return useMutation({
    mutationFn: (query: string) =>
      api<StructuredQuery>('/api/search/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      }),
  })
}

export function useSearchQuery(query: StructuredQuery) {

  return useQuery({
    queryKey: ['search', JSON.stringify(query)] as const,
    queryFn: () =>
      api<InvoiceOut[]>('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(query),
      }),
  })
}

export type AppMeta = {
  version: string
  llm_provider: 'stub' | 'anthropic'
}

export function useAppMetaQuery() {
  return useQuery({
    queryKey: ['meta'] as const,
    queryFn: () => api<AppMeta>('/api/meta'),
    staleTime: Infinity,
  })
}

const KEYS = {
  inbox: ['invoices'] as const,
  invoice: (id: string) => ['invoices', id] as const,
}

export function useInboxQuery() {
  return useQuery({
    queryKey: KEYS.inbox,
    queryFn: () => api<InvoiceOut[]>('/api/invoices'),
  })
}

export function useInvoiceQuery(id: string | undefined) {
  return useQuery({
    queryKey: id ? KEYS.invoice(id) : ['invoices', '__none__'],
    queryFn: () => api<InvoiceOut>(`/api/invoices/${id}`),
    enabled: !!id,
  })
}

export function useUploadMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api<InvoiceOut>('/api/invoices', { method: 'POST', body: form })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.inbox })
    },
  })
}

export function useConfirmMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) =>
      api<InvoiceOut>(`/api/invoices/${id}/confirm`, { method: 'POST' }),
    onSuccess: (inv) => {
      qc.invalidateQueries({ queryKey: KEYS.inbox })
      qc.setQueryData(KEYS.invoice(inv.id), inv)
    },
  })
}

export function useDismissDuplicateMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, againstId }: { id: string; againstId: string }) =>
      api<InvoiceOut>(`/api/invoices/${id}/dismiss-duplicate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ against_id: againstId }),
      }),
    onSuccess: (inv) => {
      qc.invalidateQueries({ queryKey: KEYS.inbox })
      qc.setQueryData(KEYS.invoice(inv.id), inv)
    },
  })
}

export function useMarkUnprocessableMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) =>
      api<InvoiceOut>(`/api/invoices/${id}/mark-unprocessable`, { method: 'POST' }),
    onSuccess: (inv) => {
      qc.invalidateQueries({ queryKey: KEYS.inbox })
      qc.setQueryData(KEYS.invoice(inv.id), inv)
    },
  })
}

export function useInvoiceVendorQuery(id: string | undefined) {
  return useQuery({
    queryKey: id ? ['invoices', id, 'vendor'] : ['invoices', '__none__', 'vendor'],
    queryFn: () => api<VendorOut | null>(`/api/invoices/${id}/vendor`),
    enabled: !!id,
  })
}

export function useRetryMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, forceTier }: { id: string; forceTier?: string }) => {
      const qs = forceTier ? `?force_tier=${forceTier}` : ''
      return api<InvoiceOut>(`/api/invoices/${id}/retry${qs}`, { method: 'POST' })
    },
    onSuccess: (inv) => {
      qc.invalidateQueries({ queryKey: KEYS.inbox })
      qc.setQueryData(KEYS.invoice(inv.id), inv)
    },
  })
}
