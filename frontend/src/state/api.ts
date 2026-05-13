/**
 * Base fetch wrapper. Throws `ApiError` on non-2xx; JSON-decodes the body.
 */

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly body?: unknown
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    let body: unknown
    try {
      body = await res.json()
    } catch {
      body = await res.text().catch(() => undefined)
    }
    throw new ApiError(
      res.status,
      `${init?.method ?? 'GET'} ${path} → ${res.status}`,
      body
    )
  }
  return res.json() as Promise<T>
}
