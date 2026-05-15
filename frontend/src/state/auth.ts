import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, api } from '@/state/api'
import type { ClerkOut, LoginIn } from '@/types/generated/domain'

const ME_KEY = ['auth', 'me'] as const

export function useMeQuery() {
  return useQuery<ClerkOut | null, ApiError>({
    queryKey: ME_KEY,
    queryFn: async () => {
      try {
        return await api<ClerkOut>('/api/auth/me')
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          return null
        }
        throw err
      }
    },
    retry: false,
    staleTime: 30_000,
  })
}

export function useLoginMutation() {
  const qc = useQueryClient()
  return useMutation<{ user: ClerkOut }, ApiError, LoginIn>({
    mutationFn: (body) =>
      api<{ user: ClerkOut }>('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: ({ user }) => {
      qc.setQueryData(ME_KEY, user)
    },
  })
}

export function useLogoutMutation() {
  const qc = useQueryClient()
  return useMutation<void, ApiError, void>({
    mutationFn: () => api<void>('/api/auth/logout', { method: 'POST' }),
    onSettled: () => {
      qc.setQueryData(ME_KEY, null)
      qc.clear()
    },
  })
}
