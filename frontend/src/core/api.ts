/* API client (spec §11) — base = location.origin (fixes the legacy hardcoded
   http://), error taxonomy: network | http | stream. */

export class ApiError extends Error {
  kind: 'network' | 'http'
  status?: number
  detail?: string

  constructor(kind: 'network' | 'http', message: string, status?: number, detail?: string) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.detail = detail
  }
}

const BASE = typeof window !== 'undefined' ? window.location.origin : ''

export async function apiJSON<T>(
  path: string,
  init?: RequestInit,
  opts?: { timeoutMs?: number },
): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(
    () => controller.abort(),
    opts?.timeoutMs ?? 15_000,
  )
  try {
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    })
    if (!res.ok) {
      let detail: string | undefined
      try {
        const body = await res.json()
        detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? body)
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError('http', `HTTP ${res.status} on ${path}`, res.status, detail)
    }
    return (await res.json()) as T
  } catch (e) {
    if (e instanceof ApiError) throw e
    throw new ApiError('network', `Cannot reach server at ${path}`, undefined, String(e))
  } finally {
    clearTimeout(timeout)
  }
}

export function sseRequest(path: string, body: unknown): { response: Promise<Response>; abort: () => void } {
  const controller = new AbortController()
  const response = fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
  return { response, abort: () => controller.abort() }
}

/* ── Known server shapes (from api_server.py / schemas.py) ── */

export interface HealthStatus {
  status: string
  version: string
}

export interface ModelStatus {
  id: string
  path: string
  loaded: boolean
  arch: string | null
  n_experts: number
  buffer_mb: number
  last_used: string | null
}

export interface ServerStatus {
  models_loaded: number
  max_models: number
  queue_depth: number
  host: string
  port: number
  priority?: string
}

export interface IssueSummary {
  id: string
  title: string
  status: string
  severity: string
  created_at: string
}
