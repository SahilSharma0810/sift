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

type UnauthorizedHandler = () => void

let unauthorizedHandler: UnauthorizedHandler | null = null

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: 'include',
    ...init,
  })
  if (!res.ok) {
    if (res.status === 401 && unauthorizedHandler) {
      unauthorizedHandler()
    }
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
  if (res.status === 204) {
    return undefined as unknown as T
  }
  return res.json() as Promise<T>
}
