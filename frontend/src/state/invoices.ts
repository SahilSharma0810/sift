import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type { InvoiceOut } from '@/types/generated/domain'

import { api } from './api'

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
